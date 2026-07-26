# -*- coding: utf-8 -*-
"""
Novel Generation Production Line End-to-End Test
验证 novel_gen_v1 生产线的完整认知闭环。
"""

import asyncio
import os
import sys
from pathlib import Path

# 确保路径正确
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from AI_Ori.Project_Omega_OCO.core.graph import OmegaCognitiveGraph
from AI_Ori.Project_Omega_OCO.mcp.client import OCO_MCPClient, MCPServerConfig
from AI_Ori.Project_Omega_OCO.memory.vector_store import OCO_VectorStore

async def test_novel_production_line():
    print("=" * 60)
    print("🚀 开始验证 Novel Generation v1 生产线")
    print("=" * 60)

    # 1. 初始化 MCP Client 并连接所有必要的服务器
    client = OCO_MCPClient()
    python_exe = sys.executable
    
    servers = [
        {
            "name": "InternetServer",
            "path": "AI_Ori/Project_Omega_OCO/mcp/servers/internet_server.py"
        },
        {
            "name": "NovelServer",
            "path": "AI_Ori/Project_Omega_OCO/mcp/servers/novel_mcp_server.py"
        }
    ]

    for s in servers:
        config = MCPServerConfig(
            name=s["name"],
            command=python_exe,
            args=[s["path"]],
            env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT)}
        )
        success = await client.add_server(config)
        if success:
            print(f"✅ Connected to {s['name']}")
        else:
            print(f"❌ Failed to connect to {s['name']}")

    # 2. 实例化认知图
    graph = OmegaCognitiveGraph(client)
    
    # 3. 执行测试用例 TC-01
    theme = "赛博朋克背景下的侦探故事"
    thread_id = "novel_test_tc01"
    
    print(f"\n[Test Case TC-01] Theme: {theme}")
    
    # 注入 L3 知识到上下文 (模拟 Planner 检索)
    vector_store = OCO_VectorStore()
    knowledge = await vector_store.query(f"关于{theme}的写作知识")
    context_str = "\n".join([k[0].content for k in knowledge])
    
    initial_context = {
        "writing_knowledge": context_str,
        "theme": theme
    }

    try:
        final_state = await graph.run(
            goal=f"为主题 '{theme}' 创作一个高质量的小说大纲及首章，确保符合三幕结构且逻辑自洽。",
            thread_id=thread_id,
            context=initial_context
        )
        
        # 4. 验证结果
        response = final_state.get("context", {}).get("final_response", "")
        if response:
            print("\n" + "=" * 20 + " FINAL OUTPUT " + "=" * 20)
            print(response)
            print("=" * 50)
            print("\n✅ Production line executed successfully.")
        else:
            print("\n❌ No final response generated.")
            
    except Exception as e:
        print(f"\n❌ Execution failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.disconnect_all()

if __name__ == "__main__":
    asyncio.run(test_novel_production_line())