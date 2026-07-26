# -*- coding: utf-8 -*-
"""Tests for the public OCO router behavior."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from router import OCORouter, RoutePath, TaskComplexity, route_message


def test_assess_complexity():
    """测试任务复杂度评估"""
    print("\n=== 测试：任务复杂度评估 ===")
    
    router = OCORouter()
    
    # 简单任务
    simple_tasks = [
        "你好",
        "hi",
        "谢谢",
        "是谁",
        "什么是 AI",
    ]
    
    print("\n简单任务测试:")
    for task in simple_tasks:
        complexity = router.assess_complexity(task)
        print(f"  '{task}' -> {complexity.value}")
        assert complexity == TaskComplexity.SIMPLE, f"Expected SIMPLE, got {complexity}"
    
    # 复杂任务
    complex_tasks = [
        "写一个科幻小说大纲",
        "帮我设计一个架构",
        "创作一个故事",
    ]
    
    print("\n复杂任务测试:")
    for task in complex_tasks:
        complexity = router.assess_complexity(task)
        print(f"  '{task}' -> {complexity.value}")
        assert complexity == TaskComplexity.COMPLEX, f"Expected COMPLEX, got {complexity}"
    
    # 普通对话默认保持轻量路径，避免所有请求都进入重型 OCO 图。
    normal_chat_tasks = [
        "这是一个比较长的消息，但不包含任何特殊关键词，只是普通的对话内容。",
    ]
    
    print("\n普通对话任务测试:")
    for task in normal_chat_tasks:
        complexity = router.assess_complexity(task)
        print(f"  '{task[:30]}...' -> {complexity.value}")
        assert complexity == TaskComplexity.SIMPLE, f"Expected SIMPLE, got {complexity}"
    
    print("\n✅ 任务复杂度评估测试通过!")


def test_route_decision():
    """测试路由决策"""
    print("\n=== 测试：路由决策 ===")
    
    router = OCORouter()
    
    # 简单任务 -> LEGACY
    decision = router.route("你好", "user123", {})
    print(f"\n简单任务 '你好':")
    print(f"  path: {decision.path.value}")
    print(f"  complexity: {decision.complexity.value}")
    print(f"  thread_id: {decision.thread_id}")
    print(f"  reasoning: {decision.reasoning}")
    assert decision.path == RoutePath.LEGACY
    assert decision.thread_id is None
    
    # 复杂任务 -> OCO
    decision = router.route("写一个科幻小说大纲", "user123", {})
    print(f"\n复杂任务 '写一个科幻小说大纲':")
    print(f"  path: {decision.path.value}")
    print(f"  complexity: {decision.complexity.value}")
    print(f"  thread_id: {decision.thread_id}")
    print(f"  reasoning: {decision.reasoning}")
    assert decision.path == RoutePath.OCO
    assert decision.thread_id is not None
    
    # 当前公开路由策略中，代码/开发类任务统一进入 OCO 闭环。
    decision = router.route("大 G，帮我写代码", "user123", {})
    print(f"\n复杂任务 '大 G，帮我写代码':")
    print(f"  path: {decision.path.value}")
    print(f"  complexity: {decision.complexity.value}")
    print(f"  thread_id: {decision.thread_id}")
    print(f"  reasoning: {decision.reasoning}")
    assert decision.path == RoutePath.OCO
    
    print("\n✅ 路由决策测试通过!")


def test_thread_id_generation():
    """测试 thread_id 生成"""
    print("\n=== 测试：thread_id 生成 ===")
    
    router = OCORouter()
    
    sender_id = "user123"
    message = "写一个科幻小说大纲"
    
    thread_id = router.generate_thread_id(sender_id, message)
    print(f"\n输入:")
    print(f"  sender_id: {sender_id}")
    print(f"  message: {message}")
    print(f"\n生成的 thread_id: {thread_id}")
    
    # 验证 thread_id 格式
    parts = thread_id.split("_")
    assert len(parts) == 3, f"Expected 3 parts, got {len(parts)}"
    assert parts[0] == sender_id, f"Expected sender_id={sender_id}, got {parts[0]}"
    assert len(parts[2]) == 8, f"Expected hash length 8, got {len(parts[2])}"
    
    print("\n✅ thread_id 生成测试通过!")


def test_new_task_detection():
    """测试新任务检测"""
    print("\n=== 测试：新任务检测 ===")
    
    router = OCORouter()
    
    # 新任务关键词
    new_task_messages = [
        "写一个新的小说",
        "开始一个项目",
        "创作另一个故事",
    ]
    
    print("\n新任务检测:")
    for msg in new_task_messages:
        is_new = router.detect_new_task(msg, {})
        print(f"  '{msg}' -> is_new_task: {is_new}")
        assert is_new == True, f"Expected True, got {is_new}"
    
    # 续传任务（短消息）
    continuation_messages = [
        "好的",
        "继续",
        "y",
    ]
    
    print("\n续传任务检测:")
    for msg in continuation_messages:
        is_new = router.detect_new_task(msg, {"current_task": "writing_novel"})
        print(f"  '{msg}' -> is_new_task: {is_new}")
        assert is_new == False, f"Expected False, got {is_new}"
    
    print("\n✅ 新任务检测测试通过!")


def test_route_message_function():
    """测试便捷函数 route_message"""
    print("\n=== 测试：便捷函数 route_message ===")
    
    decision = route_message("写一个科幻小说大纲", "user123", {})
    print(f"\nroute_message('写一个科幻小说大纲', 'user123', {{}}):")
    print(f"  path: {decision.path.value}")
    print(f"  thread_id: {decision.thread_id}")
    
    assert decision.path == RoutePath.OCO
    assert decision.thread_id is not None
    
    print("\n✅ 便捷函数测试通过!")


def main():
    """运行所有测试"""
    print("=" * 60)
    print("OCO Router 测试套件")
    print("=" * 60)
    
    try:
        test_assess_complexity()
        test_route_decision()
        test_thread_id_generation()
        test_new_task_detection()
        test_route_message_function()
        
        print("\n" + "=" * 60)
        print("✅ 所有测试通过!")
        print("=" * 60)
        return 0
    except AssertionError as e:
        print(f"\n❌ 测试失败：{e}")
        return 1
    except Exception as e:
        print(f"\n❌ 测试异常：{e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
