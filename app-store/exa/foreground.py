from __future__ import annotations

import argparse
import asyncio
import functools
import inspect
import sys
from typing import Any, Callable



from mcp.types import CallToolResult, TextContent
from truffile.app_runtime import ForegroundApp, ToolSpec, err
from truffile.app_runtime.icons import phosphor_icon_url

from exa_client import ExaRemoteClient, ExaRpcError
from exa_common import icon_url_for_tool, selected_tool_names, tool_definition
from tools import TOOLS_BY_NAME


def _text_result(
    text: str,
    *,
    structured: dict[str, Any] | None = None,
    is_error: bool = False,
) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=text.strip() or "Exa returned no visible details.")],
        structuredContent=structured or None,
        isError=is_error,
    )


def _exa_content_text(payload: dict[str, Any]) -> str:
    content = payload.get("content")
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text" and item.get("text"):
                parts.append(str(item["text"]))
            elif hasattr(item, "text"):
                parts.append(str(getattr(item, "text")))
        if parts:
            return "\n\n".join(parts)
    return ""


def _result_row(item: dict[str, Any]) -> str:
    title = item.get("title") or item.get("name") or item.get("url") or item.get("id") or "result"
    details = []
    for key in ("url", "author", "publishedDate", "score", "id"):
        if item.get(key) not in (None, ""):
            details.append(f"{key}={item[key]}")
    return f"- {title}" + (f" ({'; '.join(details[:4])})" if details else "")


def _format_exa_text(tool_name: str, payload: dict[str, Any]) -> str:
    content_text = _exa_content_text(payload)
    if content_text:
        return content_text
    lines = [f"### Exa {tool_name}"]
    message = payload.get("message")
    if isinstance(message, str) and message.strip():
        lines.append(message.strip())
    for key in ("results", "contents", "citations"):
        value = payload.get(key)
        if isinstance(value, list):
            lines.append(f"{key.title()}:")
            for item in value[:8]:
                lines.append(_result_row(item) if isinstance(item, dict) else f"- {item}")
            if len(value) > 8:
                lines.append(f"- ... {len(value) - 8} more")
    for key in ("authenticated", "status_code", "retryable", "retry_after_seconds", "researchId", "task_id"):
        if payload.get(key) not in (None, ""):
            lines.append(f"{key}: {payload[key]}")
    return "\n".join(line for line in lines if line)


def _format_exa_result(tool_name: str, payload: Any) -> CallToolResult:
    if isinstance(payload, CallToolResult):
        return payload
    if not isinstance(payload, dict):
        return _text_result(f"### Exa {tool_name}\n{payload}")
    is_error = bool(payload.get("isError")) or payload.get("status") == "error"
    structured = {
        key: value
        for key, value in payload.items()
        if key not in {"status", "message", "tool", "content", "isError"}
    }
    metadata = structured.get("exa_metadata")
    if isinstance(metadata, dict) and "tool" in metadata:
        structured["exa_metadata"] = {key: value for key, value in metadata.items() if key != "tool"}
    return _text_result(
        _format_exa_text(tool_name, payload),
        structured=structured,
        is_error=is_error,
    )


def _tool_spec(name: str) -> ToolSpec:
    tool = TOOLS_BY_NAME[name]
    supported = set(inspect.signature(ToolSpec).parameters)
    kwargs: dict[str, Any] = {
        "name": tool.name,
        "title": tool.title,
        "description": tool.description,
        "icon": phosphor_icon_url(tool.icon),
        "annotations": dict(tool.annotations),
    }
    if "structured_output" in supported:
        kwargs["structured_output"] = False
    return ToolSpec(**kwargs)


