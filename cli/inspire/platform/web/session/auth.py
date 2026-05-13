"""Authentication helpers for web-session based APIs."""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING, Any, Optional, cast

from inspire.config import Config

from .models import DEFAULT_WORKSPACE_ID, WebSession
from .browser_launch import (
    chromium_launch_kwargs,
    is_playwright_browser_runtime_error,
    playwright_install_hint,
)
from .proxy import get_playwright_proxy

if TYPE_CHECKING:
    from playwright.sync_api import ProxySettings


def _load_runtime_config() -> Config:
    config, _ = Config.from_files_and_env(require_credentials=False)
    return config


def _session_matches_username(cached: WebSession, username: str) -> bool:
    if not username:
        return True
    if not cached.login_username:
        return False
    return cached.login_username == username


def _has_real_workspace_id(session: WebSession) -> bool:
    value = str(session.workspace_id or "").strip()
    return bool(value) and value != DEFAULT_WORKSPACE_ID


def _is_browser_closed_error(exc: BaseException) -> bool:
    text = str(exc)
    return "Target page, context or browser has been closed" in text


def _is_browser_launch_runtime_error(exc: BaseException) -> bool:
    return is_playwright_browser_runtime_error(exc)


def _raise_browser_launch_runtime_error(exc: BaseException) -> None:
    raise RuntimeError(
        "Playwright Chromium could not start for Inspire login. Repair the "
        "browser runtime and Linux container dependencies with:\n"
        f"    {playwright_install_hint()}\n"
        "Then retry `inspire init`."
    ) from exc


def _raise_browser_closed_error(exc: BaseException) -> None:
    from inspire.config import ConfigError

    raise ConfigError(
        "Playwright Chromium closed during Inspire login. This is usually a "
        "browser runtime problem in a containerized notebook, not an account "
        "credential problem. InspireSkill launches Chromium with container-safe "
        "sandbox and /dev/shm flags; if this still happens, reinstall the "
        "Playwright browser runtime for the active package and retry."
    ) from exc


