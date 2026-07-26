# -*- coding: utf-8 -*-
"""
Harness MCP Server
将 Harness Agent 的能力暴露为 MCP 工具，供 OCO 认知闭环调用。

架构：
OCO Planner → MCP Client → Harness MCP Server → Harness Agent → 工具执行
"""

import os
import sys
import json
import time
from typing import Dict, Any, List
from pathlib import Path

# 添加项目根目录到路径
import os
import sys
from pathlib import Path

# 获取绝对路径，并避免导入冲突
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.append(str(PROJECT_ROOT))
sys.path.append(str(PROJECT_ROOT / "Project_Omega_OCO"))

# 延迟导入以防止干扰标准库 mcp
def get_logger():
    # 强制从指定绝对路径加载模块
    import importlib.util
    module_name = "tool_call_logger"
    file_path = str(PROJECT_ROOT / "Project_Omega_OCO" / "mcp" / "utils" / "tool_call_logger.py")
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.get_logger()

# 配置日志
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Harness_MCP_Server")

try:
    from mcp.server.fastmcp import FastMCP
    MCP_AVAILABLE = True
except ImportError as e:
    logger.error(f"Failed to import mcp: {e}")
    MCP_AVAILABLE = False
    FastMCP = None


class HarnessMCPServer:
    """
    Harness MCP Server
    
    将 Harness Agent 封装为 MCP 工具，提供以下能力：
    1. call_agent: 调用 Harness Agent 处理任务
    2. list_sessions: 列出所有会话
    3. get_session: 获取指定会话详情
    """
    
    def __init__(self):
        if not MCP_AVAILABLE:
            raise ImportError("请先安装 mcp 库：pip install mcp")
        
        self.mcp = FastMCP("Harness_Agent")
        self.base_url = "http://127.0.0.1:5006"
        self.tool_logger = get_logger()  # 初始化工具调用日志记录器
        self._setup_tools()
    
    def _setup_tools(self):
        """定义并注册 Harness 工具"""
        
        @self.mcp.tool()
        async def call_harness_agent(
            message: str,
            session_id: str = "default",
            mode: str = "autonomous"
        ) -> Dict[str, Any]:
            """
            调用 Harness Agent 处理任务
            
            Args:
                message: 用户消息/任务描述
                session_id: 会话 ID（用于保持上下文）
                mode: 模式 - 'autonomous' (自主) 或 'interactive' (交互)
            
            Returns:
                Dict[str, Any]: 包含 response, session_info 等的结果字典
            """
            import urllib.request
            import urllib.parse
            
            start_time = time.time()
            request_params = {"message": message, "session_id": session_id, "mode": mode}
            
            try:
                url = f"{self.base_url}/api/agent"
                payload = {
                    "message": message,
                    "session_id": session_id,
                    "mode": mode
                }
                
                data = json.dumps(payload).encode('utf-8')
                req = urllib.request.Request(
                    url,
                    data=data,
                    headers={'Content-Type': 'application/json'},
                    method='POST'
                )
                
                with urllib.request.urlopen(req, timeout=300) as response:
                    result = json.loads(response.read().decode('utf-8'))
                    
                    # 记录工具调用日志
                    self.tool_logger.log_call(
                        tool_name="call_harness_agent",
                        server_name="Harness_MCP_Server",
                        request_params=request_params,
                        response=result,
                        start_time=start_time,
                        status="success"
                    )
                    
                    logger.info(f"[Harness MCP] Agent 调用成功：{message[:50]}...")
                    return result
                    
            except Exception as e:
                # 记录错误日志
                self.tool_logger.log_call(
                    tool_name="call_harness_agent",
                    server_name="Harness_MCP_Server",
                    request_params=request_params,
                    response={"error": str(e)},
                    start_time=start_time,
                    status="error",
                    error_message=str(e)
                )
                
                logger.error(f"[Harness MCP] Agent 调用失败：{e}")
                return {
                    "success": False,
                    "error": str(e),
                    "response": f"Harness Agent 调用失败：{str(e)}"
                }
        
        @self.mcp.tool()
        async def get_harness_session(session_id: str) -> Dict[str, Any]:
            """
            获取 Harness 会话详情
            
            Args:
                session_id: 会话 ID
            
            Returns:
                Dict[str, Any]: 会话详情
            """
            import urllib.request
            
            start_time = time.time()
            request_params = {"session_id": session_id}
            
            try:
                url = f"{self.base_url}/api/session/{session_id}"
                req = urllib.request.Request(url, method='GET')
                
                with urllib.request.urlopen(req, timeout=30) as response:
                    result = json.loads(response.read().decode('utf-8'))
                    
                    # 记录工具调用日志
                    self.tool_logger.log_call(
                        tool_name="get_harness_session",
                        server_name="Harness_MCP_Server",
                        request_params=request_params,
                        response=result,
                        start_time=start_time,
                        status="success"
                    )
                    
                    return result
                    
            except Exception as e:
                # 记录错误日志
                self.tool_logger.log_call(
                    tool_name="get_harness_session",
                    server_name="Harness_MCP_Server",
                    request_params=request_params,
                    response={"error": str(e)},
                    start_time=start_time,
                    status="error",
                    error_message=str(e)
                )
                
                logger.error(f"[Harness MCP] 获取会话失败：{e}")
                return {
                    "success": False,
                    "error": str(e)
                }
        
        @self.mcp.tool()
        async def list_harness_sessions() -> List[str]:
            """
            列出所有 Harness 会话
            
            Returns:
                List[str]: 会话 ID 列表
            """
            import urllib.request
            
            start_time = time.time()
            request_params = {}
            
            try:
                url = f"{self.base_url}/api/sessions"
                req = urllib.request.Request(url, method='GET')
                
                with urllib.request.urlopen(req, timeout=30) as response:
                    result = json.loads(response.read().decode('utf-8'))
                    sessions = result.get("sessions", [])
                    
                    # 记录工具调用日志
                    self.tool_logger.log_call(
                        tool_name="list_harness_sessions",
                        server_name="Harness_MCP_Server",
                        request_params=request_params,
                        response={"sessions": sessions},
                        start_time=start_time,
                        status="success"
                    )
                    
                    return sessions
                    
            except Exception as e:
                # 记录错误日志
                self.tool_logger.log_call(
                    tool_name="list_harness_sessions",
                    server_name="Harness_MCP_Server",
                    request_params=request_params,
                    response={"error": str(e)},
                    start_time=start_time,
                    status="error",
                    error_message=str(e)
                )
                
                logger.error(f"[Harness MCP] 列出会话失败：{e}")
                return []
    
    def run(self):
        """启动 MCP Server"""
        logger.info("[Harness MCP Server] 启动中...")
        self.mcp.run()


if __name__ == "__main__":
    server = HarnessMCPServer()
    server.run()
