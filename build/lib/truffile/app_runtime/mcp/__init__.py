import logging
from .config import TRUFFLE_MCP_TRANSPORT, TRUFFLE_MCP_HOST, TRUFFLE_MCP_PORT
try:
    from mcp.server.fastmcp import FastMCP
    from .helpers_fast import create_mcp_server, run_mcp_server
    
except ImportError as e:
    try: # feb 2026/v1.26.0: looks like next version of MCP will have FastMCP removed, so fall back to MCPServer if FastMCP is not found
        from mcp.server.mcpserver import MCPServer # type: ignore
        from .helpers_mcp import create_mcp_server, run_mcp_server
    except ImportError as e2:
        raise ImportError("Neither FastMCP nor MCPServer could be imported. Please ensure the MCP library is installed and up to date.") from e2



