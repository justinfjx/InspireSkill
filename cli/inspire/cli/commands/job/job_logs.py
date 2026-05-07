"""Job logs command — SSH tunnel only.

`inspire job logs <name>` cats / tails / follows the remote log file via
the SSH tunnel of a cached notebook (any one with shared-FS access; pick
explicitly with ``--notebook``). The log path uses the convention
``<target_dir>/.inspire/training_master_<sanitized_name>_<timestamp>.log``;
``inspire job logs`` resolves the latest match via SSH ``ls -1t`` so a
re-submitted name shows the most recent run, not a clobbered file. Pass
``--remote-log-path`` to override (e.g. for jobs created from the Web UI).

Bulk mode and the legacy GitHub-workflow fallback were removed alongside
the JobCache deletion: the SSH tunnel kit is universal (cf. SKILL §1.1
"SSH bootstrap"), and the workflow path was already declared deprecated.
"""

from __future__ import annotations

import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import click

from inspire.bridge.tunnel import (
    TunnelNotAvailableError,
    _test_ssh_connection,
    is_tunnel_available,
    load_tunnel_config,
    run_ssh_command,
)
from inspire.cli.context import (
    Context,
    EXIT_CONFIG_ERROR,
    EXIT_GENERAL_ERROR,
    EXIT_JOB_NOT_FOUND,
    EXIT_LOG_NOT_FOUND,
    EXIT_SUCCESS,
    pass_context,
)
from inspire.cli.formatters import json_formatter
from inspire.cli.utils.auth import AuthManager
from inspire.cli.utils.errors import exit_with_error as _handle_error
from inspire.cli.utils.job_cli import resolve_job_id
from inspire.cli.utils.job_submit import derive_remote_log_glob
from inspire.config import Config, ConfigError


def _resolve_latest_log_via_ssh(
    glob_pattern: str, *, bridge_name: Optional[str] = None
) -> Optional[str]:
    """Resolve a log glob pattern to the most recently written matching file.

    Uses ``ls -1t`` so the freshest mtime wins (re-submitting the same job
    NAME picks up the new run, not a clobbered old log). The pattern is
    intentionally NOT shell-quoted so ``*`` expands; the directory and
    sanitized name within it have no other shell metacharacters by
    construction (``sanitize_job_name_for_filename`` strips them).

    Returns the absolute path on hit, ``None`` on no match. Errors during
    SSH propagate up — the caller is the boundary that decides whether to
    surface them.
    """
    cmd = f"ls -1t {glob_pattern} 2>/dev/null | head -n 1"
    try:
        result = run_ssh_command(command=cmd, capture_output=True, bridge_name=bridge_name)
    except Exception:
        return None
    if result.returncode != 0:
        return None
    out = (result.stdout or "").strip()
    return out or None


def _fetch_log_via_ssh(
    remote_log_path: str,
    tail: Optional[int] = None,
    head: Optional[int] = None,
    bridge_name: Optional[str] = None,
) -> str:
    if tail:
        command = f"tail -n {tail} '{remote_log_path}'"
    elif head:
        command = f"head -n {head} '{remote_log_path}'"
    else:
        command = f"cat '{remote_log_path}'"

    result = run_ssh_command(command=command, capture_output=True, bridge_name=bridge_name)

    if result.returncode != 0:
        raise IOError(f"Failed to read log file: {result.stderr}")

    return result.stdout


