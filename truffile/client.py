import asyncio
import json
import platform
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator
import grpc
from grpc import aio
import httpx
from google.protobuf import empty_pb2
from truffle.os.truffleos_pb2_grpc import TruffleOSStub
from truffle.os.builder_pb2 import (
    StartBuildSessionRequest,
    StartBuildSessionResponse,
    FinishBuildSessionRequest,
    FinishBuildSessionResponse,
)
from truffle.os.client_session_pb2 import (
    RegisterNewSessionRequest,
    RegisterNewSessionResponse,
    NewSessionStatus,
)
from truffle.os.client_metadata_pb2 import ClientMetadata
from truffle.os.app_queries_pb2 import GetAllAppsRequest, GetAllAppsResponse
from truffle.app.app_type_pb2 import AppType
from truffle.app.foreground_pb2 import ForegroundApp
from truffle.app.background_pb2 import BackgroundApp, BackgroundAppRuntimePolicy
from truffile.schedule import parse_runtime_policy


def get_client_metadata() -> ClientMetadata:
    from truffile import __version__
    metadata = ClientMetadata()
    metadata.device = platform.node()
    metadata.platform = platform.platform()
    metadata.version = f"truffile-{__version__}-{platform.python_version()}"
    return metadata


async def resolve_mdns(hostname: str) -> str:
    if ".local" not in hostname:
        return hostname
    loop = asyncio.get_event_loop()
    try:
        resolved = await loop.run_in_executor(None, socket.gethostbyname, hostname)
        return resolved
    except socket.gaierror as e:
        raise RuntimeError(f"Failed to resolve {hostname} - is the device on the same network? ({e})")


@dataclass
class ExecResult:
    exit_code: int
    output: list[str]


@dataclass
class UploadResult:
    path: str
    bytes: int
    sha256: str