class ExaForegroundApp(ForegroundApp):
    def __init__(self, *, client: ExaRemoteClient | None = None) -> None:
        super().__init__("exa", logger_name="exa.foreground")
        self._client = client
        self._register_tools()
        self._register_user_info_resource()

    def _get_client(self) -> ExaRemoteClient:
        if self._client is None:
            self._client = ExaRemoteClient()
        return self._client

    def _register_user_info_resource(self) -> None:
        @self.user_info_resource()
        async def exa_user_info() -> str:
            client = self._get_client()
            lines = ["# Exa", f"Account: API key connected ({client.masked_api_key})"]
            try:
                tools = await client.list_tools()
                names = sorted(
                    str(tool.get("name"))
                    for tool in tools
                    if isinstance(tool, dict) and isinstance(tool.get("name"), str)
                )
            except Exception:
                names = list(selected_tool_names())
            if names:
                shown = ", ".join(names[:8])
                extra = f" (+{len(names) - 8} more)" if len(names) > 8 else ""
                lines.append(f"Tools: {len(names)} available ({shown}{extra})")
            lines.append("More: use web_search_exa / research / crawl.")
            return "\n".join(lines)

    def _wrap_tool(self, tool_name: str, func: Callable[..., Any]) -> Callable[..., Any]:
        wrapped = super()._wrap_tool(tool_name, func)

        @functools.wraps(func)
        async def formatted(*args: Any, **kwargs: Any) -> CallToolResult:
            return _format_exa_result(tool_name, await wrapped(*args, **kwargs))

        formatted.__signature__ = inspect.signature(func).replace(return_annotation=Any)  # type: ignore[attr-defined]
        return formatted

    async def _call_remote_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        filtered_arguments = {key: value for key, value in arguments.items() if value is not None}
        try:
            result = await self._get_client().call_tool(name, filtered_arguments)
        except ExaRpcError as exc:
            retryable = _is_retryable_exa_error(exc)
            return err(
                str(exc),
                tool=name,
                status_code=exc.status_code,
                remote_error=exc.error,
                retryable=retryable,
                retry_after_seconds=exc.retry_after_seconds,
                retry_guidance=_retry_guidance(name, exc),
            )
        payload = result if isinstance(result, dict) else {"result": result}
        payload.setdefault("exa_metadata", _exa_tool_metadata(name, filtered_arguments))
        return payload

    def _register_tools(self) -> None:
        selected = set(selected_tool_names())

        @self.tool(
            _tool_spec("check_exa_auth")
        )
        async def check_exa_auth_tool() -> dict[str, Any]:
            try:
                ok, message = await self._get_client().verify()
                return {
                    "status": "success" if ok else "error",
                    "authenticated": ok,
                    "message": message,
                    "health": {
                        "mcp_initialize": ok,
                        "api_key_masked": self._get_client().masked_api_key,
                        "selected_tools": selected_tool_names(),
                    },
                }
            except Exception as exc:
                return err(
                    f"Exa auth check failed: {exc}",
                    tool="check_exa_auth",
                    authenticated=False,
                    retryable=False,
                )

        if "web_search_exa" in selected:
            definition = tool_definition("web_search_exa")

            @self.tool(
                ToolSpec(
                    name=definition.name,
                    title=definition.title,
                    description=definition.description,
                    icon=icon_url_for_tool(definition.name),
                    annotations=definition.annotations,
                )
            )
            async def web_search_exa_tool(
                query: str,
                num_results: int = 10,
                include_text: bool = False,
            ) -> dict[str, Any]:
                return await self._call_remote_tool(
                    "web_search_exa",
                    {
                        "query": query,
                        "num_results": num_results,
                        "include_text": include_text,
                    },
                )

        if "web_search_advanced_exa" in selected:
            definition = tool_definition("web_search_advanced_exa")

            @self.tool(
                ToolSpec(
                    name=definition.name,
                    title=definition.title,
                    description=definition.description,
                    icon=icon_url_for_tool(definition.name),
                    annotations=definition.annotations,
                )
            )
            async def web_search_advanced_exa_tool(
                query: str,
                num_results: int = 10,
                include_text: bool = False,
                include_domains: list[str] | None = None,
                exclude_domains: list[str] | None = None,
                start_published_date: str | None = None,
                end_published_date: str | None = None,
            ) -> dict[str, Any]:
                return await self._call_remote_tool(
                    "web_search_advanced_exa",
                    {
                        "query": query,
                        "num_results": num_results,
                        "include_text": include_text,
                        "include_domains": include_domains,
                        "exclude_domains": exclude_domains,
                        "start_published_date": start_published_date,
                        "end_published_date": end_published_date,
                    },
                )

        if "get_code_context_exa" in selected:
            definition = tool_definition("get_code_context_exa")

            @self.tool(
                ToolSpec(
                    name=definition.name,
                    title=definition.title,
                    description=definition.description,
                    icon=icon_url_for_tool(definition.name),
                    annotations=definition.annotations,
                )
            )
            async def get_code_context_exa_tool(
                query: str,
                num_results: int = 10,
            ) -> dict[str, Any]:
                return await self._call_remote_tool(
                    "get_code_context_exa",
                    {
                        "query": query,
                        "num_results": num_results,
                    },
                )

        if "crawling_exa" in selected:
            definition = tool_definition("crawling_exa")

            @self.tool(
                ToolSpec(
                    name=definition.name,
                    title=definition.title,
                    description=definition.description,
                    icon=icon_url_for_tool(definition.name),
                    annotations=definition.annotations,
                )
            )
            async def crawling_exa_tool(
                url: str | None = None,
                urls: list[str] | None = None,
                subpages: int | None = None,
                max_characters: int | None = None,
            ) -> dict[str, Any]:
                request_urls = list(urls or [])
                if url:
                    request_urls.append(url)
                if not request_urls:
                    return err("Provide url or urls for crawling_exa", tool="crawling_exa")
                return await self._call_remote_tool(
                    "crawling_exa",
                    {
                        "urls": request_urls,
                        "subpages": subpages,
                        "max_characters": max_characters,
                    },
                )

        if "company_research_exa" in selected:
            definition = tool_definition("company_research_exa")

            @self.tool(
                ToolSpec(
                    name=definition.name,
                    title=definition.title,
                    description=definition.description,
                    icon=icon_url_for_tool(definition.name),
                    annotations=definition.annotations,
                )
            )
            async def company_research_exa_tool(companyName: str, numResults: int = 3) -> dict[str, Any]:
                return await self._call_remote_tool(
                    "company_research_exa",
                    {
                        "companyName": companyName,
                        "numResults": numResults,
                    },
                )

        if "people_search_exa" in selected:
            definition = tool_definition("people_search_exa")

            @self.tool(
                ToolSpec(
                    name=definition.name,
                    title=definition.title,
                    description=definition.description,
                    icon=icon_url_for_tool(definition.name),
                    annotations=definition.annotations,
                )
            )
            async def people_search_exa_tool(
                query: str,
                company: str | None = None,
                title: str | None = None,
                numResults: int = 5,
            ) -> dict[str, Any]:
                return await self._call_remote_tool(
                    "people_search_exa",
                    {
                        "query": query,
                        "company": company,
                        "title": title,
                        "numResults": numResults,
                    },
                )

        if "deep_researcher_start" in selected:
            definition = tool_definition("deep_researcher_start")

            @self.tool(
                ToolSpec(
                    name=definition.name,
                    title=definition.title,
                    description=definition.description,
                    icon=icon_url_for_tool(definition.name),
                    annotations=definition.annotations,
                )
            )
            async def deep_researcher_start_tool(
                instructions: str,
                model: str = "exa-research-fast",
            ) -> dict[str, Any]:
                return await self._call_remote_tool(
                    "deep_researcher_start",
                    {
                        "instructions": instructions,
                        "model": model,
                    },
                )

        if "deep_researcher_check" in selected:
            definition = tool_definition("deep_researcher_check")

            @self.tool(
                ToolSpec(
                    name=definition.name,
                    title=definition.title,
                    description=definition.description,
                    icon=icon_url_for_tool(definition.name),
                    annotations=definition.annotations,
                )
            )
            async def deep_researcher_check_tool(researchId: str) -> dict[str, Any]:
                return await self._call_remote_tool(
                    "deep_researcher_check",
                    {
                        "researchId": researchId,
                    },
                )


