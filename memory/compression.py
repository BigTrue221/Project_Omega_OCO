# -*- coding: utf-8 -*-
"""
Cognitive Compression Mechanism
认知压缩机制：处理 L1 Working Memory (Context Window) 溢出时的信息精简策略。
"""

import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("OCO_Compression")

class CognitiveCompressor:
    """
    认知压缩器：负责在上下文达到阈值时，对状态进行语义压缩。
    """
    def __init__(self, max_tokens: int = 4096, compression_threshold: float = 0.8):
        self.max_tokens = max_tokens
        self.compression_threshold = compression_threshold

    async def compress_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        对状态进行压缩处理
        实现逻辑：
        1. 评估当前认知追踪 (cognitive_trace) 的长度。
        2. 如果超过阈值，则将旧的追踪记录进行“摘要化”或“丢弃”。
        3. 对 subtask_results 进行置信度过滤，仅保留高价值结果。
        """
        trace = state.get("cognitive_trace", [])
        results = state.get("subtask_results", [])
        
        # 模拟 Token 计数 (实际应调用 tokenizer)
        current_estimated_tokens = len(trace) * 100 + len(results) * 200
        
        if current_estimated_tokens < self.max_tokens * self.compression_threshold:
            return state # 未达到阈值，无需压缩

        print(f"[Compression] Context overflow detected ({current_estimated_tokens} tokens). Compressing...")

        # 1. 压缩认知追踪：保留最近的 5 条，其余的合并为一条摘要
        if len(trace) > 10:
            summary = f"Previous {len(trace)-5} steps summarized: System iterated through planning and execution phases."
            compressed_trace = [summary] + trace[-5:]
        else:
            compressed_trace = trace

        # 2. 压缩结果集：仅保留置信度 > 0.7 的结果，低置信度结果被丢弃以节省空间
        compressed_results = [res for res in results if res.confidence > 0.7]
        
        # 如果过滤后结果太少，则保留最新的 3 条
        if len(compressed_results) < 3 and len(results) > 0:
            compressed_results = results[-3:]

        return {
            **state,
            "cognitive_trace": compressed_trace,
            "subtask_results": compressed_results,
            "context": {**state.get("context", {}), "compression_event": "L1_Memory_Compressed"}
        }

    def summarize_result(self, result: Any) -> str:
        """将详细结果压缩为简短摘要"""
        # 实际应调用 LLM 进行摘要
        return f"Result({result.task_id}): {str(result.result)[:50]}..."