# -*- coding: utf-8 -*-
"""
Critic Node
评估节点：充当系统的"质量门"，决定结果是 Pass (进入 Aggregator) 还是 Fail (返回 Planner)。
"""

import time
import logging
from typing import Dict, Any, List

# 使用灵活的导入方式
try:
    from ..core.state import OmegaState
    from ..core.constants import MAX_COGNITIVE_ITERATIONS, MIN_CONFIDENCE_THRESHOLD
    from ..core.llm import LLMClient
except ImportError:
    try:
        from Project_Omega_OCO.core.state import OmegaState
        from Project_Omega_OCO.core.constants import MAX_COGNITIVE_ITERATIONS, MIN_CONFIDENCE_THRESHOLD
        from Project_Omega_OCO.core.llm import LLMClient
    except ImportError:
        from AI_Ori.Project_Omega_OCO.core.state import OmegaState
        from AI_Ori.Project_Omega_OCO.core.constants import MAX_COGNITIVE_ITERATIONS, MIN_CONFIDENCE_THRESHOLD
        from AI_Ori.Project_Omega_OCO.core.llm import LLMClient

logger = logging.getLogger("OCO_Critic")

class CriticNode:
    def __init__(self):
        self.llm = LLMClient()

    async def __call__(self, state: OmegaState) -> Dict[str, Any]:
        """
        评估逻辑：
        1. 检查是否达到最大迭代次数 (Hard Cutoff)。
        2. 检查当前计划中的所有任务是否都已完成且置信度达标。
        3. 如果所有任务通过，则标记 is_final = True。
        4. 如果未通过且未超限，则建议重新规划。
        """
        node_start = time.time()
        
        goal = state.get("goal", "")
        plan = state.get("current_plan", [])
        results = state.get("subtask_results", [])
        plan_version = state.get("plan_version", 0)
        
        print(f"[Critic][TIMING] 开始执行 Critic 节点，goal={goal[:50]}...")

        # 1. 最大迭代次数截断
        if plan_version >= MAX_COGNITIVE_ITERATIONS:
            logger.warning(f"Reached MAX_COGNITIVE_ITERATIONS ({MAX_COGNITIVE_ITERATIONS}). Forcing termination.")
            print(f"[Critic][TIMING] 达到最大迭代次数，强制终止")
            return {
                "is_final": True, 
                "cognitive_trace": ["Critic: Max iterations reached, forcing finalization"]
            }

        if not plan:
            print(f"[Critic][TIMING] 无计划可评估")
            return {"cognitive_trace": ["Critic: No plan to evaluate"]}

        # 2. 真实 LLM 质量评估
        # 构造评估上下文
        eval_context = f"目标：{goal}\n计划：{plan}\n执行结果：{results}"
        
        llm_start = time.time()
        print(f"[Critic][TIMING] 正在调用 LLM 进行质量评估...")
        eval_result = self.llm.generate_json(
            system_prompt="你是一个质量审计员。请检查执行结果是否达成了目标。特别注意：若工具返回类似 {'thread_id': 'xxx', 'status': 'outline_generating'} 或其他表明“后台任务已成功启动”的信息，说明该任务已被移交到异步流水线处理，这表示当前阶段的目标已经**完美达成**！此时必须输出 is_passed 为 true！请输出 JSON: {'is_passed': bool, 'reasoning': str}",
            user_prompt=f"请评估以下认知循环的状态：\n{eval_context}"
        )
        llm_elapsed = time.time() - llm_start
        print(f"[Critic][TIMING] LLM 质量评估完成，耗时：{llm_elapsed:.2f}秒")
        
        is_passed = eval_result.get("is_passed", False)
        reasoning = eval_result.get("reasoning", "No reasoning provided")

        if is_passed:
            print(f"[Critic][TIMING] ✅ 质量门通过：{reasoning}")
            return {
                "is_final": True,
                "cognitive_trace": [f"Critic: Passed. {reasoning}"]
            }
        else:
            print(f"[Critic][TIMING] ❌ 质量门未通过：{reasoning}")
            return {
                "is_final": False,
                "cognitive_trace": [f"Critic: Failed. {reasoning}"]
            }
