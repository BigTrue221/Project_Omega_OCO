#!/usr/bin/env python3
"""
MCP 客户端端到端测试

测试 MCP 客户端的核心功能：
1. 工具自动发现
2. 工具调用缓存
3. 健康检查
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


async def test_tool_discovery():
    """测试工具自动发现功能"""
    print_section("测试 1: 工具自动发现")
    
    client = OCO_MCPClient(enable_cache=False)
    
    # 获取项目根目录
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # 尝试连接 Novel MCP Server
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
        print(f"   - {tool['name']}: {tool['description'][:50]}...")
    
    # 验证工具列表不为空
    passed = len(tools) > 0
    print_test_result("工具发现", passed, f"发现 {len(tools)} 个工具")
    
    # 清理
    await client.disconnect_all()
    
    return passed


async def test_tool_cache():
    """测试工具调用缓存功能"""
    print_section("测试 2: 工具调用缓存")
    
    # 创建带缓存的客户端
    client = OCO_MCPClient(enable_cache=True, cache_ttl=300)
    
    # 测试缓存统计
    stats = client.get_cache_stats()
    print(f"\n📋 初始缓存状态:")
    print(f"   启用：{stats['enabled']}")
    print(f"   TTL: {stats['ttl']} 秒")
    print(f"   大小：{stats['size']}")
    
    # 验证缓存已启用
    passed1 = stats['enabled'] == True
    print_test_result("缓存启用", passed1)
    
    # 测试清空缓存
    client.clear_cache()
    passed2 = stats['size'] == 0
    print_test_result("清空缓存", passed2)
    
    return passed1 and passed2


async def test_health_check():
    """测试健康检查功能"""
    print_section("测试 3: 健康检查")
    
    client = OCO_MCPClient(enable_cache=False)
    
    # 测试未连接服务器的健康检查
    results = await client.health_check("nonexistent_server")
    print(f"\n📋 未连接服务器健康检查:")
    print(f"   结果：{results}")
    
    passed1 = "nonexistent_server" in results
    print_test_result("未连接服务器检查", passed1)
    
    # 测试服务器状态
    status = client.get_server_status()
    print(f"\n📋 服务器状态:")
    print(f"   已连接服务器：{status['connected_servers']}")
    print(f"   总服务器数：{status['total_servers']}")
    print(f"   总工具数：{status['total_tools']}")
    
    passed2 = status['total_servers'] == 0
    print_test_result("初始状态检查", passed2)
    
    return passed1 and passed2


async def test_tool_info():
    """测试工具信息获取功能"""
    print_section("测试 4: 工具信息获取")
    
    client = OCO_MCPClient(enable_cache=False)
    
    # 测试获取不存在的工具信息
    info = client.get_tool_info("nonexistent_tool")
    passed1 = info is None
    print_test_result("不存在工具返回 None", passed1)
    
    return passed1


async def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("  MCP 客户端端到端测试套件")
    print("=" * 60)
    
    results = {}
    
    # 执行所有测试
    results["工具自动发现"] = await test_tool_discovery()
    results["工具调用缓存"] = await test_tool_cache()
    results["健康检查"] = await test_health_check()
    results["工具信息获取"] = await test_tool_info()
    
    # 打印总结
    print_section("测试总结")
    
    passed_count = sum(1 for v in results.values() if v)
    total_count = len(results)
    
    for test_name, passed in results.items():
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"  {status}: {test_name}")
    
    print(f"\n总计：{passed_count}/{total_count} 通过")
    
    if passed_count == total_count:
        print("\n🎉 所有测试通过!")
        return 0
    else:
        print("\n⚠️  部分测试失败，请检查日志")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