class TruffleClient:
    def __init__(self, address: str, token: str):
        self.address = address
        self.token = token
        self.channel: aio.Channel | None = None
        self.stub: TruffleOSStub | None = None
        self.app_uuid: str | None = None
        self.access_path: str | None = None

    @property
    def http_base(self) -> str | None:
        if not self.access_path:
            return None
        host = self.address if "://" in self.address else f"http://{self.address}"
        return f"{host}/containers/{self.access_path}"

    @property
    def _metadata(self) -> list:
        return [("session", self.token)]

    async def connect(self, timeout: float = 15.0):
        self.channel = aio.insecure_channel(self.address)
        await asyncio.wait_for(self.channel.channel_ready(), timeout=timeout)
        self.stub = TruffleOSStub(self.channel)

    def update_token(self, token: str):
        self.token = token

    async def check_auth(self) -> bool:
        if not self.stub or not self.token:
            return False
        try:
            await self.stub.System_GetInfo(empty_pb2.Empty(), metadata=self._metadata)
            return True
        except aio.AioRpcError as e:
            if e.code() == grpc.StatusCode.UNAUTHENTICATED:
                return False
            raise

    async def register_new_session(self, user_id: str) -> tuple[NewSessionStatus, str | None]:
        if not self.stub:
            raise RuntimeError("not connected")
        req = RegisterNewSessionRequest()
        req.user_id = user_id
        req.metadata.CopyFrom(get_client_metadata())
        resp: RegisterNewSessionResponse = await self.stub.Client_RegisterNewSession(req)
        if resp.status.error == NewSessionStatus.NEW_SESSION_SUCCESS:
            self.token = resp.token
            return resp.status, resp.token
        return resp.status, None

    async def get_all_apps(self) -> tuple[list[ForegroundApp], list[BackgroundApp]]:
        if not self.stub:
            raise RuntimeError("not connected")
        req = GetAllAppsRequest()
        resp: GetAllAppsResponse = await self.stub.Apps_GetAll(req, metadata=self._metadata)
        return list(resp.foreground_apps), list(resp.background_apps)

    async def start_build(self, app_type: AppType = AppType.APP_TYPE_BACKGROUND) -> StartBuildSessionResponse:
        if not self.stub:
            raise RuntimeError("not connected")
        req = StartBuildSessionRequest()
        req.app_type = app_type
        resp: StartBuildSessionResponse = await self.stub.Builder_StartBuildSession(
            req, metadata=self._metadata
        )
        self.app_uuid = resp.app_uuid
        self.access_path = resp.access_path
        return resp

    async def _sse_events(self, client: httpx.AsyncClient, url: str, body: dict) -> AsyncIterator[tuple[str, str]]:
        async with client.stream("POST", url, json=body, timeout=None) as r:
            r.raise_for_status()
            event = "message"
            data_parts = []
            async for raw in r.aiter_lines():
                if raw is None:
                    continue
                line = raw.rstrip("\r")
                if line == "":
                    if data_parts:
                        yield event, "\n".join(data_parts)
                    event, data_parts = "message", []
                    continue
                if line.startswith(":"):
                    continue
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:"):
                    data_parts.append(line[5:].lstrip())
            if data_parts:
                yield event, "\n".join(data_parts)

    async def exec(self, cmd: str, cwd: str = "/") -> ExecResult:
        if not self.http_base:
            raise RuntimeError("no active build session")
        url = f"{self.http_base}/exec/stream"
        body = {"cmd": ["bash", "-lc", f"cd {cwd} && {cmd}"], "cwd": cwd}
        output = []
        exit_code = 0
        retries = 5
        backoff = 1.0
        async with httpx.AsyncClient(timeout=None) as client:
            for attempt in range(retries):
                try:
                    async for ev, data in self._sse_events(client, url, body):
                        if ev == "log":
                            try:
                                obj = json.loads(data)
                                line = obj.get("line", "")
                            except Exception:
                                line = data
                            output.append(line)
                        elif ev == "exit":
                            try:
                                exit_code = int(json.loads(data).get("code", 0))
                            except Exception:
                                pass
                    return ExecResult(exit_code=exit_code, output=output)
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 503 and attempt < retries - 1:
                        await asyncio.sleep(backoff * (attempt + 1))
                        continue
                    raise
        return ExecResult(exit_code=exit_code, output=output)

    async def exec_stream(self, cmd: str, cwd: str = "/") -> AsyncIterator[tuple[str, str]]:
        if not self.http_base:
            raise RuntimeError("no active build session")
        url = f"{self.http_base}/exec/stream"
        body = {"cmd": ["bash", "-lc", f"cd {cwd} && {cmd}"], "cwd": cwd}
        retries = 5
        backoff = 1.0
        async with httpx.AsyncClient(timeout=None) as client:
            for attempt in range(retries):
                try:
                    async for ev, data in self._sse_events(client, url, body):
                        yield ev, data
                    return
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 503 and attempt < retries - 1:
                        await asyncio.sleep(backoff * (attempt + 1))
                        continue
                    raise

    async def upload(self, src: str | Path, dest: str) -> UploadResult:
        if not self.http_base:
            raise RuntimeError("no active build session")
        path = Path(src).expanduser()
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"no such file: {path}")
        url = f"{self.http_base}/upload"
        retries = 5
        backoff = 1.0
        async with httpx.AsyncClient(timeout=None) as client:
            for attempt in range(retries):
                try:
                    with path.open("rb") as fh:
                        files = {"file": (path.name, fh)}
                        r = await client.post(url, params={"path": dest}, files=files)
                    r.raise_for_status()
                    data = r.json()
                    return UploadResult(
                        path=data.get("path", ""),
                        bytes=data.get("bytes", 0),
                        sha256=data.get("sha256", ""),
                    )
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 503 and attempt < retries - 1:
                        await asyncio.sleep(backoff * (attempt + 1))
                        continue
                    raise
        raise RuntimeError("upload failed after retries")

    def _load_icon(self, icon: str | Path | bytes | None) -> bytes | None:
        if icon is None:
            return None
        if isinstance(icon, bytes):
            return icon
        path = Path(icon).expanduser()
        if path.exists() and path.is_file():
            return path.read_bytes()
        return None

    async def finish_foreground(
        self,
        name: str,
        cmd: str,
        args: list[str],
        cwd: str = "/",
        env: list[str] | None = None,
        description: str = "",
        icon: str | Path | bytes | None = None,
    ) -> FinishBuildSessionResponse:
        if not self.stub or not self.app_uuid:
            raise RuntimeError("no active build session")
        req = FinishBuildSessionRequest()
        req.app_uuid = self.app_uuid
        req.discard = False
        req.foreground.metadata.name = name
        if description:
            req.foreground.metadata.description = description
        icon_data = self._load_icon(icon)
        if icon_data:
            req.foreground.metadata.icon.png_data = icon_data
        req.process.cmd = cmd
        req.process.args.extend(args)
        if env:
            req.process.env.extend(env)
        req.process.cwd = cwd
        resp: FinishBuildSessionResponse = await self.stub.Builder_FinishBuildSession(
            req, metadata=self._metadata
        )
        self.app_uuid = None
        self.access_path = None
        if resp.HasField("error"):
            raise RuntimeError(f"finish failed: {resp.error.error} - {resp.error.details}")
        return resp

    async def finish_background(
        self,
        name: str,
        cmd: str,
        args: list[str],
        cwd: str = "/",
        env: list[str] | None = None,
        description: str = "",
        icon: str | Path | bytes | None = None,
        default_schedule: dict | None = None,
    ) -> FinishBuildSessionResponse:
        if not self.stub or not self.app_uuid:
            raise RuntimeError("no active build session")
        req = FinishBuildSessionRequest()
        req.app_uuid = self.app_uuid
        req.discard = False
        req.background.metadata.name = name
        if description:
            req.background.metadata.description = description
        icon_data = self._load_icon(icon)
        if icon_data:
            req.background.metadata.icon.png_data = icon_data
        
        if default_schedule:
            runtime_policy = parse_runtime_policy(default_schedule)
            req.background.runtime_policy.CopyFrom(runtime_policy)
        else:
            req.background.runtime_policy.interval.duration.seconds = 60
        
        req.process.cmd = cmd
        req.process.args.extend(args)
        if env:
            req.process.env.extend(env)
        req.process.cwd = cwd
        resp: FinishBuildSessionResponse = await self.stub.Builder_FinishBuildSession(
            req, metadata=self._metadata
        )
        self.app_uuid = None
        self.access_path = None
        if resp.HasField("error"):
            raise RuntimeError(f"finish failed: {resp.error.error} - {resp.error.details}")
        return resp

    async def discard(self) -> FinishBuildSessionResponse | None:
        if not self.stub or not self.app_uuid:
            return None
        req = FinishBuildSessionRequest()
        req.app_uuid = self.app_uuid
        req.discard = True
        resp: FinishBuildSessionResponse = await self.stub.Builder_FinishBuildSession(
            req, metadata=self._metadata
        )
        self.app_uuid = None
        self.access_path = None
        return resp

    async def close(self):
        if self.channel:
            await self.channel.close()
            self.channel = None
            self.stub = None

    async def __aenter__(self):
        await self.connect()
        await self.start_build()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.discard()
        await self.close()
        return False
