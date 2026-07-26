# -*- coding: utf-8 -*-
"""
测试 MCP 服务器通过 WSL 启动的连接
"""

import asyncio
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from Project_Omega_OCO.mcp.client import OCO_MCPClient, MCPServerConfig

async def test_novel_mcp_connection():
    """测试 Novel MCP Server 连接"""
    client = OCO_MCPClient()
    
    # 使用 python3 直接启动 Novel MCP Server（在 WSL 环境中）
    config = MCPServerConfig(
        name="novel_tools",
        command="python3",
        args=["/mnt/d/AI/AI_Ori/Project_Omega_OCO/mcp/servers/novel_mcp_server.py"],
        env={"PYTHONPATH": "/mnt/d/AI/AI_Ori"}
    )
    
    print(f"正在连接 Novel MCP Server...")
    result = await client.add_server(config)
    
    if result:
        print("✅ Novel MCP Server 连接成功!")
        print(f"可用工具：{list(client.available_tools.keys())}")
    else:
        print("❌ Novel MCP Server 连接失败")
    
    return result

if __name__ == "__main__":
    result = asyncio.run(test_novel_mcp_connection())
    sys.exit(0 if result else 1)
