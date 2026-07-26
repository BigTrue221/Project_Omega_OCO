# -*- coding: utf-8 -*-
"""
OCO MCP 服务器适配器
MCP Server Adapters

本模块负责将现有能力封装为符合 MCP 协议的服务器。
目前首先实现对 InternetAccess 的封装。
"""

import os
import sys
from typing import List, Dict, Any, Optional
from pathlib import Path

# 确保能导入 internet_access
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from mcp.server.fastmcp import FastMCP
    from internet_access import InternetAccess
except ImportError:
    FastMCP = None
    InternetAccess = None

class InternetMCPServer:
    """
    互联网访问 MCP 服务器封装
    """
    def __init__(self):
        if FastMCP is None:
            raise ImportError("请先安装 mcp 库")
            
        self.mcp = FastMCP("OCO_Internet_Access")
        self.internet = InternetAccess(
            timeout=30,
            max_retries=2,
            brave_api_key=os.environ.get("BRAVE_API_KEY", "")
        )
        self._setup_tools()

    def _setup_tools(self):
        """定义并注册 MCP 工具"""
        
        @self.mcp.tool()
        def search_web(query: str, max_results: int = 5) -> str:
            """使用 DuckDuckGo 搜索网络信息。"""
            return self.internet.search_duckduckgo(query, max_results=max_results)

        @self.mcp.tool()
        def search_bing(query: str, max_results: int = 5) -> str:
            """使用 Bing 搜索网络信息。"""
            return self.internet.search_bing(query, max_results=max_results)

        @self.mcp.tool()
        def search_brave(query: str, max_results: int = 5) -> str:
            """使用 Brave Search API 搜索网络信息。"""
            return self.internet.search_brave(query, max_results=max_results)

        @self.mcp.tool()
        def fetch_url(url: str) -> str:
            """获取指定 URL 的内容。"""
            return self.internet.fetch_url(url)

    def run(self):
        """启动服务器"""
        self.mcp.run()

if __name__ == "__main__":
    print("Initializing server", file=sys.stderr)
    server = InternetMCPServer()
    print("Running server", file=sys.stderr)
    server.run()
    print("Server stopped", file=sys.stderr)