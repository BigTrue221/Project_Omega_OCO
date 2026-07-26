# -*- coding: utf-8 -*-
"""
Vector Store Integration Test
验证 OCO L3 真实向量库实现：确保语义检索能够正确召回相关知识。
"""

import asyncio
import os
from AI_Ori.Project_Omega_OCO.memory.vector_store import OCO_VectorStore

async def test_semantic_retrieval():
    # 1. 初始化真实向量库
    try:
        store = OCO_VectorStore()
    except ImportError as e:
        print(f"❌ Dependency missing: {e}")
        return

    # 2. 注入不同维度的知识点
    knowledge_base = [
        ("The capital of France is Paris.", {"category": "geography"}),
        ("Quantum computing uses qubits to perform calculations.", {"category": "science"}),
        ("The OCO architecture uses a cognitive loop for adaptive planning.", {"category": "architecture"}),
        ("Python is a high-level programming language.", {"category": "coding"}),
    ]
    
    print("\n--- Step 1: Injecting Knowledge ---")
    for content, meta in knowledge_base:
        await store.upsert(content, meta)
    
    # 3. 测试语义检索 (不使用完全相同的词)
    test_queries = [
        ("Tell me about French cities", "geography"),
        ("How does quantum computers work?", "science"),
        ("What is the OCO system?", "architecture"),
        ("Which language is used for AI?", "coding"),
    ]
    
    print("\n--- Step 2: Testing Semantic Retrieval ---")
    for query, expected_cat in test_queries:
        results = await store.query(query)
        if results:
            best_match, score = results[0]
            print(f"Query: {query} -> Best Match: {best_match.content} (Score: {score:.4f})")
            # 简单验证类别是否匹配
            if best_match.metadata.get("category") == expected_cat:
                print(f"✅ Correct category: {expected_cat}")
            else:
                print(f"❌ Category mismatch: {best_match.metadata.get('category')} != {expected_cat}")
        else:
            print(f"❌ No results for query: {query}")

    # 4. 测试无关查询
    print("\n--- Step 3: Testing Irrelevant Query ---")
    results = await store.query("What is the weather in Tokyo?")
    if results:
        print(f"Irrelevant query returned result with score: {results[0][1]:.4f}")

if __name__ == "__main__":
    asyncio.run(test_semantic_retrieval())