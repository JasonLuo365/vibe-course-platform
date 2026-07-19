import os
import sys
from importlib.metadata import version

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("vibe-submit-spike")


@mcp.tool()
def ping() -> str:
    """健康检查：返回版本与 Python 版本"""
    return f"pong v{version('vibe-submit')} python={sys.version.split()[0]}"


@mcp.tool()
def env_check(name: str) -> str:
    """报告指定环境变量是否存在于 MCP server 进程"""
    return f"{name}={'SET' if name in os.environ else 'MISSING'}"


def main():
    mcp.run()