def _follow_logs_via_ssh(
    job_id: str,
    config: Config,
    remote_log_path: str,
    tail_lines: int = 50,
    wait_timeout: int = 300,
    bridge_name: Optional[str] = None,
) -> Optional[str]:
    import select
    import subprocess
    import time

    from inspire.bridge.tunnel import get_ssh_command_args

    api_logger = logging.getLogger("inspire.inspire_api_control")
    original_level = api_logger.level
    api_logger.setLevel(logging.CRITICAL)

    api = AuthManager.get_api(config)
    terminal_statuses = {
        "SUCCEEDED",
        "FAILED",
        "CANCELLED",
        "job_succeeded",
        "job_failed",
        "job_cancelled",
    }
    final_status = None
    status_check_interval = 5

    is_glob = "*" in remote_log_path
    if is_glob:
        click.echo(f"Log file pattern: {remote_log_path}")
    else:
        click.echo(f"Log file: {remote_log_path}")

    start_time = time.time()
    concrete_log_path: Optional[str] = None

    while time.time() - start_time < wait_timeout:
        try:
            if is_glob:
                # Re-resolve every iteration so a fresh log file (post-create
                # eventual consistency on the FS, or job_id-based suffix that
                # only materializes when the job's container starts) is
                # picked up automatically.
                resolved = _resolve_latest_log_via_ssh(remote_log_path, bridge_name=bridge_name)
                if resolved:
                    concrete_log_path = resolved
                    break
            else:
                check_cmd = f"test -f '{remote_log_path}' && echo 'exists' || echo 'waiting'"
                result = run_ssh_command(check_cmd, timeout=10, bridge_name=bridge_name)
                if "exists" in result.stdout:
                    concrete_log_path = remote_log_path
                    break
        except Exception:
            pass

        elapsed = int(time.time() - start_time)
        click.echo(f"\rWaiting for job to start... ({elapsed}s)", nl=False)
        time.sleep(5)

    if not concrete_log_path:
        click.echo(f"\n\nTimeout: Log file not created after {wait_timeout}s")
        click.echo("Job may still be queuing. Check status with: inspire job status <job-name>")
        return None

    # Past the wait gate — switch to the concrete path for tail -f.
    remote_log_path = concrete_log_path

    click.echo("\nJob started! Following logs...")
    click.echo(f"(showing last {tail_lines} lines, then following new content)")
    click.echo("Press Ctrl+C to stop\n")

    command = f"tail -n {tail_lines} -f '{remote_log_path}'"
    ssh_args = get_ssh_command_args(bridge_name=bridge_name, remote_command=command)

    process = None
    try:
        process = subprocess.Popen(
            ssh_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            universal_newlines=True,
        )

        last_status_check = time.time()

        while True:
            if process.poll() is not None:
                for line in process.stdout:
                    click.echo(line, nl=False)
                break

            ready, _, _ = select.select([process.stdout], [], [], 1.0)

            if ready:
                line = process.stdout.readline()
                if line:
                    click.echo(line, nl=False)
                elif process.poll() is not None:
                    break

            current_time = time.time()
            if current_time - last_status_check >= status_check_interval:
                last_status_check = current_time
                try:
                    result = api.get_job_detail(job_id)
                    job_data = result.get("data", {})
                    current_status = job_data.get("status", "UNKNOWN")

                    if current_status in terminal_statuses:
                        final_status = current_status
                        time.sleep(3)
                        process.stdout.close()
                        break
                except Exception:
                    pass

        if final_status:
            click.echo(f"\n\nJob completed with status: {final_status}")

    except KeyboardInterrupt:
        click.echo("\n\nStopped following logs.")
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait()
        api_logger.setLevel(original_level)

    return final_status


def _find_connected_tunnel_bridges(
    *,
    exclude: Optional[str] = None,
    timeout: int = 5,
) -> list[str]:
    """Best-effort probe for connected tunnel profiles."""
    try:
        config = load_tunnel_config()
    except Exception:
        return []

    excluded = (exclude or "").strip()
    candidates = [bridge for bridge in config.list_bridges() if bridge.name != excluded]
    if not candidates:
        return []

    connected: list[str] = []
    max_workers = min(len(candidates), 8)
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_test_ssh_connection, bridge, config, timeout): bridge.name
            for bridge in candidates
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                if future.result():
                    connected.append(name)
            except Exception:
                continue

    return sorted(connected)


def _resolve_tunnel_preflight_target(
    bridge_name: Optional[str],
) -> tuple[Optional[str], object | None, bool]:
    """Resolve the bridge/config tuple used by SSH availability preflight."""
    try:
        tunnel_config = load_tunnel_config()
    except Exception:
        return bridge_name, None, bool(bridge_name)

    if bridge_name:
        return bridge_name, tunnel_config, tunnel_config.get_bridge(bridge_name) is not None

    bridge = tunnel_config.get_bridge()
    if bridge is None:
        return None, tunnel_config, False

    return bridge.name, tunnel_config, True


def _emit_no_tunnel_error(ctx: Context, *, bridge_name: Optional[str]) -> None:
    connected = _find_connected_tunnel_bridges(exclude=bridge_name)
    if connected:
        preview = ", ".join(connected[:5])
        if len(connected) > 5:
            preview = f"{preview}, +{len(connected) - 5} more"
        hint = (
            f"Cached notebook tunnel(s): {preview}. "
            "Pass --notebook <name> to target one explicitly, "
            "or run `inspire notebook ssh <notebook-name>` to bootstrap a new one."
        )
    else:
        hint = (
            "No cached notebook tunnels found. "
            "Run `inspire notebook ssh <notebook-name>` to bootstrap one with shared-FS access."
        )
    label = f"bridge '{bridge_name}'" if bridge_name else "default bridge"
    _handle_error(
        ctx,
        "TunnelError",
        f"SSH tunnel not available for {label}.",
        EXIT_GENERAL_ERROR,
        hint=hint,
    )


