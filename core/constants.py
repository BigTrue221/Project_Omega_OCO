# -*- coding: utf-8 -*-
"""
OCO 系统常量定义
System Constants for Omega Cognitive Orchestrator
"""

# 认知循环限制
MAX_COGNITIVE_ITERATIONS = 4  # 降低最大迭代次数（原为10），避免长时间死循环导致 600s 超时
MIN_CONFIDENCE_THRESHOLD = 0.6  # 结果被认为是“合格”的最低置信度阈值

# 状态标识
STATE_IDLE = "IDLE"
STATE_PLANNING = "PLANNING"
STATE_EXECUTING = "EXECUTING"
STATE_EVALUATING = "EVALUATING"
STATE_COMPLETED = "COMPLETED"
STATE_FAILED = "FAILED"

# 默认配置
DEFAULT_AGENT_ID = "OCO_CORE_AGENT"