
### 第十二阶段：长文本撑爆 Critic 解析导致死循环（2026-04-16 更新）

**问题现象**：
1. 用户下发了长篇小说写作任务，Planner 因为有了 `direct_response` 工具，决定“越俎代庖”，直接将数千字的小说正文写入到了 `direct_response` 的 `response` 参数中。
2. Executor 将这几千字的原样输出作为 `SubTaskResult`，传递给 `Critic` 节点进行质量审计。
3. `Critic` 在进行 LLM 评分时，由于 Prompt 中的 `eval_context` 包含了这几千字的完整小说内容，导致 LLM 生成的 JSON 评估结果过长或被意外截断。
4. JSON 解析失败（报错 `JSON parse error: Expecting property name enclosed in double quotes`），导致 `is_passed` 默认为 False，任务被迫进入无意义的重复循环（甚至达到了 6 轮以上）。
5. 虽然在第 6 轮偶尔成功解析，但前置无意义的重试加上本身极大的 Token 量，最终触发了 300 秒的全局系统超时（`[OCO Adapter] 执行超时（300 秒）`）。

**排查与修复**：
1. **防爆截断处理**：在 `nodes/critic.py` 中增加对 `results` 的长度限制，保留头尾关键信息（前 1000 字符 + 后 1000 字符），防止超长执行结果污染 LLM 审计上下文。
   ```python
   def truncate_result(res):
       try:
           res_str = str(res)
           if len(res_str) > 2000:
               return res_str[:1000] + "\n...[内容过长已截断]...\n" + res_str[-1000:]
           return res_str
       except:
           return str(res)
   ```
2. **扩大全局超时限制**：将 `adapter.py` 中的同步调用 `timeout` 从 300 秒放宽至 600 秒，为大型创作任务提供充分的生成窗口。

此举保证了无论单次工具调用返回的内容多么庞大，`Critic` 都能始终稳定输出结构化的 JSON 评判结果，避免陷入因为解析异常导致的无限重试。
