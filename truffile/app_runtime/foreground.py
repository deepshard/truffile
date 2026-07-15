from __future__ import annotations

from dataclasses import dataclass, field
import functools
import inspect
import logging
from types import NoneType
from typing import Any, Callable, get_args, get_origin, get_type_hints

from .errors import ErrorReporter


def _normalize_annotations(annotations: dict[str, Any] | None) -> dict[str, Any]:
    return dict(annotations or {})


# Standard URI every app uses for its user-profile resource; the firmware
# discovers it via resources/list at install time and injects the combined
# text into the agent's system prompt.
USER_INFO_RESOURCE_URI = "truffle://user-info"


def resource_link(
    uri: str,
    *,
    name: str = "",
    mime_type: str = "",
    description: str = "",
    title: str = "",
    size: int | None = None,
) -> Any:
    """Build a spec ResourceLink content block for a CallToolResult.

    Include one of these alongside the text content whenever a tool result
    references a resource the app serves (e.g. ``myapp://file/{id}``). The
    agent runtime reads linked custom-scheme resources back through this
    app's ``resources/read`` and hands the agent a local file — so large
    payloads never need to be inlined in the tool result.
    """
    from mcp.types import ResourceLink

    if not uri:
        raise ValueError("resource_link requires a uri")
    return ResourceLink(
        type="resource_link",
        uri=uri,
        name=name or uri.rsplit("/", 1)[-1] or uri,
        title=title or None,
        description=description or None,
        mimeType=mime_type or None,
        size=size,
    )


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    icon: str
    title: str | None = None
    annotations: dict[str, Any] = field(default_factory=dict)
    structured_output: bool | None = None

    def read_only(self) -> bool:
        return bool(self.annotations.get("readOnlyHint"))

    def destructive(self) -> bool:
        return bool(self.annotations.get("destructiveHint"))


@dataclass(frozen=True, slots=True)
class _ToolRegistration:
    spec: ToolSpec
    handler: Callable[..., Any]


@dataclass(frozen=True, slots=True)
class _PromptRegistration:
    name: str
    description: str
    handler: Callable[..., Any]


@dataclass(frozen=True, slots=True)
class _ResourceRegistration:
    uri: str
    name: str
    description: str
    mime_type: str
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
        self._resources: dict[str, _ResourceRegistration] = {}

    def tool(
        self,
        spec_or_name: ToolSpec | str,
        *,
        description: str | None = None,
        icon: str | None = None,
        title: str | None = None,
        annotations: dict[str, Any] | None = None,
        structured_output: bool | None = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        spec = self._normalize_tool_spec(
            spec_or_name,
            description=description,
            icon=icon,
            title=title,
            annotations=annotations,
            structured_output=structured_output,
        )

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            wrapped = self._wrap_tool(spec.name, func)
            kwargs: dict[str, Any] = {"description": spec.description}
            if spec.title:
                kwargs["title"] = spec.title
            if spec.icon:
                from mcp.types import Icon
                kwargs["icons"] = [Icon(src=spec.icon)]
            from mcp.types import ToolAnnotations
            kwargs["annotations"] = ToolAnnotations(**spec.annotations)
            if spec.structured_output is not None:
                kwargs["structured_output"] = spec.structured_output
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

    def resource(
        self,
        uri: str,
        *,
        name: str | None = None,
        description: str | None = None,
        mime_type: str | None = None,
        title: str | None = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        if not uri:
            raise ValueError("resource uri is required")
        resolved_name = name or uri

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            wrapped = self._wrap_passthrough(func)
            registered = self._mcp.resource(
                uri,
                name=resolved_name,
                title=title,
                description=description,
                mime_type=mime_type,
            )(wrapped)
            self._resources[uri] = _ResourceRegistration(
                uri=uri,
                name=resolved_name,
                description=description or "",
                mime_type=mime_type or "",
                handler=wrapped,
            )
            return registered

        return decorator

    def user_info_resource(self) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register this app's user-profile resource at the standard URI.

        The decorated handler returns markdown about the authed user — facts
        first (name, email, workspace, upcoming items), then short hints to the
        tools/skills that go deeper. The firmware reads this at install time and
        folds it into the agent's system prompt. The body is also re-read on
        demand, so handlers should serve a cached copy when fresh and scrape
        live otherwise — never assume earlier state survived a restore. The text
        is returned to consumers verbatim; any length limits belong downstream
        (storage, prompt budget), not on this API.
        """

        return self.resource(
            USER_INFO_RESOURCE_URI,
            name="user_info",
            title="User Info",
            description=(
                "Profile of the authed user as known to this app: identity "
                "facts first, then hints to tools/skills for more detail."
            ),
            mime_type="text/markdown",
        )

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
                "title": registration.spec.title or registration.spec.name,
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

    def list_resources(self) -> list[dict[str, str]]:
        return [
            {
                "uri": reg.uri,
                "name": reg.name,
                "description": reg.description,
                "mime_type": reg.mime_type,
            }
            for reg in sorted(self._resources.values(), key=lambda item: item.uri)
        ]

    def logger_names(self) -> list[str]:
        return [self.logger.name]

    def _normalize_tool_spec(
        self,
        spec_or_name: ToolSpec | str,
        *,
        description: str | None,
        icon: str | None,
        title: str | None,
        annotations: dict[str, Any] | None,
        structured_output: bool | None,
    ) -> ToolSpec:
        if isinstance(spec_or_name, ToolSpec):
            resolved_icon = self._resolve_icon(spec_or_name.icon)
            if resolved_icon != spec_or_name.icon:
                return ToolSpec(
                    name=spec_or_name.name,
                    description=spec_or_name.description,
                    icon=resolved_icon,
                    title=spec_or_name.title,
                    annotations=_normalize_annotations(spec_or_name.annotations),
                    structured_output=spec_or_name.structured_output,
                )
            return spec_or_name
        if not description:
            raise ValueError("tool description is required")
        if not icon:
            raise ValueError("tool icon is required")
        return ToolSpec(
            name=spec_or_name,
            description=description,
            icon=self._resolve_icon(icon),
            title=title,
            annotations=_normalize_annotations(annotations),
            structured_output=structured_output,
        )

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
