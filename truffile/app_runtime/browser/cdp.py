from __future__ import annotations

import asyncio
import contextlib
import socket
import time
from pathlib import Path
from typing import Any, Callable

import httpx


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return int(sock.getsockname()[1])


class ChromiumCDPBrowser:
    def __init__(
        self,
        *,
        browser_binary: str,
        user_data_dir: str | Path,
        start_url: str,
        window_size: tuple[int, int] = (1920, 1080),
    ) -> None:
        self.browser_binary = browser_binary
        self.user_data_dir = Path(user_data_dir)
        self.start_url = start_url
        self.window_size = window_size

        self.debug_port = _find_free_port()
        self._proc: asyncio.subprocess.Process | None = None
        self._cdp_client: Any = None
        self._session_id: str | None = None
        self._target_id: str | None = None
        self._page_crashed = False
        self._request_callback_registered = False

    @property
    def process(self) -> asyncio.subprocess.Process | None:
        return self._proc

    @property
    def page_crashed(self) -> bool:
        return self._page_crashed

    async def start(self) -> None:
        self.user_data_dir.mkdir(parents=True, exist_ok=True)
        self._clean_profile_locks()

        launch_args = self._build_launch_args()
        launch_args.append(f"--remote-debugging-port={self.debug_port}")
        launch_args.append("--remote-debugging-address=127.0.0.1")

        self._proc = await asyncio.create_subprocess_exec(
            *launch_args,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )

        debugger_url = await self._wait_for_debugger_url()

        from cdp_use import CDPClient

        self._cdp_client = CDPClient(debugger_url, max_ws_frame_size=50 * 1024 * 1024)
        await self._cdp_client.start()

        def _on_target_crashed(event: dict, session_id: str | None = None) -> None:
            self._page_crashed = True

        self._cdp_client.register.Target.targetCrashed(_on_target_crashed)
        await self._attach_page_target()

    async def close(self) -> None:
        if self._cdp_client is not None:
            with contextlib.suppress(Exception):
                await self._cdp_client.stop()
            self._cdp_client = None
        if self._proc is not None:
            if self._proc.returncode is None:
                self._proc.terminate()
                try:
                    await asyncio.wait_for(self._proc.wait(), timeout=3.0)
                except TimeoutError:
                    with contextlib.suppress(ProcessLookupError):
                        self._proc.kill()
                    with contextlib.suppress(Exception):
                        await self._proc.wait()
            self._proc = None

    def is_alive(self) -> bool:
        if self._page_crashed:
            return False
        return self._proc is not None and self._proc.returncode is None

    async def navigate(self, url: str) -> None:
        assert self._cdp_client is not None and self._session_id is not None
        await self._cdp_client.send.Page.navigate(params={"url": url}, session_id=self._session_id)

    async def evaluate(self, expression: str) -> Any:
        assert self._cdp_client is not None and self._session_id is not None
        result = await self._cdp_client.send.Runtime.evaluate(
            params={"expression": expression, "returnByValue": True, "awaitPromise": True},
            session_id=self._session_id,
        )
        if "exceptionDetails" in result:
            raise RuntimeError(f"Runtime.evaluate failed: {result['exceptionDetails']}")
        return result.get("result", {}).get("value")

    async def current_url(self) -> str:
        return str(await self.evaluate("window.location.href") or "")

    async def title(self) -> str:
        return str(await self.evaluate("document.title") or "")

    async def ready_state(self) -> str:
        return str(await self.evaluate("document.readyState") or "")

    async def get_cookies(self) -> list[dict[str, Any]]:
        assert self._cdp_client is not None and self._session_id is not None
        result = await self._cdp_client.send.Storage.getCookies(session_id=self._session_id)
        return list(result.get("cookies", []) or [])

    async def get_user_agent(self) -> str:
        return str(await self.evaluate("navigator.userAgent") or "")

    async def get_language(self) -> str:
        return str(await self.evaluate("navigator.language || 'en-US'") or "en-US")

    async def capture_matching_requests(
        self,
        *,
        duration: float,
        should_capture: Callable[[str], bool],
        on_capture: Callable[..., None],
        source: str = "cdp",
        include_post_data: bool = False,
    ) -> int:
        if duration <= 0:
            return 0
        assert self._cdp_client is not None
        assert self._session_id is not None

        captured = 0

        def _on_request(params: Any, session_id: str | None = None) -> None:
            nonlocal captured
            if session_id and session_id != self._session_id:
                return
            request = params.get("request", {}) if hasattr(params, "get") else {}
            url = str(request.get("url") or "")
            if not should_capture(url):
                return
            method = str(request.get("method") or "GET").upper()
            if method == "OPTIONS":
                return
            headers_raw = request.get("headers") or {}
            headers = {str(k): str(v) for k, v in headers_raw.items()} if isinstance(headers_raw, dict) else {}
            post_data = str(request.get("postData") or "")
            if include_post_data:
                on_capture(method, url, headers, post_data, source)
            else:
                on_capture(method, url, headers, source)
            captured += 1

        if not self._request_callback_registered:
            self._cdp_client.register.Network.requestWillBeSent(_on_request)
            self._request_callback_registered = True

        await asyncio.sleep(duration)
        return captured

    def _clean_profile_locks(self) -> None:
        for pattern in ("Singleton*", "lockfile"):
            for path in self.user_data_dir.glob(pattern):
                with contextlib.suppress(Exception):
                    path.unlink()

    def _build_launch_args(self) -> list[str]:
        width, height = self.window_size
        return [
            self.browser_binary,
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-infobars",
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--test-type",
            "--disable-gpu",
            "--disable-software-rasterizer",
            f"--window-size={width},{height}",
            "--start-fullscreen",
            f"--app={self.start_url}",
            f"--user-data-dir={self.user_data_dir}",
        ]

    async def _wait_for_debugger_url(self, timeout_seconds: float = 10.0) -> str:
        deadline = time.monotonic() + timeout_seconds
        version_url = f"http://127.0.0.1:{self.debug_port}/json/version"

        async with httpx.AsyncClient(timeout=1.0) as client:
            while time.monotonic() < deadline:
                if self._proc is not None and self._proc.returncode is not None:
                    raise RuntimeError(f"Chromium exited early with code {self._proc.returncode}")
                try:
                    response = await client.get(version_url)
                    response.raise_for_status()
                    payload = response.json()
                    debugger_url = str(payload.get("webSocketDebuggerUrl") or "").strip()
                    if debugger_url:
                        return debugger_url
                except Exception:
                    pass
                await asyncio.sleep(0.2)

        raise RuntimeError("Timed out waiting for Chromium CDP endpoint")

    async def _attach_page_target(self) -> None:
        assert self._cdp_client is not None
        target_id = await self._choose_target_id()
        attach_result = await self._cdp_client.send.Target.attachToTarget(
            params={"targetId": target_id, "flatten": True}
        )
        self._target_id = target_id
        self._session_id = attach_result["sessionId"]
        await asyncio.gather(
            self._cdp_client.send.Page.enable(session_id=self._session_id),
            self._cdp_client.send.Runtime.enable(session_id=self._session_id),
            self._cdp_client.send.Network.enable(session_id=self._session_id),
        )

    async def _choose_target_id(self) -> str:
        assert self._cdp_client is not None
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            targets_result = await self._cdp_client.send.Target.getTargets()
            target_infos = list(targets_result.get("targetInfos", []) or [])
            page_targets = [
                t for t in target_infos
                if t.get("type") in {"page", "tab"}
                and not str(t.get("url") or "").startswith("devtools://")
                and not str(t.get("url") or "").startswith("chrome-extension://")
            ]
            if page_targets:
                chosen = next((t for t in page_targets if self._target_matches_start_url(t)), page_targets[0])
                return str(chosen["targetId"])
            await asyncio.sleep(0.1)

        created = await self._cdp_client.send.Target.createTarget(params={"url": self.start_url})
        return str(created["targetId"])

    def _target_matches_start_url(self, target: dict[str, Any]) -> bool:
        url = str(target.get("url") or "").lower()
        return self.start_url.lower().split("/", 3)[2] in url if "://" in self.start_url else self.start_url.lower() in url
