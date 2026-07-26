# -*- coding: utf-8 -*-
"""
Executor Node
执行节点：负责根据计划调用 MCP 工具并产生执行结果。
"""

import time
import logging
from typing import Dict, Any, List, Optional

# 使用灵活的导入方式
try:
    from ..core.state import OmegaState, SubTaskResult
    from ..mcp.client import OCO_MCPClient
    from ..core.llm import LLMClient
except ImportError:
    try:
        from Project_Omega_OCO.core.state import OmegaState, SubTaskResult
        from Project_Omega_OCO.mcp.client import OCO_MCPClient
        from Project_Omega_OCO.core.llm import LLMClient
    except ImportError:
        from AI_Ori.Project_Omega_OCO.core.state import OmegaState, SubTaskResult
        from AI_Ori.Project_Omega_OCO.mcp.client import OCO_MCPClient
        from AI_Ori.Project_Omega_OCO.core.llm import LLMClient

logger = logging.getLogger("OCO_Executor")

class Executor:
    def __init__(self, mcp_client: OCO_MCPClient):
        self.mcp_client = mcp_client
        self.llm = LLMClient()

    async def __call__(self, state: OmegaState) -> Dict[str, Any]:
        """
        执行逻辑：
        1. 从 current_plan 中找到第一个尚未完成的任务。
        2. 使用 MCP Client 调用对应的工具。
        3. 将结果封装为 SubTaskResult 并更新到状态中。
        """
        node_start = time.time()
        
        plan = state.get("current_plan", [])
        results = state.get("subtask_results", [])
        try:
            from ..core.context import progress_callback_var
            progress_callback = progress_callback_var.get()
        except Exception:
            try:
                from Project_Omega_OCO.core.context import progress_callback_var
                progress_callback = progress_callback_var.get()
            except Exception:
                progress_callback = None
        
        print(f"[Executor][TIMING] 开始执行 Executor 节点，计划任务数：{len(plan)}")
        
        if not plan:
            print(f"[Executor][TIMING] 无计划任务，直接返回")
            return {"cognitive_trace": ["Executor: No plan found to execute"]}

        # 1. 寻找待执行任务 (第一个不在 results 中的 task_id)
        existing_ids = {res.task_id for res in results}
        target_task = next((task for task in plan if task["task_id"] not in existing_ids), None)

        if not target_task:
            print(f"[Executor][TIMING] 所有任务已完成，直接返回")
            return {"cognitive_trace": ["Executor: All planned tasks have been executed"]}

        task_id = target_task["task_id"]
        tool_name = target_task["tool"]
        params = target_task.get("params", {})

        print(f"[Executor][TIMING] 正在执行任务 {task_id}，使用工具 {tool_name}...")
        
        # 报告进度：Executor 开始
        if progress_callback:
            progress_callback("executing", f"正在执行任务：{tool_name}...", 0.7)

        # 2. 调用 MCP 工具
        try:
            # 实际调用
            mcp_start = time.time()
            if tool_name == "CAPABILITY_MISSING":
                print(f"[Executor][TIMING] 处理能力缺失报告...")
                if progress_callback:
                    progress_callback("executing", f"系统能力不足，正在生成反馈...", 0.75)
                req_cap = params.get("required_capability", "未知能力")
                reason = params.get("reason", "未提供原因")
                observation = f"抱歉，该任务需要用到【{req_cap}】工具，但目前系统尚未接入此能力，请您先尝试构建。\n原因：{reason}"
                mcp_elapsed = time.time() - mcp_start
            else:
                print(f"[Executor][TIMING] 正在调用 MCP 工具 {tool_name}...")
                if progress_callback:
                    progress_callback("executing", f"正在调用工具 {tool_name}...", 0.75)
                observation = await self.mcp_client.call_tool(tool_name, params)
                mcp_elapsed = time.time() - mcp_start
                print(f"[Executor][TIMING] MCP 工具调用完成，耗时：{mcp_elapsed:.2f}秒")
            
            # 使用 LLM 评估执行结果的置信度
            llm_start = time.time()
            print(f"[Executor][TIMING] 正在调用 LLM 评估结果质量...")
            if progress_callback:
                progress_callback("executing", "正在评估执行结果质量...", 0.8)
            
            # 对超长 observation 进行截断，防止撑爆 LLM 评估的 JSON 解析
            def truncate_obs(obs_text):
                obs_str = str(obs_text)
                if len(obs_str) > 2000:
                    return obs_str[:1000] + "\n...[内容过长已截断]...\n" + obs_str[-1000:]
                return obs_str
                
            eval_prompt = f"请评估以下工具执行结果的质量。如果结果完整且无误，请给出高分 (0.0-1.0)，如果包含错误信息或不完整，请给出低分。结果：{truncate_obs(observation)}"
            confidence_str = self.llm.chat(
                system_prompt="你是一个结果质量评估专家。请仅输出一个 0.0 到 1.0 之间的浮点数，不要输出任何其他文字。",
                user_prompt=eval_prompt
            )
            llm_elapsed = time.time() - llm_start
            print(f"[Executor][TIMING] LLM 评估完成，耗时：{llm_elapsed:.2f}秒")
            try:
                confidence = float(confidence_str.strip())
            except:
                confidence = 0.3 if "❌" in observation else 0.85
            
            # 3. 封装结果
            result = SubTaskResult(
                task_id=task_id,
                result=observation,
                confidence=confidence,
                agent_id="OCO_EXECUTOR_01",
                timestamp=time.time(),
                metadata={"tool": tool_name, "params": params}
            )
            
            node_elapsed = time.time() - node_start
            print(f"[Executor][TIMING] Executor 节点执行完成，总耗时：{node_elapsed:.2f}秒")
            
            # 报告进度：Executor 完成
            if progress_callback:
                progress_callback("executing", f"任务 {task_id} 执行完成", 0.85)
            
            # 修复：只返回新结果，让 Reducer 处理合并
            return {
                "subtask_results": result,  # 返回单个结果（不是列表）
                "cognitive_trace": [f"Executor completed task {task_id} with confidence {confidence}"]
            }

        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            logger.error(f"Executor failed to execute task {task_id}: {e}\n{error_trace}")
            return {
                "cognitive_trace": [f"Executor failed task {task_id}: {str(e)}"],
                "error_count": state.get("error_count", 0) + 1
            }
