
### 第十阶段：LangGraph 状态序列化错误（2026-04-16 更新）

**问题现象**：在通过飞书发送消息时，由于飞书后台任务传递了一个用于更新发送进度的 `progress_callback` 函数，系统报出严重错误：
```
任务执行失败：Type is not msgpack serializable: function
```

**排查过程**：
1. 分析错误提示发现，LangGraph 的 Checkpointer (即 `AsyncSqliteSaver`) 在保存认知图状态（State）时，使用了 `msgpack` 序列化。
2. 检查 `Project_Omega_OCO/core/graph.py`，发现 `run` 方法将传入的 `progress_callback` 函数直接赋值给了 `initial_state` 的 `_progress_callback` 字段。
3. 根据 **LangGraph State Serialization Rule** 原则，图的状态对象必须是完全可序列化的字典，包含不可序列化对象（如 Python 函数）会导致系统在尝试向 SQLite 写入检查点时崩溃。

**修复方案**：
引入 Python 内置的异步上下文变量 (`contextvars`)，将 `progress_callback` 从状态流转中彻底剥离，以非侵入的方式安全传递给各个节点。
1. 新建 `Project_Omega_OCO/core/context.py` 定义全局上下文变量：
   ```python
   import contextvars
   progress_callback_var = contextvars.ContextVar('progress_callback', default=None)
   ```
2. 修改 `graph.py` 中的执行入口，使用 `contextvars` 包装运行上下文，移除 `initial_state` 中的回调函数注入：
   ```python
   from .context import progress_callback_var
   token = progress_callback_var.set(progress_callback)
   try:
       final_state = await self.app.ainvoke(initial_state, config=config)
   finally:
       progress_callback_var.reset(token)
   ```
3. 在 `nodes/planner.py` 和 `nodes/executor.py` 等各个处理节点中，安全读取全局上下文变量以执行回调：
   ```python
   try:
       from ..core.context import progress_callback_var
       progress_callback = progress_callback_var.get()
   except Exception:
       progress_callback = None
   ```
此方案彻底消除了不可序列化函数对象对 LangGraph 状态机的影响，成功实现了安全的跨层级进度回调。