async def _verify_async() -> int:
    try:
        client = ExaRemoteClient()
    except Exception as exc:
        print(f"Exa verification failed: {exc}", flush=True)
        return 1

    try:
        ok, message = await client.verify()
    except Exception as exc:
        print(f"Exa verification failed: {exc}", flush=True)
        await client.close()
        return 1

    await client.close()
    print(message, flush=True)
    return 0 if ok else 1


def verify() -> int:
    return asyncio.run(_verify_async())


def _is_retryable_exa_error(exc: ExaRpcError) -> bool:
    if exc.status_code in {408, 409, 425, 429}:
        return True
    if exc.status_code is not None and 500 <= exc.status_code < 600:
        return True
    text = str(exc).lower()
    return any(token in text for token in ("timeout", "temporarily", "rate limit", "too many requests"))


def _retry_guidance(name: str, exc: ExaRpcError) -> dict[str, Any]:
    retryable = _is_retryable_exa_error(exc)
    guidance = {
        "retryable": retryable,
        "retry_after_seconds": exc.retry_after_seconds,
        "next_action": "do not retry automatically; adjust the request or check auth",
    }
    if retryable:
        guidance["next_action"] = "retry once after retry_after_seconds or a short exponential backoff"
    if name == "crawling_exa":
        guidance["fallbacks"] = [
            "retry with lower subpages or max_characters",
            "crawl a canonical/article URL instead of a homepage",
            "fall back to web_search_advanced_exa snippets or another source URL",
        ]
    return guidance


def _exa_tool_metadata(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "tool": name,
        "result_controls": {},
        "retryability": {
            "transient_status_codes": [408, 409, 425, 429, 500, 502, 503, 504],
            "crawler_fallback": name == "crawling_exa",
        },
    }
    if name in {"web_search_exa", "web_search_advanced_exa", "get_code_context_exa"}:
        metadata["result_controls"] = {
            "num_results_requested": arguments.get("num_results"),
            "cursor_pagination_supported": False,
            "pagination_guidance": "increase num_results modestly or refine query/domain/date filters",
        }
    if name == "crawling_exa":
        metadata["result_controls"] = {
            "url_count": len(arguments.get("urls") or []),
            "max_characters_per_page": arguments.get("max_characters"),
            "subpages": arguments.get("subpages"),
        }
    return metadata


app = ExaForegroundApp()


def main() -> int:
    parser = argparse.ArgumentParser(description="Exa foreground app")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify EXA_API_KEY by calling initialize + tools/list on Exa MCP.",
    )
    args = parser.parse_args()
    if args.verify:
        return verify()
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