def _run_job_logs_single_job(
    ctx: Context,
    *,
    job_id: str,
    remote_log_path: str,
    tail: int | None,
    head: int | None,
    path: bool,
    follow: bool,
    bridge_name: Optional[str] = None,
) -> None:
    try:
        config = Config.from_env(require_target_dir=False)

        effective_bridge_name, tunnel_config, bridge_configured = _resolve_tunnel_preflight_target(
            bridge_name
        )
        bridge_name_for_checks = effective_bridge_name or bridge_name

        try:
            tunnel_ok = is_tunnel_available(
                bridge_name=bridge_name_for_checks,
                config=tunnel_config,
                retries=0,
                retry_pause=0.0,
                progressive=False,
            )
        except TypeError:
            # Backward-compatible test doubles may still expose the old no-arg signature.
            tunnel_ok = is_tunnel_available()

        if not tunnel_ok:
            if bridge_name and tunnel_config is not None and not bridge_configured:
                _handle_error(
                    ctx,
                    "NotebookTunnelNotFound",
                    f"No cached notebook tunnel for '{bridge_name}'.",
                    EXIT_GENERAL_ERROR,
                    hint="Run 'inspire notebook connections' to see cached notebooks.",
                )
            _emit_no_tunnel_error(ctx, bridge_name=bridge_name)
            return

        if path:
            if ctx.json_output:
                click.echo(
                    json_formatter.format_json({"job_id": job_id, "log_path": remote_log_path})
                )
            else:
                click.echo(remote_log_path)
            sys.exit(EXIT_SUCCESS)

        if follow:
            if ctx.json_output:
                _handle_error(
                    ctx,
                    "InvalidUsage",
                    "--follow requires the human-readable output mode.",
                    EXIT_GENERAL_ERROR,
                    hint="Drop --json or use a one-shot fetch (default / --tail / --head).",
                )
                return

            if not ctx.json_output:
                label = f", bridge: {bridge_name}" if bridge_name else ""
                click.echo(f"Using SSH tunnel (fast path{label})")

            final_status = _follow_logs_via_ssh(
                job_id=job_id,
                config=config,
                remote_log_path=remote_log_path,
                tail_lines=tail or 50,
                bridge_name=bridge_name,
            )

            if final_status in {"SUCCEEDED", "job_succeeded"}:
                sys.exit(EXIT_SUCCESS)
            if final_status in {"FAILED", "CANCELLED", "job_failed", "job_cancelled"}:
                sys.exit(EXIT_GENERAL_ERROR)
            sys.exit(EXIT_SUCCESS)

        if not ctx.json_output:
            label = f", bridge: {bridge_name}" if bridge_name else ""
            click.echo(f"Using SSH tunnel (fast path{label})")

        try:
            content = _fetch_log_via_ssh(
                remote_log_path=remote_log_path,
                tail=tail,
                head=head,
                bridge_name=bridge_name,
            )
        except IOError as e:
            _handle_error(
                ctx,
                "LogNotFound",
                str(e),
                EXIT_LOG_NOT_FOUND,
                hint=(
                    "If the job hasn't started yet the log file may not exist. "
                    "Check `inspire job status` and try again, or pass --remote-log-path "
                    "if the path differs from the default training_master_<name>.log convention."
                ),
            )
            return

        if ctx.json_output:
            click.echo(
                json_formatter.format_json(
                    {
                        "job_id": job_id,
                        "log_path": remote_log_path,
                        "content": content,
                        "method": "ssh_tunnel",
                    }
                )
            )
            return

        if tail:
            click.echo(f"=== Last {tail} lines ===\n")
        elif head:
            click.echo(f"=== First {head} lines ===\n")
        click.echo(content)

    except TunnelNotAvailableError:
        _emit_no_tunnel_error(ctx, bridge_name=bridge_name)
    except ConfigError as e:
        _handle_error(ctx, "ConfigError", str(e), EXIT_CONFIG_ERROR)
    except Exception as e:
        _handle_error(ctx, "Error", str(e), EXIT_GENERAL_ERROR)


