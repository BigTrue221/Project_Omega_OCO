# -*- coding: utf-8 -*-
"""
状态协议幂等性测试
Idempotency Tests for State Protocol
"""

import unittest
import time

try:
    from Project_Omega_OCO.core.state import conflict_resolver_reducer, SubTaskResult
except ImportError:
    from core.state import conflict_resolver_reducer, SubTaskResult

class TestStateReducer(unittest.TestCase):
    def test_initial_addition(self):
        """测试初始结果添加"""
        current = None
        new = [SubTaskResult(task_id="task_1", result="res1", confidence=0.8, agent_id="a1", timestamp=time.time())]
        result = conflict_resolver_reducer(current, new)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].task_id, "task_1")

    def test_idempotency_same_result(self):
        """测试提交相同结果的幂等性"""
        res = SubTaskResult(task_id="task_1", result="res1", confidence=0.8, agent_id="a1", timestamp=time.time())
        current = [res]
        new = [res]
        result = conflict_resolver_reducer(current, new)
        self.assertEqual(len(result), 1, "相同结果提交不应增加长度")

    def test_confidence_override(self):
        """测试高置信度结果覆盖低置信度结果"""
        res_low = SubTaskResult(task_id="task_1", result="low_res", confidence=0.5, agent_id="a1", timestamp=time.time())
        res_high = SubTaskResult(task_id="task_1", result="high_res", confidence=0.9, agent_id="a2", timestamp=time.time() + 1)
        
        current = [res_low]
        new = [res_high]
        result = conflict_resolver_reducer(current, new)
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].result, "high_res", "高置信度结果应覆盖低置信度结果")

    def test_timestamp_override(self):
        """测试相同置信度下，新时间戳覆盖旧时间戳"""
        t1 = time.time()
        res_old = SubTaskResult(task_id="task_1", result="old_res", confidence=0.8, agent_id="a1", timestamp=t1)
        res_new = SubTaskResult(task_id="task_1", result="new_res", confidence=0.8, agent_id="a2", timestamp=t1 + 10)
        
        current = [res_old]
        new = [res_new]
        result = conflict_resolver_reducer(current, new)
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].result, "new_res", "相同置信度下，新结果应覆盖旧结果")

    def test_multiple_tasks_merge(self):
        """测试多个不同任务的合并"""
        current = [
            SubTaskResult(task_id="t1", result="r1", confidence=0.7, agent_id="a1", timestamp=time.time()),
            SubTaskResult(task_id="t2", result="r2", confidence=0.7, agent_id="a1", timestamp=time.time()),
        ]
        new = [
            SubTaskResult(task_id="t2", result="r2_new", confidence=0.9, agent_id="a2", timestamp=time.time() + 1),
            SubTaskResult(task_id="t3", result="r3", confidence=0.8, agent_id="a2", timestamp=time.time() + 1),
        ]
        result = conflict_resolver_reducer(current, new)
        
        self.assertEqual(len(result), 3)
        # 检查 t2 是否被更新
        t2_res = next(r for r in result if r.task_id == "t2")
        self.assertEqual(t2_res.result, "r2_new")

if __name__ == "__main__":
    unittest.main()
