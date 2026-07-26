# -*- coding: utf-8 -*-
"""
测试 LLMClient 是否能正常工作
"""

import asyncio
import sys
import os

# 添加路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.llm import LLMClient

async def test_llm():
    print("[Test] 开始测试 LLMClient...")
    
    client = LLMClient()
    
    system_prompt = "你是一个助手，请用 JSON 格式回复。"
    user_prompt = "请返回一个简单的 JSON 对象"
    
    print("[Test] 调用 chat...")
    try:
        result = await client.chat(system_prompt, user_prompt)
        print(f"[Test] chat 结果：{result}")
    except Exception as e:
        print(f"[Test] chat 失败：{e}")
    
    print("[Test] 调用 generate_json...")
    try:
        result = await client.generate_json(system_prompt, user_prompt)
        print(f"[Test] generate_json 结果：{result}")
    except Exception as e:
        print(f"[Test] generate_json 失败：{e}")

if __name__ == "__main__":
    asyncio.run(test_llm())
