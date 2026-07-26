# -*- coding: utf-8 -*-
"""
OCO MCP Client Implementation
感知层标准化接口 - MCP 客户端实现

使用官方 mcp 库的异步实现
"""

import asyncio
import logging
import os
import time
import json
import hashlib
from typing import Dict, Any, Optional, List
from pathlib import Path
from dataclasses import dataclass

import sys

# 避免本地的 mcp 目录与 pip 安装的 mcp 库冲突（Name Shadowing）
# 临时从 sys.path 中移除项目目录，确保 import mcp 能加载到真实的库
old_path = sys.path.copy()
sys.path = [p for p in sys.path if not p.endswith('Project_Omega_OCO') and not p.endswith('AI_Ori') and p != '']

# 导入官方 mcp 库
try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    MCP_AVAILABLE = True
except ImportError as e:
    MCP_AVAILABLE = False
    logging.warning(f"mcp 库未安装，使用降级模式: {e}")
finally:
    sys.path = old_path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("OCO_MCPClient")


import json
import hashlib
@dataclass
class MCPTool:
    name: str
    description: str
    inputSchema: Dict[str, Any]


@dataclass
class MCPServerConfig:
    name: str
    command: str
    args: List[str]
    env: Optional[Dict[str, str]] = None


class OCO_MCPClient:
    """使用官方 mcp 库的 MCP 客户端实现"""
    
    def __init__(self, enable_cache: bool = True, cache_ttl: int = 300):
        self.servers: Dict[str, Any] = {}
        self.sessions: Dict[str, ClientSession] = {}
        self.contexts: Dict[str, Any] = {}
        self.server_configs: Dict[str, MCPServerConfig] = {}
        self.available_tools: Dict[str, MCPTool] = {}
        self.tool_to_server: Dict[str, str] = {}
        self.enable_cache = enable_cache
        self.cache_ttl = cache_ttl
        self.tool_cache: Dict[str, tuple] = {}

    async def add_server(self, config: MCPServerConfig, timeout: float = 15.0):
        """连接到 MCP 服务器"""
        logger.info(f"正在连接到 MCP 服务器：{config.name}...")

        if not MCP_AVAILABLE:
            logger.error("mcp 库未安装，无法连接服务器")
            return False

        try:
            # 准备环境变量
            full_env = {**os.environ, **(config.env or {})}
            full_env["PYTHONUNBUFFERED"] = "1"
            
            # 创建 stdio 服务器参数
            server_params = StdioServerParameters(
                command=config.command,
                args=config.args,
                env=full_env
            )

            ctx = stdio_client(server_params)
            
            try:
                read, write = await ctx.__aenter__()
                session = ClientSession(read, write)
                await session.__aenter__()
                
                # 初始化会话
                await session.initialize()
                
                # 存储会话和上下文
                self.sessions[config.name] = session
                self.contexts[config.name] = ctx
                self.server_configs[config.name] = config

                # 获取可用工具
                tools_result = await session.list_tools()
                for tool in tools_result.tools:
                    mcp_tool = MCPTool(
                        name=tool.name,
                        description=tool.description or "",
                        inputSchema=tool.inputSchema
                    )
                    self.available_tools[tool.name] = mcp_tool
                    self.tool_to_server[tool.name] = config.name
                    logger.info(f"发现工具：{tool.name} (来自服务器：{config.name})")

                logger.info(f"✅ 服务器 {config.name} 连接成功")
                return True
                
            except BaseException as e:
                # 若抛出异常，清理可能已打开的上下文
                if hasattr(self, 'sessions') and config.name in self.sessions:
                    try:
                        session_to_close = self.sessions.pop(config.name)
                        await session_to_close.__aexit__(None, None, None)
                    except Exception:
                        pass
                if hasattr(self, 'contexts') and config.name in self.contexts:
                    self.contexts.pop(config.name)
                try:
                    await ctx.__aexit__(None, None, None)
                except Exception:
                    pass
                raise e

        except asyncio.TimeoutError:
            logger.error(f"❌ 连接服务器 {config.name} 超时（{timeout}秒）")
            return False
        except asyncio.CancelledError:
            logger.error(f"❌ 连接服务器 {config.name} 被取消")
            return False
        except Exception as e:
            logger.error(f"❌ 连接服务器 {config.name} 失败：{type(e).__name__}: {e}")
            return False

    def _get_cache_key(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        args_str = json.dumps(arguments, sort_keys=True)
        return f"{tool_name}:{hashlib.md5(args_str.encode()).hexdigest()}"

    def _get_cached_result(self, cache_key: str) -> Optional[str]:
        if not self.enable_cache:
            return None
        if cache_key in self.tool_cache:
            result, timestamp = self.tool_cache[cache_key]
            if time.time() - timestamp < self.cache_ttl:
                return result
            else:
                del self.tool_cache[cache_key]
        return None

    def _cache_result(self, cache_key: str, result: str):
        if self.enable_cache:
            self.tool_cache[cache_key] = (result, time.time())

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any] = None) -> str:
        """调用工具"""
        if tool_name not in self.available_tools:
            raise ValueError(f"未知工具：{tool_name}")

        server_name = self.tool_to_server.get(tool_name)
        if not server_name or server_name not in self.sessions:
            raise ValueError(f"工具 {tool_name} 的服务器 {server_name} 未连接")

        # 检查缓存
        cache_key = ""
        if arguments:
            # 序列化字典生成 cache_key
            try:
                cache_key = f"{tool_name}_{hashlib.md5(json.dumps(arguments, sort_keys=True).encode()).hexdigest()}"
                cached = self._get_cached_result(cache_key)
                if cached:
                    logger.info(f"使用缓存结果：{tool_name}")
                    return cached
            except Exception as e:
                logger.warning(f"无法生成 cache key: {e}")

        session = self.sessions[server_name]
        try:
            result = await session.call_tool(tool_name, arguments or {})
        except Exception as e:
            logger.error(f"调用工具 {tool_name} 失败: {e}")
            raise

        # 提取文本内容
        text_result = ""
        if hasattr(result, 'content'):
            for content in result.content:
                if hasattr(content, 'text'):
                    text_result += content.text
        else:
            text_result = str(result)
            
        if cache_key:
            self._cache_result(cache_key, text_result)
        return text_result

    def get_available_tools(self) -> Dict[str, MCPTool]:
        return self.available_tools.copy()

    def get_tool(self, tool_name: str) -> Optional[MCPTool]:
        return self.available_tools.get(tool_name)

    def get_server_tools(self, server_name: str) -> List[MCPTool]:
        return [t for name, t in self.available_tools.items() if self.tool_to_server.get(name) == server_name]

    def list_servers(self) -> List[str]:
        return list(self.sessions.keys())

    def is_connected(self, server_name: str = None) -> bool:
        if server_name:
            return server_name in self.sessions
        return len(self.sessions) > 0

    async def disconnect_all(self):
        """断开所有连接 - 使用显式调用 __aexit__"""
        logger.info("正在断开所有 MCP 服务器连接...")
        
        for server_name in list(self.sessions.keys()):
            session = self.sessions.pop(server_name)
            ctx = self.contexts.pop(server_name, None)
            try:
                await session.__aexit__(None, None, None)
                if ctx:
                    await ctx.__aexit__(None, None, None)
                logger.info(f"已断开服务器上下文：{server_name}")
            except Exception as e:
                logger.error(f"断开服务器 {server_name} 时出错：{e}")
        
        self.sessions.clear()
        self.contexts.clear()
        self.available_tools.clear()
        self.tool_to_server.clear()
        self.tool_cache.clear()
        
        logger.info("所有 MCP 服务器连接已断开")
