#!/usr/bin/env python3
"""
Novel MCP Server 连接验证测试

验证 Novel MCP Server 是否正确连接到 LangGraph API。
"""

import sys
import os
import asyncio

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Project_Omega_OCO.mcp.client import OCO_MCPClient, MCPServerConfig


def print_section(title: str):
    """打印章节标题"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_test_result(name: str, passed: bool, details: str = ""):
    """打印测试结果"""
    status = "✅" if passed else "❌"
    print(f"  {status} {name}")
    if details:
        print(f"     {details}")


async def test_novel_mcp_connection():
    """测试 Novel MCP Server 连接"""
    print_section("Novel MCP Server 连接验证")
    
    client = OCO_MCPClient(enable_cache=False)
    
    # 获取项目根目录
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # Novel MCP Server 路径
    novel_server_path = os.path.join(project_root, "mcp", "servers", "novel_mcp_server.py")
    
    if not os.path.exists(novel_server_path):
        print(f"  ⚠️  Novel MCP Server 不存在：{novel_server_path}")
        print("  跳过此测试")
        return True
    
    print(f"\n📋 连接 Novel MCP Server...")
    print(f"   路径：{novel_server_path}")
    
    config = MCPServerConfig(
        name="novel_tools",
        command=sys.executable,
        args=[novel_server_path],
        env={"PYTHONPATH": project_root}
    )
    
    success = await client.add_server(config)
    
    if not success:
        print("  ❌ 连接失败")
        return False
    
    # 检查发现的工具
    tools = client.list_available_tools(detailed=True)
    print(f"\n📋 发现的工具 ({len(tools)} 个):")
    for tool in tools:
        print(f"   - {tool['name']}: {tool['description'][:80]}...")
    
    # 验证工具列表不为空
    passed = len(tools) > 0
    print_test_result("工具发现", passed, f"发现 {len(tools)} 个工具")
    
    # 验证特定工具存在
    expected_tools = ["generate_outline", "write_chapter", "get_state"]
    found_tools = [t["name"] for t in tools]
    
    for expected_tool in expected_tools:
        tool_exists = expected_tool in found_tools
        print_test_result(f"工具 {expected_tool} 存在", tool_exists)
        passed = passed and tool_exists
    
    # 健康检查
    print("\n📋 健康检查...")
    health_results = await client.health_check("novel_tools")
    print(f"   结果：{health_results}")
    
    is_healthy = health_results.get("novel_tools", {}).get("status") == "healthy"
    print_test_result("健康检查", is_healthy)
    passed = passed and is_healthy
    
    # 清理
    await client.disconnect_all()
    
    return passed


async def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("  Novel MCP Server 连接验证测试")
    print("=" * 60)
    
    passed = await test_novel_mcp_connection()
    
    print_section("测试总结")
    
    if passed:
        print("\n🎉 所有测试通过!")
        return 0
    else:
        print("\n⚠️  部分测试失败，请检查日志")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
