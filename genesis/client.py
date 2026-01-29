import grpc
import httpx
import json
import time
from dataclasses import dataclass
from typing import Iterator
from truffle.os.truffleos_pb2_grpc import TruffleOSStub
from truffle.os.builder_pb2 import (
    StartBuildSessionRequest,
    StartBuildSessionResponse,
    FinishBuildSessionRequest,
    FinishBuildSessionResponse,
)
from truffle.app.app_type_pb2 import AppType


@dataclass
class ExecResult:
    exit_code: int
    output: list[str]


class TruffleClient:
    def __init__(self, address: str, token: str):
        self.address = address
        self.token = token
        self.channel: grpc.Channel | None = None
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

    def connect(self, timeout: float = 15.0):
        self.channel = grpc.insecure_channel(self.address)
        grpc.channel_ready_future(self.channel).result(timeout=timeout)
        self.stub = TruffleOSStub(self.channel)

    def start_build(self, app_type: AppType = AppType.APP_TYPE_BACKGROUND) -> StartBuildSessionResponse:
        if not self.stub:
            raise RuntimeError("not connected")
        req = StartBuildSessionRequest()
        req.app_type = app_type
        resp: StartBuildSessionResponse = self.stub.Builder_StartBuildSession(
            req, metadata=self._metadata
        )
        self.app_uuid = resp.app_uuid
        self.access_path = resp.access_path
        return resp

    def _parse_sse(self, response: httpx.Response) -> Iterator[tuple[str, str]]:
        event = "message"
        data_parts = []
        for raw in response.iter_lines():
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

    def exec(self, cmd: str, cwd: str = "/", stream: bool = False) -> ExecResult | Iterator[tuple[str, str]]:
        if not self.http_base:
            raise RuntimeError("no active build session")
        url = f"{self.http_base}/exec/stream"
        body = {"cmd": ["bash", "-lc", f"cd {cwd} && {cmd}"], "cwd": cwd}
        if stream:
            return self._exec_stream(url, body)
        return self._exec_collect(url, body)

    def _exec_stream(self, url: str, body: dict, retries: int = 5, backoff: float = 1.0) -> Iterator[tuple[str, str]]:
        with httpx.Client(timeout=None) as client:
            for attempt in range(retries):
                try:
                    with client.stream("POST", url, json=body) as response:
                        response.raise_for_status()
                        for ev, data in self._parse_sse(response):
                            yield ev, data
                        return
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 503 and attempt < retries - 1:
                        time.sleep(backoff * (attempt + 1))
                        continue
                    raise

    def _exec_collect(self, url: str, body: dict) -> ExecResult:
        output = []
        exit_code = 0
        for ev, data in self._exec_stream(url, body):
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

    def discard(self) -> FinishBuildSessionResponse | None:
        if not self.stub or not self.app_uuid:
            return None
        req = FinishBuildSessionRequest()
        req.app_uuid = self.app_uuid
        req.discard = True
        resp: FinishBuildSessionResponse = self.stub.Builder_FinishBuildSession(
            req, metadata=self._metadata
        )
        self.app_uuid = None
        self.access_path = None
        return resp

    def close(self):
        if self.channel:
            self.channel.close()
            self.channel = None
            self.stub = None

    def __enter__(self):
        self.connect()
        self.start_build()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.discard()
        self.close()
        return False
