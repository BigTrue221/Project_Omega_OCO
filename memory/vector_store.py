# -*- coding: utf-8 -*-
"""
L3 Long-term Memory: Real Vector Store (ChromaDB)
实现基于 ChromaDB 的跨 Session 语义检索与知识存储。
"""

import os
import uuid
import time
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

# 延迟导入 chromadb，避免由于依赖库导致 import 时直接退出
CHROMA_AVAILABLE = False
try:
    # 只检测是否可用，但不在这里实际保留全局导入
    import importlib.util
    if importlib.util.find_spec("chromadb") is not None:
        CHROMA_AVAILABLE = True
except Exception:
    CHROMA_AVAILABLE = False

@dataclass
class MemoryEntry:
    id: str
    content: str
    metadata: Dict[str, Any]
    timestamp: float
    score: float = 0.0

class OCO_VectorStore:
    """
    L3 长期记忆存储实现 - 基于 ChromaDB。
    实现了真正的语义向量检索，支持持久化存储。
    """
    def __init__(self, collection_name: str = "oco_long_term_memory", persist_directory: str = "./chroma_db"):
        if not CHROMA_AVAILABLE:
            raise ImportError("Please install chromadb to use real L3 memory: pip install chromadb")
        
        import chromadb
        from chromadb.utils import embedding_functions

        # 1. 初始化持久化客户端
        self.client = chromadb.PersistentClient(path=persist_directory)
        
        # 2. 使用默认的 embedding 函数 (Sentence Transformers)
        self.embedding_fn = embedding_functions.DefaultEmbeddingFunction()
        
        # 3. 获取或创建集合
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=self.embedding_fn
        )
        print(f"[L3 Memory] Real Vector Store initialized. Collection: {collection_name}, Path: {persist_directory}")

    async def upsert(self, content: str, metadata: Dict[str, Any] = None) -> str:
        """
        将知识点存入 L3 记忆 (语义向量化存储)
        """
        entry_id = str(uuid.uuid4())
        
        # ChromaDB 会自动调用 embedding_fn 处理 content
        self.collection.add(
            ids=[entry_id],
            documents=[content],
            metadatas=[metadata or {}]
        )
        
        print(f"[L3 Memory] Upserted semantic knowledge: {content[:50]}...")
        return entry_id

    async def query(self, query_text: str, top_k: int = 3) -> List[Tuple[MemoryEntry, float]]:
        """
        基于语义相似度检索相关知识
        """
        print(f"[L3 Memory] Semantic Querying for: {query_text}")
        
        # 执行向量检索
        results = self.collection.query(
            query_texts=[query_text],
            n_results=top_k
        )
        
        # 解析 ChromaDB 返回的结果
        # results['documents'] 是一个列表的列表 [[doc1, doc2...]]
        # results['metadatas'] 是一个列表的列表 [[meta1, meta2...]]
        # results['distances'] 是一个列表的列表 [[dist1, dist2...]]
        
        final_results = []
        if not results['documents'] or not results['documents'][0]:
            return []

        docs = results['documents'][0]
        metas = results['metadatas'][0]
        dists = results['distances'][0] if 'distances' in results else [0.0] * len(docs)

        for i in range(len(docs)):
            # ChromaDB 默认使用 L2 距离，距离越小越相似。
            # 为了统一接口，我们将距离转换为一个伪“置信度”分数 (1 / (1 + dist))
            score = 1.0 / (1.0 + dists[i]) if i < len(dists) else 0.0
            
            entry = MemoryEntry(
                id=f"doc_{i}", # 简化处理
                content=docs[i],
                metadata=metas[i] if i < len(metas) else {},
                timestamp=time.time(),
                score=score
            )
            final_results.append((entry, score))
            
        return final_results

    async def clear(self):
        """清空长期记忆"""
        self.client.delete_collection(self.collection.name)
        self.collection = self.client.get_or_create_collection(
            name="oco_long_term_memory",
            embedding_function=self.embedding_fn
        )
        print("[L3 Memory] Vector store cleared.")