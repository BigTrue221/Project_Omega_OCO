#!/usr/bin/env python3
"""
端到端测试脚本 - 验证 OCO 认知闭环完整流程

测试场景:
1. 简单任务 -> 传统路径
2. 复杂任务 -> OCO 认知闭环
3. Harness 任务 -> Harness Server
"""

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Project_Omega_OCO.router import OCORouter, route_message


def print_section(title: str):
    """打印章节标题"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_test_case(name: str, result):
    """打印测试结果"""
    print(f"\n📋 测试用例：{name}")
    print(f"  路由路径：{result.path if hasattr(result, 'path') else result.get('path', 'N/A')}")
    print(f"  复杂度：{result.complexity if hasattr(result, 'complexity') else result.get('complexity', 'N/A')}")
    print(f"  Thread ID: {result.thread_id if hasattr(result, 'thread_id') else result.get('thread_id', 'N/A')}")
    print(f"  决策理由：{result.reasoning if hasattr(result, 'reasoning') else result.get('reasoning', 'N/A')}")


def test_simple_tasks():
    """测试简单任务路由到传统路径"""
    print_section("测试 1: 简单任务 -> 传统路径")
    
    test_cases = [
        ("你好", "user123"),
        ("hi", "user456"),
        ("谢谢", "user789"),
        ("是谁", "user101"),
        ("什么是 AI", "user202"),
    ]
    
    all_passed = True
    for message, sender_id in test_cases:
        result = route_message(message, sender_id, {})
        print_test_case(f"'{message}'", result)
        
        # 验证：简单任务应该路由到 legacy 路径
        actual_path = result.path.value if hasattr(result.path, 'value') else str(result.path)
        if actual_path != "legacy":
            print(f"  ❌ 失败：预期路径 'legacy'，实际 '{actual_path}'")
            all_passed = False
        else:
            print(f"  ✅ 通过")
    
    return all_passed


def test_complex_tasks():
    """测试复杂任务路由到 OCO 认知闭环"""
    print_section("测试 2: 复杂任务 -> OCO 认知闭环")
    
    test_cases = [
        ("写一个科幻小说大纲", "user123"),
        ("帮我设计一个架构", "user456"),
        ("创作一个故事", "user789"),
        ("分析这个项目的代码结构", "user101"),
    ]
    
    all_passed = True
    for message, sender_id in test_cases:
        result = route_message(message, sender_id, {})
        print_test_case(f"'{message}'", result)
        
        # 验证：复杂任务应该路由到 oco 路径
        actual_path = result.path.value if hasattr(result.path, 'value') else str(result.path)
        if actual_path != "oco":
            print(f"  ❌ 失败：预期路径 'oco'，实际 '{actual_path}'")
            all_passed = False
        elif result.thread_id is None:
            print(f"  ❌ 失败：预期有 thread_id，实际为 None")
            all_passed = False
        else:
            print(f"  ✅ 通过")
    
    return all_passed


def test_harness_tasks():
    """测试 Harness 任务路由到 Harness Server"""
    print_section("测试 3: Harness 任务 -> Harness Server")
    
    test_cases = [
        ("大 G，帮我写代码", "user123"),
        ("大 G，分析一下这个文件", "user456"),
    ]
    
    all_passed = True
    for message, sender_id in test_cases:
        result = route_message(message, sender_id, {})
        print_test_case(f"'{message}'", result)
        
        # 验证：Harness 任务应该路由到 harness 路径
        actual_path = result.path.value if hasattr(result.path, 'value') else str(result.path)
        if actual_path != "harness":
            print(f"  ❌ 失败：预期路径 'harness'，实际 '{actual_path}'")
            all_passed = False
        else:
            print(f"  ✅ 通过")
    
    return all_passed


def test_thread_id_generation():
    """测试 thread_id 生成"""
    print_section("测试 4: thread_id 生成")
    
    router = OCORouter()
    
    # 测试新任务生成 thread_id
    message = "写一个科幻小说大纲"
    sender_id = "user123"
    
    thread_id = router.generate_thread_id(sender_id, message)
    
    print(f"\n📋 输入:")
    print(f"  sender_id: {sender_id}")
    print(f"  message: {message}")
    print(f"\n📋 生成的 thread_id: {thread_id}")
    
    # 验证 thread_id 格式
    expected_format = f"{sender_id}_"
    if thread_id.startswith(expected_format):
        print(f"  ✅ thread_id 格式正确")
        return True
    else:
        print(f"  ❌ thread_id 格式错误：预期以 '{expected_format}' 开头")
        return False


def test_new_task_detection():
    """测试新任务检测"""
    print_section("测试 5: 新任务检测")
    
    router = OCORouter()
    
    new_task_messages = [
        "写一个新的小说",
        "开始一个项目",
        "创作另一个故事",
    ]
    
    continuation_messages = [
        "好的",
        "继续",
        "y",
        "yes",
    ]
    
    all_passed = True
    
    print("\n📋 新任务检测:")
    for message in new_task_messages:
        is_new = router.detect_new_task(message, {})
        status = "✅" if is_new else "❌"
        print(f"  {status} '{message}' -> is_new_task: {is_new}")
        if not is_new:
            all_passed = False
    
    print("\n📋 续传任务检测:")
    for message in continuation_messages:
        is_new = router.detect_new_task(message, {})
        status = "✅" if not is_new else "❌"
        print(f"  {status} '{message}' -> is_new_task: {is_new}")
        if is_new:
            all_passed = False
    
    return all_passed


def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("  OCO 认知闭环端到端测试套件")
    print("=" * 60)
    
    results = {}
    
    # 执行所有测试
    results["简单任务路由"] = test_simple_tasks()
    results["复杂任务路由"] = test_complex_tasks()
    results["Harness 任务路由"] = test_harness_tasks()
    results["thread_id 生成"] = test_thread_id_generation()
    results["新任务检测"] = test_new_task_detection()
    
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
    sys.exit(main())
