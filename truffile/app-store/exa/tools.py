"""Canonical foreground tool metadata for runtime registration and default-app publishing."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    title: str
    description: str
    icon: str
    annotations: dict[str, bool]


TOOLS = [
 ToolDefinition(**{'name': 'check_exa_auth',
 'title': 'Check Exa Auth',
 'description': 'Verify Exa MCP/API authentication and report selected tool availability.',
 'icon': 'heartbeat',
 'annotations': {'readOnlyHint': True, 'destructiveHint': False}}),
 ToolDefinition(**{'name': 'web_search_exa',
 'title': 'Web Search Exa',
 'description': 'Search the web for current information. Use this for straightforward lookups, recent facts, and '
                'finding relevant pages on a topic. Describe the ideal page rather than using bare keywords.\n'
                '\n'
                'Parameters:\n'
                '- query (required): natural language search query describing the ideal page.\n'
                '- num_results (optional): integer result count/page size; default 10. Exa search is not '
                'cursor-paginated in this app, so increase this modestly or refine the query/domain/date filters for '
                'more coverage.\n'
                '- include_text (optional): boolean; true asks Exa to include page text when available.\n'
                '\n'
                'Example:\n'
                'web_search_exa(query="blog post comparing React and Vue performance", num_results=5)',
 'icon': 'globe',
 'annotations': {'readOnlyHint': True, 'destructiveHint': False}}),
 ToolDefinition(**{'name': 'web_search_advanced_exa',
 'title': 'Web Search Advanced Exa',
 'description': 'Advanced web search with full control over filters, domains, date ranges, and content options. Use '
                'when you need date filtering, domain restrictions, text inclusion/exclusion, or neural search. This '
                'app exposes result count but not cursor pagination.\n'
                '\n'
                'Parameters:\n'
                '- query (required): search query string.\n'
                '- num_results (optional): integer result count/page size; default 10.\n'
                '- include_text (optional): boolean; true asks Exa to include page text when available.\n'
                "- include_domains (optional): list of allowed domains, e.g. ['openai.com', 'anthropic.com'].\n"
                '- exclude_domains (optional): list of blocked domains.\n'
                "- start_published_date (optional): ISO 8601 date lower bound, e.g. '2026-01-01'.\n"
                '- end_published_date (optional): ISO 8601 date upper bound.\n'
                '\n'
                'Example:\n'
                'web_search_advanced_exa(query="AI safety policy", include_domains=["openai.com","anthropic.com"], '
                'start_published_date="2026-01-01", num_results=5)',
 'icon': 'globe-stand',
 'annotations': {'readOnlyHint': True, 'destructiveHint': False}}),
 ToolDefinition(**{'name': 'get_code_context_exa',
 'title': 'Get Code Context Exa',
 'description': 'Search technical sources for code examples, documentation, and programming solutions. Use for library '
                'usage, API details, and coding research. Describe what you need specifically. This app exposes result '
                'count but not cursor pagination.\n'
                '\n'
                'Parameters:\n'
                "- query (required): technical search string, e.g. 'Python requests library POST with JSON body'.\n"
                '- num_results (optional): integer result count/page size; default 10.\n'
                '\n'
                'Example:\n'
                'get_code_context_exa(query="FastAPI background tasks example", num_results=5)',
 'icon': 'terminal',
 'annotations': {'readOnlyHint': True, 'destructiveHint': False}}),
 ToolDefinition(**{'name': 'crawling_exa',
 'title': 'Crawling Exa',
 'description': 'Fetch and read full page content as clean markdown from one or more URLs. Use after web_search_exa '
                'when highlights are insufficient, or to read any known URL. Batch multiple URLs in one call. If a '
                'crawl fails, retry only for transient status codes and fall back to search snippets or another source '
                'URL.\n'
                '\n'
                'Parameters:\n'
                '- url (optional): one URL string to crawl.\n'
                "- urls (optional): list of URL strings to crawl, e.g. ['https://example.com/page']. Provide url or "
                'urls.\n'
                '- max_characters (optional): integer cap on extracted text per page; use this to keep crawls '
                'bounded.\n'
                '- subpages (optional): integer number of linked subpages to also crawl from each URL.\n'
                '\n'
                'Example:\n'
                'crawling_exa(urls=["https://openai.com/index/gpt-4-1/"], max_characters=12000)',
 'icon': 'browsers',
 'annotations': {'readOnlyHint': True, 'destructiveHint': False}}),
 ToolDefinition(**{'name': 'company_research_exa',
 'title': 'Company Research Exa',
 'description': 'Legacy/deprecated company research helper. Prefer web_search_advanced_exa with explicit company name, '
                'domains, and date filters because it gives clearer result controls and source visibility.\n'
                '\n'
                'Parameters:\n'
                '- companyName (required): the name of the company to research.\n'
                '- numResults (optional): integer number of results; default 3.\n'
                '\n'
                'Example:\n'
                'company_research_exa(companyName="Stripe", numResults=3)',
 'icon': 'building-office',
 'annotations': {'readOnlyHint': True, 'destructiveHint': False}}),
 ToolDefinition(**{'name': 'people_search_exa',
 'title': 'People Search Exa',
 'description': "Legacy/deprecated people search helper. Prefer web_search_advanced_exa with the person's name, "
                'company/title terms, and trusted profile/news domains for clearer source visibility.\n'
                '\n'
                'Parameters:\n'
                '- query (required): person name or person-focused search query.\n'
                '- numResults (optional): integer number of profile results; default 5.\n'
                '\n'
                'Example:\n'
                'people_search_exa(query="Dario Amodei Anthropic CEO", numResults=3)',
 'icon': 'address-book',
 'annotations': {'readOnlyHint': True, 'destructiveHint': False}}),
 ToolDefinition(**{'name': 'deep_researcher_start',
 'title': 'Deep Researcher Start',
 'description': 'Legacy/deprecated asynchronous deep research job that searches, reads, and writes a detailed report. '
                'Prefer explicit web_search_advanced_exa plus crawling_exa when you need inspectable sources. If used, '
                'poll with deep_researcher_check using the returned researchId.\n'
                '\n'
                'Parameters:\n'
                '- instructions (required): detailed research question or instructions for the AI researcher.\n'
                "- model (optional): 'exa-research-fast' (~15s, default), 'exa-research' (15-45s), or "
                "'exa-research-pro' (45s-3min, most comprehensive).\n"
                '\n'
                'Example:\n'
                'deep_researcher_start(instructions="Compare the latest AI coding agents on autonomy, safety, and '
                'pricing", model="exa-research-fast")',
 'icon': 'binoculars',
 'annotations': {'readOnlyHint': False, 'destructiveHint': False}}),
 ToolDefinition(**{'name': 'deep_researcher_check',
 'title': 'Deep Researcher Check',
 'description': "Legacy/deprecated status checker for deep_researcher_start. Keep polling until status is 'completed', "
                'but prefer explicit search/crawl workflows for new research tasks.\n'
                '\n'
                'Parameters:\n'
                '- researchId (required): the research ID string returned by deep_researcher_start.\n'
                '\n'
                'Example:\n'
                'deep_researcher_check(researchId="r_01kmm0ny9pfx44ed2kgrknfvz2")',
 'icon': 'check',
 'annotations': {'readOnlyHint': True, 'destructiveHint': False}})
]

TOOLS_BY_NAME = {tool.name: tool for tool in TOOLS}
