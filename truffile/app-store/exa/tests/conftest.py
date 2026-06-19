import sys
from pathlib import Path
import os
import types


# add app dir to sys.path for local imports
_app_dir = Path(__file__).resolve().parent.parent
if str(_app_dir) not in sys.path:
    sys.path.insert(0, str(_app_dir))

def install_stub_modules() -> None:
    if os.getenv("APP_STORE_USE_TEST_STUBS") != "1":
        return None

    fake_client_mod = types.ModuleType("exa_client")

    class ExaRpcError(RuntimeError):
        def __init__(
            self,
            message: str,
            *,
            status_code: int | None = None,
            error: dict[str, object] | None = None,
            raw: str | None = None,
        ) -> None:
            super().__init__(message)
            self.status_code = status_code
            self.error = error or {}
            self.raw = raw or ""

    class ExaRemoteClient:
        def __init__(self, **_: object) -> None:
            self.masked_api_key = "exa_...stub"

        async def close(self) -> None:
            return None

        async def verify(self) -> tuple[bool, str]:
            return True, "stub verify ok"

        async def list_tools(self) -> list[dict[str, object]]:
            return [{"name": "web_search_exa"}]

        async def call_tool(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
            if name == "deep_researcher_start":
                return {"task_id": "exa-task-stub", "status": "started"}
            if name == "deep_researcher_check":
                return {"task_id": arguments.get("task_id", "exa-task-stub"), "status": "completed"}
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"stubbed {name} result for {arguments}",
                    }
                ],
                "isError": False,
            }

    fake_client_mod.ExaRemoteClient = ExaRemoteClient
    fake_client_mod.ExaRpcError = ExaRpcError
    sys.modules["exa_client"] = fake_client_mod
    return None


install_stub_modules()
