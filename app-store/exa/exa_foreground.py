from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any



from truffile.app_runtime import ForegroundApp, ToolSpec, err

from exa_client import ExaRemoteClient, ExaRpcError
from exa_common import icon_url_for_tool, selected_tool_names, tool_definition


class ExaForegroundApp(ForegroundApp):
    def __init__(self, *, client: ExaRemoteClient | None = None) -> None:
        super().__init__("exa", logger_name="exa.foreground")
        self._client = client
        self._register_tools()

    def _get_client(self) -> ExaRemoteClient:
        if self._client is None:
            self._client = ExaRemoteClient()
        return self._client

    async def _call_remote_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        filtered_arguments = {key: value for key, value in arguments.items() if value is not None}
        try:
            result = await self._get_client().call_tool(name, filtered_arguments)
        except ExaRpcError as exc:
            return err(
                str(exc),
                tool=name,
                status_code=exc.status_code,
                remote_error=exc.error,
            )
        return result if isinstance(result, dict) else {"result": result}

    def _register_tools(self) -> None:
        selected = set(selected_tool_names())

        if "web_search_exa" in selected:
            definition = tool_definition("web_search_exa")

            @self.tool(
                ToolSpec(
                    name=definition.name,
                    description=definition.description,
                    icon=icon_url_for_tool(definition.name),
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
                    description=definition.description,
                    icon=icon_url_for_tool(definition.name),
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
                    description=definition.description,
                    icon=icon_url_for_tool(definition.name),
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
                    description=definition.description,
                    icon=icon_url_for_tool(definition.name),
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
                    description=definition.description,
                    icon=icon_url_for_tool(definition.name),
                )
            )
            async def company_research_exa_tool(query: str) -> dict[str, Any]:
                return await self._call_remote_tool(
                    "company_research_exa",
                    {
                        "query": query,
                    },
                )

        if "people_search_exa" in selected:
            definition = tool_definition("people_search_exa")

            @self.tool(
                ToolSpec(
                    name=definition.name,
                    description=definition.description,
                    icon=icon_url_for_tool(definition.name),
                )
            )
            async def people_search_exa_tool(
                query: str,
                company: str | None = None,
                title: str | None = None,
            ) -> dict[str, Any]:
                return await self._call_remote_tool(
                    "people_search_exa",
                    {
                        "query": query,
                        "company": company,
                        "title": title,
                    },
                )

        if "deep_researcher_start" in selected:
            definition = tool_definition("deep_researcher_start")

            @self.tool(
                ToolSpec(
                    name=definition.name,
                    description=definition.description,
                    icon=icon_url_for_tool(definition.name),
                )
            )
            async def deep_researcher_start_tool(query: str) -> dict[str, Any]:
                return await self._call_remote_tool(
                    "deep_researcher_start",
                    {
                        "query": query,
                    },
                )

        if "deep_researcher_check" in selected:
            definition = tool_definition("deep_researcher_check")

            @self.tool(
                ToolSpec(
                    name=definition.name,
                    description=definition.description,
                    icon=icon_url_for_tool(definition.name),
                )
            )
            async def deep_researcher_check_tool(task_id: str) -> dict[str, Any]:
                return await self._call_remote_tool(
                    "deep_researcher_check",
                    {
                        "task_id": task_id,
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