@click.command("logs")
@click.argument("job")
@click.option("--tail", "-n", type=int, help="Show last N lines only")
@click.option("--head", type=int, help="Show first N lines only")
@click.option("--path", is_flag=True, help="Just print log path, don't read content")
@click.option("--follow", "-f", is_flag=True, help="Stream new log content via tail -f over SSH")
@click.option(
    "--remote-log-path",
    default=None,
    help=(
        "Explicit remote log file path. Overrides the default convention "
        "<target_dir>/.inspire/training_master_<name>.log. Useful for web-UI-created "
        "jobs where the path was set by the platform."
    ),
)
@click.option(
    "--notebook",
    help=(
        "Notebook name whose cached SSH tunnel should be used. Required when more "
        "than one is cached and the default bridge is ambiguous. "
        "Bootstrap with `inspire notebook ssh <notebook-name>` first. "
        "No short alias — `-n` is reserved for --tail."
    ),
)
@click.option(
    "--all-workspaces",
    "-A",
    is_flag=True,
    help="Resolve the job name across every visible workspace, not just the current one",
)
@pass_context
def logs(
    ctx: Context,
    job: str,
    tail: int | None,
    head: int | None,
    path: bool,
    follow: bool,
    remote_log_path: Optional[str],
    notebook: Optional[str],
    all_workspaces: bool,
) -> None:
    """Tail / cat the remote log file for a training job over SSH.

    Requires a cached notebook tunnel (`inspire notebook ssh <name>`).
    The log path defaults to the convention written by `inspire run` /
    `inspire job create` (``<target_dir>/.inspire/training_master_<name>.log``);
    use ``--remote-log-path`` to override for jobs whose path differs.

    \b
    Examples:
        inspire job logs my-training-run
        inspire job logs my-training-run --tail 100
        inspire job logs my-training-run --head 50
        inspire job logs my-training-run --follow
        inspire job logs my-training-run --path
        inspire job logs my-training-run --notebook my-cpu-box
        inspire job logs my-training-run --remote-log-path /inspire/.../custom.log
    """
    if notebook is not None:
        from inspire.cli.utils.id_resolver import reject_id_at_boundary

        notebook = reject_id_at_boundary(
            ctx,
            notebook,
            resource_type="notebook",
            list_command="inspire notebook connections",
        )
    bridge = notebook

    job_id = resolve_job_id(ctx, job, all_workspaces=all_workspaces)

    if remote_log_path:
        resolved_log_path = remote_log_path.strip()
        if not resolved_log_path:
            _handle_error(
                ctx,
                "InvalidUsage",
                "--remote-log-path cannot be empty",
                EXIT_GENERAL_ERROR,
            )
            return
    else:
        try:
            config = Config.from_env(require_target_dir=False)
        except ConfigError as e:
            _handle_error(ctx, "ConfigError", str(e), EXIT_CONFIG_ERROR)
            return
        glob_pattern = derive_remote_log_glob(config, name=job)
        if not glob_pattern:
            _handle_error(
                ctx,
                "ConfigError",
                "Cannot derive remote log path: [paths].target_dir is unset.",
                EXIT_CONFIG_ERROR,
                hint=(
                    "Set [paths].target_dir in your account config (run "
                    "`inspire init --discover` to populate it), or pass "
                    "--remote-log-path explicitly."
                ),
            )
            return
        resolved_log_path = _resolve_latest_log_via_ssh(glob_pattern, bridge_name=bridge)
        if not resolved_log_path:
            if follow:
                # `_follow_logs_via_ssh` polls for the file's existence with
                # its own wait loop — pass the glob pattern through so it
                # can poll-resolve on each iteration.
                resolved_log_path = glob_pattern
            else:
                _handle_error(
                    ctx,
                    "LogNotFound",
                    f"No log file matches {glob_pattern!r} on the shared filesystem.",
                    EXIT_LOG_NOT_FOUND,
                    hint=(
                        "The job may not have started writing yet. Pass --follow "
                        "to wait, or pass --remote-log-path if the job uses a "
                        "non-default path (e.g. created from the Web UI)."
                    ),
                )
                return

    if not job_id:
        _handle_error(ctx, "JobNotFound", f"Job not found: {job}", EXIT_JOB_NOT_FOUND)
        return

    _run_job_logs_single_job(
        ctx,
        job_id=job_id,
        remote_log_path=resolved_log_path,
        tail=tail,
        head=head,
        path=path,
        follow=follow,
        bridge_name=bridge,
    )


__all__ = ["logs"]
