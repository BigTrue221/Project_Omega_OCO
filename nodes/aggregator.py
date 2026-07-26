# -*- coding: utf-8 -*-
"""
Aggregator Node
聚合节点：负责将所有子任务的结果汇总，生成最终的认知输出。
"""

import time
import logging
from typing import Dict, Any

# 使用灵活的导入方式
try:
    from ..core.state import OmegaState
    from ..core.llm import LLMClient
except ImportError:
    try:
        from Project_Omega_OCO.core.state import OmegaState
        from Project_Omega_OCO.core.llm import LLMClient
    except ImportError:
        from AI_Ori.Project_Omega_OCO.core.state import OmegaState
        from AI_Ori.Project_Omega_OCO.core.llm import LLMClient

logger = logging.getLogger("OCO_Aggregator")

class Aggregator:
    def __init__(self):
        self.llm = LLMClient()

    async def __call__(self, state: OmegaState) -> Dict[str, Any]:
        """
        聚合逻辑：
        1. 提取所有 subtask_results。
        2. 将结果进行格式化汇总。
        3. 生成最终响应。
        """
        node_start = time.time()
        
        goal = state.get("goal", "Unknown Goal")
        results = state.get("subtask_results", [])
        
        print(f"[Aggregator][TIMING] 开始执行 Aggregator 节点，goal={goal[:50]}...")
        
        if not results:
            print(f"[Aggregator][TIMING] 无结果可聚合")
            return {
                "cognitive_trace": ["Aggregator: No results to aggregate"],
                "is_final": True
            }

        # 真实 LLM 认知汇总
        summary_text = "\n".join([f"Task {res.task_id}: {res.result}" for res in results])
        
        llm_start = time.time()
        print(f"[Aggregator][TIMING] 正在调用 LLM 进行认知汇总...")
        final_response = self.llm.chat(
            system_prompt="你是一个认知汇总专家。请将碎片化的执行结果升华为一个结构清晰、逻辑严密的最终答案。不要简单地罗列，而要进行综合分析。",
            user_prompt=f"目标：{goal}\n执行结果汇总:\n{summary_text}"
        )
        llm_elapsed = time.time() - llm_start
        print(f"[Aggregator][TIMING] LLM 认知汇总完成，耗时：{llm_elapsed:.2f}秒")
        
        node_elapsed = time.time() - node_start
        print(f"[Aggregator][TIMING] Aggregator 节点执行完成，总耗时：{node_elapsed:.2f}秒")
        
        return {
            "cognitive_trace": ["Aggregator: Successfully synthesized final response"],
            "is_final": True,
            "context": {**state.get("context", {}), "final_response": final_response}
        }
