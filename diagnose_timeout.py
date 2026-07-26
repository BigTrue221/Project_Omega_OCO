# -*- coding: utf-8 -*-
"""
OCO 认知闭环超时诊断脚本

诊断目标：找出导致 300 秒超时的根本原因

可能的原因：
1. LLM 调用卡住（Planner 节点调用 LLMClient）
2. MCP 工具调用卡住（Executor 节点调用 MCP 工具）
3. 认知图执行根本没有开始
4. subtask_results 更新逻辑错误导致无限循环
"""

import asyncio
import time
import sys
import os
from pathlib import Path

# 添加路径 - 先添加 Project_Omega_OCO 目录
project_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_dir)

# 先导入本地模块（避免与系统 mcp 库冲突）
from Project_Omega_OCO.mcp.client import OCO_MCPClient, MCPServerConfig
from core.llm import LLMClient

async def test_llm_client():
    """测试 LLMClient 是否能正常工作"""
    print("\n" + "="*60)
    print("测试 1: LLMClient")
    print("="*60)
    
    client = LLMClient()
    
    # 测试简单聊天
    print("\n[测试] 简单聊天...")
    start = time.time()
    try:
        result = await client.chat(
            system_prompt="你是一个助手。",
            user_prompt="你好，请简单回复。"
        )
        elapsed = time.time() - start
        print(f"[结果] 耗时 {elapsed:.2f} 秒")
        print(f"[响应] {result[:100]}...")
    except Exception as e:
        print(f"[失败] {e}")
        return False
    
    # 测试 JSON 生成
    print("\n[测试] JSON 生成...")
    start = time.time()
    try:
        result = await client.generate_json(
            system_prompt="你是一个助手。请返回 JSON 格式。",
            user_prompt="请返回一个简单的计划：[{'task_id': '1', 'description': '测试'}]"
        )
        elapsed = time.time() - start
        print(f"[结果] 耗时 {elapsed:.2f} 秒")
        print(f"[响应] {result}")
    except Exception as e:
        print(f"[失败] {e}")
        return False
    
    return True

async def test_mcp_client():
    """测试 MCPClient 是否能正常工作"""
    print("\n" + "="*60)
    print("测试 2: MCPClient")
    print("="*60)
    
    client = OCO_MCPClient()
    
    # 配置 Novel MCP Server
    project_root = Path(__file__).parent.parent
    novel_server_path = project_root / "Project_Omega_OCO" / "mcp" / "servers" / "novel_mcp_server.py"
    
    if not novel_server_path.exists():
        print(f"[失败] Novel MCP Server 不存在：{novel_server_path}")
        return False
    
    python_path = os.environ.get("PYTHON", "python3")
    novel_config = MCPServerConfig(
        name="novel_tools",
        command=python_path,
        args=[str(novel_server_path)],
        env={"PYTHONPATH": str(project_root)}
    )
    
    # 连接 MCP Server
    print("\n[测试] 连接 Novel MCP Server...")
    start = time.time()
    try:
        result = await client.add_server(novel_config)
        elapsed = time.time() - start
        print(f"[结果] 耗时 {elapsed:.2f} 秒，连接成功：{result}")
    except Exception as e:
        print(f"[失败] {e}")
        return False
    
    # 列出工具
    print("\n[测试] 列出工具...")
    start = time.time()
    try:
        tools = await client.list_all_tools()
        elapsed = time.time() - start
        print(f"[结果] 耗时 {elapsed:.2f} 秒")
        for tool in tools:
            print(f"  - {tool['name']}: {tool['description'][:50]}...")
    except Exception as e:
        print(f"[失败] {e}")
        return False
    
    # 断开连接
    await client.disconnect_all()
    
    return True

def test_subtask_results_reducer():
    """测试 subtask_results Reducer 是否正确工作"""
    print("\n" + "="*60)
    print("测试 3: subtask_results Reducer")
    print("="*60)
    
    from core.state import SubTaskResult, conflict_resolver_reducer
    
    # 创建测试数据
    result1 = SubTaskResult(
        task_id="task_1",
        result="结果 1",
        confidence=0.9,
        agent_id="agent_1",
        timestamp=time.time()
    )
    
    result2 = SubTaskResult(
        task_id="task_2",
        result="结果 2",
        confidence=0.8,
        agent_id="agent_1",
        timestamp=time.time()
    )
    
    # 测试 Reducer
    print("\n[测试] Reducer 合并结果...")
    current = [result1]
    new = [result2]
    
    merged = conflict_resolver_reducer(current, new)
    
    print(f"[当前] {len(current)} 个结果")
    print(f"[新增] {len(new)} 个结果")
    print(f"[合并后] {len(merged)} 个结果")
    
    if len(merged) == 2:
        print("[通过] Reducer 正确合并了结果")
        return True
    else:
        print("[失败] Reducer 未正确合并结果")
        return False

async def main():
    """主函数"""
    print("\n" + "#"*60)
    print("# OCO 认知闭环超时诊断")
    print("#"*60)
    
    results = {}
    
    # 测试 1: LLMClient
    results["LLMClient"] = await test_llm_client()
    
    # 测试 2: MCPClient
    results["MCPClient"] = await test_mcp_client()
    
    # 测试 3: subtask_results Reducer
    results["Reducer"] = test_subtask_results_reducer()
    
    # 总结
    print("\n" + "="*60)
    print("诊断总结")
    print("="*60)
    for name, passed in results.items():
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{name}: {status}")
    
    all_passed = all(results.values())
    print("\n" + "="*60)
    if all_passed:
        print("所有测试通过！超时问题可能出在其他地方。")
        print("建议检查：")
        print("1. 认知图执行流程是否正确")
        print("2. Executor 节点的 subtask_results 更新逻辑")
        print("3. Critic 节点的终止条件")
    else:
        print("部分测试失败！请修复上述问题。")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(main())
