import requests 
from ddgs import DDGS
from ddgs.results import TextResult, NewsResult
from typing import List
from mcp.server.fastmcp import FastMCP
from abrasive.extract import extract_content_from_url

PERPLEXITY_KEY = "you thought"
class PerplexitySearcher:
    def __init__(self, key : str = PERPLEXITY_KEY):
        self.system_prompt = "You provide concise and accurate answers to queries, aim for recent information. This is presented to another LLM which will use it to help a user. Cite sources where possible and format your answer in markdown."
        self.model = "sonar"
        self.url = "https://api.perplexity.ai/chat/completions"
        self.key = key  
    def run(self, query: str) -> str:
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": query}
        ]
        response = requests.post(
            self.url,
            json={
                "model": self.model,
                "messages": messages
            },
            headers={
                "accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.key}"
            }
        )
        return response.json()["choices"][0]["message"]["content"]

HOST = "0.0.0.0"
PORT = 8000
   
mcp = FastMCP("research", stateless_http=True,  host=HOST, port=PORT)


@mcp.tool("search_perplexity", description="Searches Perplexity AI for an answer to the given query.")
async def search_perplexity(query: str) -> str:
    searcher = PerplexitySearcher()
    result = searcher.run(query)
    return result

@mcp.tool("search_web")
async def search_web(query: str, num_results: int = 5) -> str:

    results : List[dict] = DDGS().text(query, max_results=num_results, region='us-en', safesearch='off')  # type: ignore
    formatted_results = "\n".join([f"{i+1}. {res['title']}: {res['href']}" for i, res in enumerate(results)])
    return formatted_results

@mcp.tool("search_news")
async def search_news(query: str, num_results: int = 5) -> str:
    results : List[dict] = DDGS().news(query, max_results=num_results, region='us-en', safesearch='off')  # type: ignore
    formatted_results = "\n".join([f"{i+1}. [{res['source']}] '{res['title']}': {res['body']} <{res['url']}>" for i, res in enumerate(results)])
    return formatted_results

@mcp.tool("fetch_url_content", description="Fetches and extracts the main content from a given URL. Will return text and any images found in markdown format. Some sites may block scraping.")
async def fetch_url_content(url: str) -> str:
    try:
        content = extract_content_from_url(url.strip())
        if content is None:
            return "Error: Failed to extract content from the URL. Was it valid? This site may block scraping."
        
        content_str = f"<{url}>\n\n{content.text}\n"
        if content.images:
            content_str += "\n\nImages:\n" + "\n".join(content.images)
        if content.source_name:
            content_str = f"Source: {content.source_name}\n\n" + content_str
        return content_str
    except Exception as e:
        return f"Error: Exception occurred while fetching URL: {str(e)}"
    
def main():
    print(f"Starting MCP server on {HOST}:{PORT}")
    mcp.run(transport="streamable-http")





if __name__ == "__main__":
    main()



