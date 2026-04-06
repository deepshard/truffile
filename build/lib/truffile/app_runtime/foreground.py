from __future__ import annotations

from dataclasses import dataclass
import functools
import inspect
import logging
from types import NoneType
from typing import Any, Callable, get_args, get_origin, get_type_hints

from .errors import ErrorReporter


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    icon: str
    readonly: bool = False


@dataclass(frozen=True, slots=True)
class _ToolRegistration:
    spec: ToolSpec
    handler: Callable[..., Any]


@dataclass(frozen=True, slots=True)
class _PromptRegistration:
    name: str
    description: str
    handler: Callable[..., Any]


class ForegroundApp:
    def __init__(self, name: str, *, logger_name: str | None = None) -> None:
        from app_runtime.mcp import create_mcp_server

        self.name = name
        self.logger = logging.getLogger(logger_name or f"{name}.foreground")
        self.logger.setLevel(logging.INFO)
        self._mcp = create_mcp_server(name)
        self._error_reporter = ErrorReporter(logger=self.logger, app_name=name)
        self._tools: dict[str, _ToolRegistration] = {}
        self._prompts: dict[str, _PromptRegistration] = {}

    def tool(
        self,
        spec_or_name: ToolSpec | str,
        *,
        description: str | None = None,
        icon: str | None = None,
        readonly: bool = False,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        spec = self._normalize_tool_spec(spec_or_name, description=description, icon=icon, readonly=readonly)

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            wrapped = self._wrap_tool(spec.name, func)
            kwargs: dict[str, Any] = {"description": spec.description}
            if spec.icon:
                from mcp.types import Icon
                kwargs["icons"] = [Icon(src=spec.icon)]
            if spec.readonly:
                from mcp.types import ToolAnnotations
                kwargs["annotations"] = ToolAnnotations(readOnlyHint=True)
            registered = self._mcp.tool(spec.name, **kwargs)(wrapped)
            self._tools[spec.name] = _ToolRegistration(spec=spec, handler=wrapped)
            return registered

        return decorator

    def prompt(
        self,
        name: str,
        *,
        description: str | None = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        if not description:
            raise ValueError("prompt description is required")

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            wrapped = self._wrap_passthrough(func)
            registered = self._mcp.prompt(name, description=description)(wrapped)
            self._prompts[name] = _PromptRegistration(name=name, description=description, handler=wrapped)
            return registered

        return decorator

    def run(self) -> None:
        from app_runtime.mcp import run_mcp_server

        run_mcp_server(self._mcp, self.logger)

    async def invoke_tool(self, name: str, **arguments: Any) -> Any:
        registration = self._tools.get(name)
        if registration is None:
            raise KeyError(f"Unknown tool: {name}")
        return await registration.handler(**arguments)

    async def invoke_prompt(self, name: str, **arguments: Any) -> Any:
        registration = self._prompts.get(name)
        if registration is None:
            raise KeyError(f"Unknown prompt: {name}")
        result = registration.handler(**arguments)
        if inspect.isawaitable(result):
            return await result
        return result

    def list_tools(self) -> list[dict[str, str]]:
        return [
            {
                "name": registration.spec.name,
                "description": registration.spec.description,
                "icon": registration.spec.icon,
            }
            for registration in sorted(self._tools.values(), key=lambda item: item.spec.name)
        ]

    def openai_tools(self) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        for registration in sorted(self._tools.values(), key=lambda item: item.spec.name):
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": registration.spec.name,
                        "description": registration.spec.description,
                        "parameters": self._signature_to_json_schema(registration.handler),
                    },
                }
            )
        return tools

    def list_prompts(self) -> list[dict[str, str]]:
        return [
            {"name": reg.name, "description": reg.description}
            for reg in sorted(self._prompts.values(), key=lambda item: item.name)
        ]

    def logger_names(self) -> list[str]:
        return [self.logger.name]

    def _normalize_tool_spec(
        self,
        spec_or_name: ToolSpec | str,
        *,
        description: str | None,
        icon: str | None,
        readonly: bool,
    ) -> ToolSpec:
        if isinstance(spec_or_name, ToolSpec):
            resolved_icon = self._resolve_icon(spec_or_name.icon)
            if resolved_icon != spec_or_name.icon:
                return ToolSpec(name=spec_or_name.name, description=spec_or_name.description, icon=resolved_icon, readonly=spec_or_name.readonly)
            return spec_or_name
        if not description:
            raise ValueError("tool description is required")
        if not icon:
            raise ValueError("tool icon is required")
        return ToolSpec(name=spec_or_name, description=description, icon=self._resolve_icon(icon), readonly=readonly)

    @staticmethod
    def _resolve_icon(icon: str) -> str:
        if not icon or icon.startswith("http://") or icon.startswith("https://"):
            return icon
        from .icons import phosphor_icon_url
        return phosphor_icon_url(icon)

    def _wrap_tool(self, tool_name: str, func: Callable[..., Any]) -> Callable[..., Any]:
        signature = inspect.signature(func)

        @functools.wraps(func)
        async def wrapped(*args: Any, **kwargs: Any) -> Any:
            try:
                result = func(*args, **kwargs)
                if inspect.isawaitable(result):
                    return await result
                return result
            except Exception as exc:
                await self._error_reporter.report_foreground_exception(exc, tool_name=tool_name)
                raise

        wrapped.__signature__ = signature  # type: ignore[attr-defined]
        return wrapped

    def _wrap_passthrough(self, func: Callable[..., Any]) -> Callable[..., Any]:
        signature = inspect.signature(func)

        @functools.wraps(func)
        async def wrapped(*args: Any, **kwargs: Any) -> Any:
            result = func(*args, **kwargs)
            if inspect.isawaitable(result):
                return await result
            return result

        wrapped.__signature__ = signature  # type: ignore[attr-defined]
        return wrapped

    def _signature_to_json_schema(self, func: Callable[..., Any]) -> dict[str, Any]:
        signature = inspect.signature(func)
        type_hints = get_type_hints(func)
        properties: dict[str, Any] = {}
        required: list[str] = []

        for name, param in signature.parameters.items():
            if param.kind not in (
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            ):
                continue

            annotation = type_hints.get(name, param.annotation if param.annotation is not inspect._empty else Any)
            schema = self._annotation_to_json_schema(annotation)
            properties[name] = schema
            if param.default is inspect._empty:
                required.append(name)

        out: dict[str, Any] = {
            "type": "object",
            "properties": properties,
            "additionalProperties": False,
        }
        if required:
            out["required"] = required
        return out

    def _annotation_to_json_schema(self, annotation: Any) -> dict[str, Any]:
        if annotation is Any:
            return {}

        origin = get_origin(annotation)
        args = get_args(annotation)

        if origin is None:
            return self._plain_type_schema(annotation)

        if origin in (list, tuple):
            item_annotation = args[0] if args else Any
            return {
                "type": "array",
                "items": self._annotation_to_json_schema(item_annotation),
            }

        if origin is dict:
            return {"type": "object"}

        non_none_args = [arg for arg in args if arg is not NoneType]
        if len(non_none_args) == 1 and len(non_none_args) != len(args):
            schema = self._annotation_to_json_schema(non_none_args[0])
            if not schema:
                return schema
            if "type" in schema and isinstance(schema["type"], str):
                schema = dict(schema)
                schema["type"] = [schema["type"], "null"]
            return schema

        return {}

    def _plain_type_schema(self, annotation: Any) -> dict[str, Any]:
        if annotation is str:
            return {"type": "string"}
        if annotation is int:
            return {"type": "integer"}
        if annotation is float:
            return {"type": "number"}
        if annotation is bool:
            return {"type": "boolean"}
        if annotation in (list, tuple):
            return {"type": "array"}
        if annotation is dict:
            return {"type": "object"}
        return {}
