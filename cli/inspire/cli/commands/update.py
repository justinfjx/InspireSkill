"""`inspire update` — check for and install newer InspireSkill versions.

Covers two things a user might want:

    inspire update                 # full upgrade: CLI package + SKILL/references
    inspire update --check         # only check upstream; write cache; print status
    inspire update --silent        # suppress output (used by the background check)
    inspire update --cli-only      # upgrade the Python package only
    inspire update --skill-only    # refresh SKILL.md + references/ only

Design notes:
- Upstream version comes from cli/pyproject.toml on main (parsed via raw.githubusercontent.com).
- SKILL/references are copied (not symlinked) into every detected harness skills dir.
- The Python package is upgraded via whatever installer currently owns it
  (`uv tool upgrade` / `pipx upgrade`), detected from ``sys.executable``'s
  path. ``inspire-skill`` is published to PyPI, so the standard upgrade path
  works — the `install.sh` default SPEC is also the PyPI package name, so
  first-time install and `inspire update` pull from the same source.
"""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

import click

from inspire import __version__
from inspire.cli.utils.update_notice import (
    PACKAGE_NAME,
    TARBALL_URL,
    run_check,
    _is_newer,
)


def _opencode_config_dir() -> Path:
    """Resolve OpenCode's config dir: $OPENCODE_CONFIG_DIR or ~/.config/opencode."""
    override = os.environ.get("OPENCODE_CONFIG_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / "opencode"


HARNESS_SKILL_DIRS = {
    "claude": Path.home() / ".claude" / "skills" / "inspire",
    "codex": Path.home() / ".codex" / "skills" / "inspire",
    "gemini": Path.home() / ".gemini" / "skills" / "inspire",
    "openclaw": Path.home() / ".openclaw" / "skills" / "inspire",
    "opencode": _opencode_config_dir() / "skills" / "inspire",
}
HARNESS_ROOTS = {
    "claude": Path.home() / ".claude",
    "codex": Path.home() / ".codex",
    "gemini": Path.home() / ".gemini",
    "openclaw": Path.home() / ".openclaw",
    "opencode": _opencode_config_dir(),
}

SKILL_ASSETS = ("SKILL.md", "references")


def _detect_harnesses() -> list[str]:
    return [h for h, root in HARNESS_ROOTS.items() if root.is_dir()]


def _detect_installer() -> str | None:
    """Guess which installer owns the current `inspire` process.

    Probes ``sys.prefix`` (the venv root) — NOT ``sys.executable.resolve()``,
    because resolving the venv's ``python`` symlink follows it through to the
    underlying interpreter (e.g. ``~/.local/share/uv/python/cpython-3.11.../
    bin/python3``), which loses the ``tools`` segment that signals "this is a
    `uv tool install`". Same hazard applies to pipx — its venv python often
    resolves to the system Python and falls outside the pipx tree.

    Returns "uv", "pipx", or None (unknown / unsupported).
    """
    parts = Path(sys.prefix).parts
    if "uv" in parts and "tools" in parts:
        return "uv"
    if "pipx" in parts and "venvs" in parts:
        return "pipx"
    return None


def _upgrade_cli(silent: bool) -> bool:
    installer = _detect_installer()
    if installer == "uv":
        cmd = ["uv", "tool", "upgrade", PACKAGE_NAME]
    elif installer == "pipx":
        cmd = ["pipx", "upgrade", PACKAGE_NAME]
    else:
        if not silent:
            click.secho(
                "✗ Can't auto-upgrade in place: this build isn't managed by "
                "`uv tool install` or `pipx install`.",
                fg="red",
                err=True,
            )
            click.secho(f"  python = {sys.executable}", fg="red", err=True)
            click.secho(f"  prefix = {sys.prefix}", fg="red", err=True)
            click.echo(
                "\n  Reinstall through the official installer so future updates "
                "use the same path as first-time installs:\n"
                "      curl -fsSL https://raw.githubusercontent.com/realZillionX/InspireSkill/main/scripts/install.sh | bash",
                err=True,
            )
        return False

    if not silent:
        click.secho(f"› {' '.join(cmd)}", fg="blue")
    try:
        subprocess.run(cmd, check=True)
    except FileNotFoundError:
        if not silent:
            click.secho(
                f"✗ `{cmd[0]}` not on PATH — you said this build was managed "
                f"by {cmd[0]} but the binary is gone.\n"
                f"  Reinstall via scripts/install.sh or run `{cmd[0]} --version` "
                f"to confirm.",
                fg="red",
                err=True,
            )
        return False
    except subprocess.CalledProcessError as e:
        if not silent:
            click.secho(
                f"✗ {cmd[0]} upgrade failed (exit {e.returncode}). "
                f"If this looks like a network / mirror error, retry; if it "
                f"keeps failing, run `{' '.join(cmd)}` manually to see the "
                f"underlying message.",
                fg="red",
                err=True,
            )
        return False
    return True


def _download_tarball(timeout: int = 30) -> bytes | None:
    req = urllib.request.Request(
        TARBALL_URL,
        headers={"User-Agent": f"inspire-skill/{__version__}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        click.secho(f"✗ tarball fetch failed: {e}", fg="red", err=True)
        return None


def _extract_assets(tarball: bytes, dest: Path) -> Path | None:
    """Extract the tarball into `dest` and return the top-level extracted dir.

    Defensive about two things:
    - **Top-level dir detection**: GitHub codeload tarballs always wrap
      content under a single ``<repo>-<ref>/`` directory, but we don't
      trust that ``members[0]`` is that directory entry — different tar
      tools order entries differently. Find the unique top segment by
      scanning all members.
    - **Path traversal**: pin ``filter='data'`` on Python 3.12+ where
      that's a documented safe default. Older Pythons silently use the
      legacy 'fully trusting' filter (``extractall`` without a filter
      kwarg), which is what we used before — codeload is GitHub-trusted
      so this is low-risk, but the explicit filter is strictly safer.
    """
    try:
        with tarfile.open(fileobj=io.BytesIO(tarball), mode="r:gz") as tf:
            members = tf.getmembers()
            if not members:
                return None
            top_segments = {m.name.split("/", 1)[0] for m in members if m.name}
            if len(top_segments) != 1:
                click.secho(
                    f"✗ tarball has unexpected layout (top-level dirs: {sorted(top_segments)}).",
                    fg="red",
                    err=True,
                )
                return None
            top = top_segments.pop()
            try:
                tf.extractall(dest, filter="data")
            except TypeError:
                # Python < 3.11.4 (no `filter=` kwarg). codeload is GitHub
                # which we trust, so the legacy extract is acceptable.
                tf.extractall(dest)
            extracted = dest / top
            return extracted if extracted.is_dir() else None
    except (tarfile.TarError, OSError) as e:
        click.secho(f"✗ tarball extract failed: {e}", fg="red", err=True)
        return None


def _refresh_skill_files(silent: bool) -> bool:
    harnesses = _detect_harnesses()
    if not harnesses:
        if not silent:
            click.secho(
                "! No agent harness detected "
                "(checked ~/.claude, ~/.codex, ~/.gemini, ~/.openclaw, "
                "$OPENCODE_CONFIG_DIR or ~/.config/opencode); "
                "skipping SKILL refresh.",
                fg="yellow",
                err=True,
            )
        return True  # not a failure; user may run skill-less

    tarball = _download_tarball()
    if tarball is None:
        return False

    with tempfile.TemporaryDirectory(prefix="inspire-skill-") as tmp:
        extracted = _extract_assets(tarball, Path(tmp))
        if extracted is None:
            click.secho("✗ tarball layout unexpected (no top-level dir).", fg="red", err=True)
            return False

        src_skill = extracted / "SKILL.md"
        src_refs = extracted / "references"
        if not src_skill.is_file():
            click.secho("✗ SKILL.md missing in tarball.", fg="red", err=True)
            return False

        for harness in harnesses:
            target = HARNESS_SKILL_DIRS[harness]
            # Wipe any previous install, including stale symlinks or files.
            if target.exists() or target.is_symlink():
                try:
                    if target.is_symlink() or target.is_file():
                        target.unlink()
                    else:
                        shutil.rmtree(target)
                except OSError as e:
                    click.secho(f"✗ couldn't clean {target}: {e}", fg="red", err=True)
                    return False
            target.mkdir(parents=True, exist_ok=True)

            shutil.copy2(src_skill, target / "SKILL.md")
            if src_refs.is_dir():
                shutil.copytree(src_refs, target / "references", dirs_exist_ok=True)

            if harness == "codex":
                agents_dir = target / "agents"
                agents_dir.mkdir(parents=True, exist_ok=True)
                (agents_dir / "openai.yaml").write_text(
                    'interface:\n'
                    '  display_name: "Inspire"\n'
                    '  short_description: "Execution-first Inspire operations via the inspire CLI, '
                    'including auth, proxy routing, notebook/image workflows, and job/HPC execution."\n',
                    encoding="utf-8",
                )

            if not silent:
                click.secho(f"✓ refreshed skill → {target}", fg="green")

    return True


def _print_status(check_result: dict, silent: bool) -> None:
    if silent:
        return
    latest = check_result.get("latest")
    current = check_result.get("current") or __version__
    if not latest:
        click.secho(
            f"! Couldn't reach upstream ({check_result.get('source')}); "
            "check your proxy / network.",
            fg="yellow",
            err=True,
        )
        return
    if _is_newer(latest, current):
        click.secho(
            f"⚠ InspireSkill v{latest} available (current v{current}).",
            fg="yellow",
        )
        click.echo("  run `inspire update` (no flags) to upgrade CLI + SKILL files in one go.")
    else:
        click.secho(f"✓ InspireSkill is up to date (v{current}).", fg="green")


@click.command("update")
@click.option("--check", "check_only", is_flag=True, help="Only check upstream; don't upgrade.")
@click.option("--silent", is_flag=True, help="Suppress output (used by background checks).")
@click.option("--cli-only", is_flag=True, help="Upgrade the Python package only.")
@click.option("--skill-only", is_flag=True, help="Refresh SKILL.md + references/ only.")
def update(check_only: bool, silent: bool, cli_only: bool, skill_only: bool) -> None:
    """Check for and install newer InspireSkill versions."""
    if cli_only and skill_only:
        raise click.UsageError("--cli-only and --skill-only are mutually exclusive.")

    # --- check path -------------------------------------------------------
    if check_only:
        result = run_check(write=True)
        _print_status(result, silent)
        if not result.get("latest"):
            sys.exit(1)
        return

    # --- upgrade path -----------------------------------------------------
    # Always refresh the version cache first so subsequent invocations show
    # the correct state and the notice goes away if we successfully upgrade.
    pre = run_check(write=True)
    if not silent:
        _print_status(pre, silent=False)

    ok = True
    if not skill_only:
        ok = _upgrade_cli(silent) and ok
    if not cli_only:
        ok = _refresh_skill_files(silent) and ok

    # Re-check after upgrade so the cache reflects the new local version.
    run_check(write=True)

    if not ok:
        sys.exit(1)

    # Run environment normalization once after a successful upgrade so users
    # coming from v3.1.x (no sentinel yet) get pre-v3 unscoped files
    # quarantined and stale env vars flagged on the same `inspire update` they
    # ran to install v4. Idempotent via the normalization sentinel.
    try:
        from inspire.accounts import normalize_environment

        normalize_environment(interactive=not silent)
    except Exception:
        # Normalization is best-effort cleanup; never fail the upgrade itself.
        pass

    if not silent:
        click.secho("✓ InspireSkill updated.", fg="green", bold=True)
