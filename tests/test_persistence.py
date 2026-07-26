# -*- coding: utf-8 -*-
"""
Persistence Test
验证 OCO L2 持久化机制：确保通过 thread_id 可以恢复认知状态。
"""

import asyncio
import os
from AI_Ori.Project_Omega_OCO.core.graph import OmegaCognitiveGraph
from AI_Ori.Project_Omega_OCO.mcp.client import OCO_MCPClient

async def test_l2_persistence():
    # 1. 初始化环境
    mcp_client = OCO_MCPClient()
    graph = OmegaCognitiveGraph(mcp_client)
    
    thread_id = "test_persistence_thread_001"
    goal = "Verify L2 Persistence"
    
    print(f"--- Step 1: First Run (Thread: {thread_id}) ---")
    # 第一次运行，应该从初始状态开始
    result1 = await graph.run(goal=goal, thread_id=thread_id)
    print(f"First run completed. Plan Version: {result1.get('plan_version')}")
    
    # 验证是否生成了数据库文件
    if os.path.exists("checkpoints.sqlite"):
        print("✅ Checkpoints database created.")
    else:
        print("❌ Checkpoints database NOT found.")
        return

    print("\n--- Step 2: Second Run (Same Thread: {thread_id}) ---")
    # 第二次运行，使用相同的 thread_id，应该触发状态恢复
    # 注意：由于目前的节点是 Mock 逻辑，每次 ainvoke 都会跑完整个图。
    # 我们通过检查 graph.run 内部的打印信息 "Recovering state for thread..." 来验证。
    result2 = await graph.run(goal=goal, thread_id=thread_id)
    print(f"Second run completed. Plan Version: {result2.get('plan_version')}")

    # 验证状态是否一致 (在 Mock 模式下，我们主要验证恢复逻辑被触发)
    print("\n--- Verification ---")
    config = {"configurable": {"thread_id": thread_id}}
    state = await graph.app.aget_state(config)
    if state.values:
        print("✅ State successfully recovered from L2 storage.")
    else:
        print("❌ State recovery failed.")

if __name__ == "__main__":
    asyncio.run(test_l2_persistence())