
### 第十一阶段：Planner 工具幻觉与飞书反馈循环优化（2026-04-16 更新）

**问题现象**：
1. 当用户发送类似 "你好" 或单纯的问候等无需调用工具的消息时，系统进入认知闭环后，`Planner` 节点由于必须返回带 `tool` 字段的 JSON，会幻觉编造出类似 `none`、`analyze_requirements` 等不存在的工具。
2. 这导致 `Executor` 执行失败（`未知工具：none`），触发 `Critic` 评判失败并重新规划，最多重复 10 次后强制终止（`Max iterations reached`）。
3. 飞书的进度通知中只有百分比和阶段，用户在多轮重新规划期间会以为机器人卡死在无限死循环中。

**排查与修复**：
1. **进度回调增加轮次标识**：修改 `cloud_brain/bot_server.py` 中的 `progress_callback`，引入 `plan_version` 计数器，在每次接收到 `计划生成完成` 详情时自增。飞书消息抬头变更为 `🔄 任务处理中 (第 X 轮)...`，显著提升多轮认知迭代时的用户体验。
2. **定义直通回答工具**：修改 `nodes/planner.py` 的 System Prompt，在可用工具列表尾部强行注入伪工具说明：
   ```text
   - direct_response: 如果目标只是普通的聊天、问候或可以直接回答的问题，请使用此工具。参数包含 'response' 字段存放你的直接回答。
   ```
3. **Executor 绕过 MCP 拦截直通**：修改 `nodes/executor.py`，在实际调用 MCP 之前拦截 `direct_response` 工具：
   ```python
   if tool_name == "direct_response":
       observation = params.get("response", "无法生成直接响应。")
   else:
       observation = await self.mcp_client.call_tool(tool_name, params)
   ```
此方案完美解决了 OCO 认知闭环在面临“无工具可用”时的异常震荡问题，并提高了系统面对普通闲聊和闲散指令的健壮性。
