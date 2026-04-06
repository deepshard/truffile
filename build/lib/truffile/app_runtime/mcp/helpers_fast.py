from mcp.server.fastmcp import FastMCP
from .config import TRUFFLE_MCP_HOST, TRUFFLE_MCP_PORT, TRUFFLE_MCP_TRANSPORT
import logging
def create_mcp_server(name : str, **kwargs) -> FastMCP:
    return FastMCP(name, stateless_http=True, host=TRUFFLE_MCP_HOST, port=TRUFFLE_MCP_PORT, **kwargs)

def run_mcp_server(mcp: FastMCP, logger : logging.Logger | None ) -> None:
    if logger:
        logger.info(f"Starting {TRUFFLE_MCP_TRANSPORT} MCP server on {TRUFFLE_MCP_HOST}:{TRUFFLE_MCP_PORT}")
    try:
        mcp.run(transport=TRUFFLE_MCP_TRANSPORT)
    except KeyboardInterrupt:
        if logger: logger.info("MCP server stopped by KeyboardInterrupt")
    except Exception as e:
        if logger: logger.exception(f"Error running MCP server: {e}")
    