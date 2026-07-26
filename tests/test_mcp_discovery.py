# -*- coding: utf-8 -*-
"""
MCP 动态发现机制验证测试
MCP Dynamic Discovery Verification Test

本测试旨在验证 OCO_MCPClient 能否正确启动 MCP Server 并动态发现其提供的工具和资源。
"""

import asyncio
import os
import sys
from pathlib import Path

# 将项目根目录添加到路径
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from AI_Ori.Project_Omega_OCO.mcp.client import OCO_MCPClient, MCPServerConfig

async def test_mcp_discovery():
    print("=" * 60)
    print("🚀 开始验证 MCP 动态发现机制")
    print("=" * 60)
    
    client = OCO_MCPClient()
    
    # 配置互联网 MCP 服务器
    # 注意：这里需要指向正确的 python 解释器和服务器脚本
    # 假设使用当前环境的 python
    python_exe = sys.executable
    server_script = str(PROJECT_ROOT / "Project_Omega_OCO" / "mcp" / "servers" / "internet_server.py")
    
    config = MCPServerConfig(
        name="InternetServer",
        command=python_exe,
        args=[server_script],
        env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT)}
    )
    
    try:
        # 1. 测试连接与发现
        print(f"\n[Step 1] 尝试连接服务器: {config.name}...")
        success = await client.add_server(config)
        
        if not success:
            print("❌ 连接失败，请检查 MCP 库是否安装或服务器脚本路径是否正确")
            return
        
        print("✅ 连接成功!")
        
        # 2. 验证工具发现
        print("\n[Step 2] 验证工具动态发现...")
        tools = client.list_available_tools()
        print(f"发现工具数量: {len(tools)}")
        for tool in tools:
            print(f"  - {tool['name']}: {tool['description'][:50]}...")
            
        expected_tools = ["search_web", "search_bing", "fetch_url"]
        found_tools = [t['name'] for t in tools]
        
        for et in expected_tools:
            if et in found_tools:
                print(f"  ✅ 成功发现预期工具: {et}")
            else:
                print(f"  ❌ 未发现预期工具: {et}")
                
        # 3. 测试工具调用
        print("\n[Step 3] 测试工具实际调用 (search_web)...")
        result = await client.call_tool("search_web", {"query": "LangGraph OCO Architecture", "max_results": 1})
        if result and "❌" not in result:
            print("✅ 工具调用成功，获得结果")
            print(f"结果摘要: {result[:100]}...")
        else:
            print(f"❌ 工具调用失败: {result}")
            
    except Exception as e:
        print(f"❌ 测试过程中发生异常: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.disconnect_all()
        print("\n" + "=" * 60)
        print("测试结束")
        print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_mcp_discovery())