_WORKSPACE_ID_PATTERN = re.compile(
    r"^ws-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


def _workspace_routes_from_payload(payload: dict[str, Any]) -> tuple[list[str], dict[str, str]]:
    workspace_ids: list[str] = []
    workspace_names: dict[str, str] = {}
    for route_group in (payload.get("data") or {}).get("routes") or []:
        if not isinstance(route_group, dict):
            continue
        if route_group.get("name") != "userWorkspaceList":
            continue
        for entry in route_group.get("routes") or []:
            if not isinstance(entry, dict):
                continue
            ws_id = str(entry.get("path") or "").strip()
            ws_name = str(entry.get("name") or "").strip()
            if ws_id and _WORKSPACE_ID_PATTERN.match(ws_id) and ws_id != DEFAULT_WORKSPACE_ID:
                if ws_id not in workspace_names:
                    workspace_ids.append(ws_id)
                    workspace_names[ws_id] = ws_name
    return workspace_ids, workspace_names


def _merge_workspace_routes(
    current_ids: list[str],
    current_names: dict[str, str],
    new_ids: list[str],
    new_names: dict[str, str],
) -> None:
    for ws_id in new_ids:
        if ws_id not in current_names:
            current_ids.append(ws_id)
        if new_names.get(ws_id):
            current_names[ws_id] = new_names[ws_id]


def get_credentials() -> tuple[str, str]:
    """Get web credentials from layered config (project/global/env/default)."""
    config = _load_runtime_config()
    username = (config.username or "").strip()
    password = config.password or ""

    if not username or not password:
        raise ValueError(
            "Missing web authentication credentials. Run 'inspire account add <name>' "
            "to create an account, or set INSPIRE_PASSWORD when the account's "
            "config.toml lacks [auth].password."
        )

    return username, password


def login_with_playwright(
    username: str,
    password: str,
    base_url: str = "https://api.example.com",
    headless: bool = True,
) -> WebSession:
    """Login to Inspire web UI using Playwright and capture session storage state.

    The login flow: qz/login -> CAS (Keycloak broker) -> Keycloak -> qz.
    """
    from inspire.platform.web.browser_api.core import _in_asyncio_loop, _run_in_thread

    if _in_asyncio_loop():
        return _run_in_thread(
            login_with_playwright,
            username,
            password,
            base_url=base_url,
            headless=headless,
        )

    from playwright.sync_api import sync_playwright

    proxy = cast("ProxySettings | None", get_playwright_proxy())
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(**chromium_launch_kwargs(headless=headless, proxy=proxy))
        except Exception as exc:
            if _is_browser_launch_runtime_error(exc):
                _raise_browser_launch_runtime_error(exc)
            raise
        context = browser.new_context(proxy=proxy, ignore_https_errors=True)
        page = context.new_page()

        # Navigate to login page; use domcontentloaded since CAS may have
        # long-polling resources that prevent networkidle from completing.
        try:
            page.goto(f"{base_url}/login", wait_until="domcontentloaded", timeout=60000)
        except Exception as exc:
            if _is_browser_closed_error(exc):
                _raise_browser_closed_error(exc)
            raise
        # Give some time for any redirects to settle
        page.wait_for_timeout(2000)

        login_pairs = [
            ("input#username", "input#passwordShow"),
            ("input[name='username']", "input[name='password']"),
            ("input[placeholder='Username/alias']", "input[placeholder='Password']"),
        ]

        def _fill_login_form() -> Optional[object]:
            for user_sel, pass_sel in login_pairs:
                try:
                    page.wait_for_selector(user_sel, timeout=5000, state="visible")
                    page.wait_for_selector(pass_sel, timeout=5000, state="visible")
                    user_locator = page.locator(user_sel).first
                    pass_locator = page.locator(pass_sel).first
                    user_locator.fill(username)
                    pass_locator.fill(password)
                    return pass_locator
                except Exception:
                    continue
            return None

        def _submit_login_form(pass_locator) -> None:  # noqa: ANN001
            try:
                pass_locator.press("Enter", timeout=3000)
                return
            except Exception:
                pass
            try:
                pass_locator.evaluate("el => el.form && el.form.submit()")
                return
            except Exception:
                pass
            try:
                pass_locator.evaluate(
                    """
                    el => {
                      const btn = el.form?.querySelector('#passbutton,button[type="submit"],input[type="submit"]');
                      if (btn) { btn.click(); return true; }
                      return false;
                    }
                    """
                )
            except Exception:
                pass

        pass_locator = _fill_login_form()
        if not pass_locator:
            try:
                page.get_by_text("Account login", exact=True).click(timeout=3000, force=True)
                page.wait_for_timeout(500)
            except Exception:
                pass
            pass_locator = _fill_login_form()

        if pass_locator:
            _submit_login_form(pass_locator)

        def _wait_for_api_auth() -> None:
            deadline = time.time() + 30
            headers = {
                "Accept": "application/json",
                "Referer": f"{base_url}/login",
            }
            while time.time() < deadline:
                try:
                    resp = context.request.get(
                        f"{base_url}/api/v1/user/detail",
                        headers=headers,
                        timeout=10000,
                    )
                    if resp.status == 200:
                        return
                except Exception:
                    pass
                page.wait_for_timeout(500)
            raise ValueError(
                "Login did not complete. Check that the password is correct and "
                "`auth.username` is the platform login ID (phone, student ID, or email), "
                "not the display name."
            )

        _wait_for_api_auth()
        # Once authenticated cookies are available, stop the page quickly and
        # use request APIs for discovery.  Some minimal GPU notebook images can
        # start Chromium but crash while rendering the full Qizhi SPA because
        # fontconfig is incomplete; rendering the SPA is unnecessary for CLI
        # session capture.
        try:
            page.close()
        except Exception:
            pass

        user_detail: dict | None = None
        request_headers = {
            "Accept": "application/json",
            "Referer": f"{base_url}/login",
        }
        try:
            user_detail_resp = context.request.get(
                f"{base_url}/api/v1/user/detail",
                headers=request_headers,
                timeout=10000,
            )
            if user_detail_resp.status == 200:
                payload = user_detail_resp.json()
                data = payload.get("data")
                if isinstance(data, dict):
                    user_detail = data
        except Exception:
            user_detail = None

        # Discover all workspace IDs via /api/v1/user/routes/default.
        # The response contains a "userWorkspaceList" route with all workspaces
        # the user can access, each with name (display name) and path (ws-... ID).
        all_workspace_ids: list[str] = []
        all_workspace_names: dict[str, str] = {}
        for routes_workspace_id in ("default",):
            try:
                routes_resp = context.request.get(
                    f"{base_url}/api/v1/user/routes/{routes_workspace_id}",
                    headers=request_headers,
                    timeout=15000,
                )
                if routes_resp.status == 200:
                    route_ids, route_names = _workspace_routes_from_payload(routes_resp.json())
                    _merge_workspace_routes(
                        all_workspace_ids,
                        all_workspace_names,
                        route_ids,
                        route_names,
                    )
            except Exception:
                pass

        workspace_id = all_workspace_ids[0] if all_workspace_ids else DEFAULT_WORKSPACE_ID

        # Capture storage state (cookies + localStorage)
        storage_state = context.storage_state()

        # Keep a simple cookie name->value mapping for debugging/back-compat
        cookies = context.cookies()
        cookie_dict = {c["name"]: c["value"] for c in cookies}

        browser.close()

        session = WebSession(
            storage_state=cast(dict[str, Any], storage_state),
            cookies=cookie_dict,
            workspace_id=workspace_id,
            login_username=username,
            base_url=base_url,
            user_detail=user_detail,
            all_workspace_ids=all_workspace_ids or None,
            all_workspace_names=all_workspace_names or None,
            created_at=time.time(),
        )
        session.save()

        return session


def get_web_session(force_refresh: bool = False, require_workspace: bool = False) -> WebSession:
    """Get a valid web session, logging in if necessary.

    Args:
        force_refresh: Force a new login even if cached session exists.
        require_workspace: Force re-login if workspace_id is missing.

    Returns:
        A valid WebSession with storage_state and optionally workspace_id.
    """
    # Resolve credentials early so we can avoid reusing a cache from another user.
    credentials_error: Optional[ValueError] = None
    try:
        username, password = get_credentials()
    except ValueError as e:
        credentials_error = e
        try:
            username = (_load_runtime_config().username or "").strip()
        except Exception:
            username = ""
        password = ""

    if not force_refresh:
        cached = WebSession.load()
        if cached and cached.storage_state.get("cookies"):
            if require_workspace and not _has_real_workspace_id(cached):
                pass
            elif username and not _session_matches_username(cached, username):
                # Credentials are available and don't match the cached login user.
                # Force fresh login so the active account follows current config.
                pass
            else:
                return cached

    # If we can't refresh (missing credentials), try the cached session anyway.
    if credentials_error is not None:
        cached = WebSession.load(allow_expired=True)
        if cached and cached.storage_state.get("cookies"):
            if require_workspace and not _has_real_workspace_id(cached):
                raise credentials_error
            return cached
        raise credentials_error

    # Use cached session if available and has cookies, even if beyond TTL.
    # The session cookies may still be valid server-side; let API calls determine validity.
    # Skip this when force_refresh is set — the caller explicitly wants a fresh login.
    if not force_refresh:
        cached = WebSession.load(allow_expired=True)
        if cached and cached.storage_state.get("cookies"):
            if (
                not require_workspace or _has_real_workspace_id(cached)
            ) and _session_matches_username(cached, username):
                # Use cached session; server will reject if truly invalid.
                return cached

    # Session is missing or has no cookies, perform fresh login
    base_url = _load_runtime_config().base_url
    return login_with_playwright(username, password, base_url=base_url)
