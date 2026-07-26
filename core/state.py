# -*- coding: utf-8 -*-
"""
OCO 核心状态定义
Core State Definitions for Omega Cognitive Orchestrator

本模块定义了系统的统一状态模型 OmegaState 以及用于处理状态合并的 Reducer。
核心设计目标：确保状态更新的幂等性，支持认知追踪，并解决多 Agent 协作时的冲突。
"""

from typing import Annotated, TypedDict, List, Dict, Any, Optional, Union
from dataclasses import dataclass, field
import operator

@dataclass
class SubTaskResult:
    """子任务执行结果"""
    task_id: str
    result: Any
    confidence: float
    agent_id: str
    timestamp: float
    metadata: Dict[str, Any] = field(default_factory=dict)

def conflict_resolver_reducer(current: Optional[List[SubTaskResult]], new: Union[List[SubTaskResult], SubTaskResult]) -> List[SubTaskResult]:
    """
    冲突解决 Reducer
    
    实现逻辑：
    1. 确保输入统一为列表。
    2. 基于 task_id 进行幂等更新。
    3. 如果 task_id 已存在，则比较 confidence (置信度)。
    4. 仅在新结果置信度更高或 timestamp 更晚时覆盖旧结果。
    
    教学点：
    - 为什么不使用 operator.add? 因为 operator.add 会导致结果无限堆积，产生冗余。
    - 幂等性：无论同一个结果被提交多少次，最终状态应保持一致。
    """
    if current is None:
        current = []
    
    # 统一转换为列表处理
    new_results = [new] if isinstance(new, SubTaskResult) else new
    
    # 将当前结果转换为字典以便快速查找 {task_id: result}
    state_map = {res.task_id: res for res in current}
    
    for res in new_results:
        tid = res.task_id
        if tid in state_map:
            existing = state_map[tid]
            # 冲突解决策略：置信度优先 -> 时间戳次之
            if res.confidence > existing.confidence:
                state_map[tid] = res
            elif res.confidence == existing.confidence and res.timestamp > existing.timestamp:
                state_map[tid] = res
        else:
            state_map[tid] = res
            
    return list(state_map.values())

class OmegaState(TypedDict):
    """
    $\Omega$-Cognitive State (统一状态模型)
    
    L1 Working Memory 的具体实现。
    """
    # 认知元数据
    plan_version: int # 计划版本号，用于追踪认知循环迭代次数
    cognitive_trace: Annotated[List[str], operator.add] # 认知追踪：记录每一步的推理路径
    
    # 任务执行状态
    goal: str # 最终目标
    current_plan: List[Dict[str, Any]] # 当前自适应计划
    
    # 核心结果集：使用自定义 Reducer 确保幂等性
    subtask_results: Annotated[List[SubTaskResult], conflict_resolver_reducer]
    
    # 上下文信息
    context: Dict[str, Any] # 外部注入的上下文
    error_count: int # 错误计数，用于触发 max_iterations 截断
    is_final: bool # 是否已达到最终状态
