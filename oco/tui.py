# -*- coding: utf-8 -*-
"""Interactive terminal UI for OCO.

The UI deliberately lives above :class:`OCOCapability`: it is a presentation and
input layer, not a second orchestration runtime.  This keeps the CLI, botmux and
future web/API surfaces on the same execution contract.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
import os
import queue
import select
import sys
import threading
import time
from typing import Any, Deque, Dict, List, Optional, TextIO

from rich import box
from rich.console import Console, Group, RenderableType
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live

from .capability import OCOCapability


FLOW = ("router", "planner", "executor", "critic", "aggregator")
STAGE_LABELS = {
    "initializing": "初始化",
    "connecting_mcp": "连接 MCP",
    "starting": "启动认知图",
    "resuming": "恢复会话",
    "planning": "规划",
    "executing": "执行工具",
    "completed": "完成",
    "failed": "失败",
}


@dataclass
class TUIState:
    session_id: str
    thread_id: Optional[str] = None
    current_goal: str = ""
    last_goal: str = ""
    route: Dict[str, Any] = field(default_factory=dict)
    plan: List[Dict[str, Any]] = field(default_factory=list)
    phase: str = "ready"
    detail: str = "输入任务开始，OCO 会在这里展示完整执行链路。"
    progress: float = 0.0
    running: bool = False
    stop_requested: bool = False
    show_detail: bool = True
    result: str = ""
    success: Optional[bool] = None
    events: Deque[str] = field(default_factory=lambda: deque(maxlen=60))
    history: Deque[Dict[str, str]] = field(default_factory=lambda: deque(maxlen=12))
    queued: Deque[str] = field(default_factory=lambda: deque(maxlen=5))


class TerminalInput:
    """Small dependency-free cbreak input reader for the resident editor."""

    def __init__(self, stream: TextIO = sys.stdin):
        self.stream = stream
        self._fd: Optional[int] = None
        self._old_attrs = None

    def __enter__(self) -> "TerminalInput":
        if not self.stream.isatty():
            raise RuntimeError("oco tui requires an interactive terminal")
        import termios
        import tty

        self._fd = self.stream.fileno()
        self._old_attrs = termios.tcgetattr(self._fd)
        tty.setcbreak(self._fd)
        return self

    def __exit__(self, *_exc: Any) -> None:
        if self._fd is not None and self._old_attrs is not None:
            import termios

            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old_attrs)

    def read_key(self, timeout: float = 0.05) -> Optional[str]:
        if self._fd is None:
            return None
        ready, _, _ = select.select([self._fd], [], [], timeout)
        if not ready:
            return None
        char = self.stream.read(1)
        if char != "\x1b":
            return char

        # Decode the common arrow/home/end sequences without pulling in a TUI
        # framework.  Unknown escape sequences are ignored.
        sequence = ""
        for _ in range(3):
            ready, _, _ = select.select([self._fd], [], [], 0.01)
            if not ready:
                break
            sequence += self.stream.read(1)
        return {
            "[A": "up",
            "[B": "down",
            "[C": "right",
            "[D": "left",
            "[H": "home",
            "[F": "end",
        }.get(sequence, "escape")


class OCOInteractiveTUI:
    """A resident, single-session OCO workbench.

    Tasks execute in a worker thread while the editor remains available.  A
    message entered during execution is queued as the next turn; it is not
    silently dropped and it does not pretend that OCO currently supports
    cancellation/steering inside a LangGraph invocation.
    """

    def __init__(
        self,
        capability: Optional[OCOCapability] = None,
        *,
        timeout: int = 600,
        enable_vector_store: bool = False,
        console: Optional[Console] = None,
    ) -> None:
        self.capability = capability or OCOCapability()
        self.timeout = timeout
        self.enable_vector_store = enable_vector_store
        self.console = console or Console()
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.state = TUIState(session_id=f"tui-{stamp}-{os.getpid()}")
        self._events: "queue.Queue[tuple[str, Any]]" = queue.Queue()
        self._worker: Optional[threading.Thread] = None
        self._input = ""
        self._input_history: List[str] = []
        self._history_index: Optional[int] = None

    def run(self, initial_goal: Optional[str] = None) -> None:
        """Run the interactive UI until Ctrl-C, Ctrl-D or /quit."""
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            if initial_goal:
                self._submit(initial_goal)
                while self.state.running:
                    self._drain_events()
                    time.sleep(0.05)
                if self.state.result:
                    self.console.print(self.state.result)
                close = getattr(self.capability, "close", None)
                if close is not None:
                    close()
                return
            raise RuntimeError("oco tui requires an interactive terminal")

        try:
            with TerminalInput() as reader:
                with Live(
                    self._render(),
                    console=self.console,
                    screen=True,
                    refresh_per_second=12,
                    transient=False,
                ) as live:
                    if initial_goal:
                        self._submit(initial_goal)
                    self._run_loop(reader, live)
        finally:
            close = getattr(self.capability, "close", None)
            if close is not None:
                close()

    def _run_loop(self, reader: TerminalInput, live: Live) -> None:
        while True:
            self._drain_events()
            live.update(self._render(), refresh=True)
            if self.state.stop_requested and not self.state.running:
                return
            key = reader.read_key()
            if key is not None:
                self._handle_key(key)

    def _submit(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        if text not in self._input_history:
            self._input_history.append(text)
        self._history_index = None

        if text.startswith("/"):
            self._command(text)
            return
        if self.state.running:
            if len(self.state.queued) >= self.state.queued.maxlen:
                self._log("队列已满，当前输入未加入队列。")
            else:
                self.state.queued.append(text)
                self._log(f"已排队：{text}")
            return
        self._start_task(text)

    def _start_task(self, goal: str) -> None:
        context: Dict[str, Any] = {"entrypoint": "tui"}
        if self.state.thread_id:
            context["thread_id"] = self.state.thread_id
        if self.state.last_goal:
            context["current_task"] = self.state.last_goal

        try:
            route = self.capability.route(goal, sender_id=self.state.session_id, context=context)
            # A complex new task owns the new router thread.  A follow-up keeps
            # the current thread; simple turns get a stable TUI thread too.
            if route.get("thread_id"):
                self.state.thread_id = route["thread_id"]
            elif not self.state.thread_id:
                self.state.thread_id = f"{self.state.session_id}-default"
            plan = self.capability.plan(goal, context=context).get("plan", [])
        except Exception as exc:
            self._log(f"路由失败：{exc}")
            self.state.success = False
            self.state.phase = "failed"
            self.state.detail = str(exc)
            return

        self.state.current_goal = goal
        self.state.last_goal = goal
        self.state.route = route
        self.state.plan = plan if isinstance(plan, list) else []
        self.state.phase = "initializing"
        self.state.progress = 0.05
        self.state.detail = "任务已接收，准备启动认知闭环。"
        self.state.result = ""
        self.state.success = None
        self.state.running = True
        self._log(f"开始任务：{goal}")

        thread_id = self.state.thread_id or f"{self.state.session_id}-default"
        self._worker = threading.Thread(
            target=self._worker_run,
            args=(goal, thread_id, route),
            name="OCO-TUI-Task",
            daemon=True,
        )
        self._worker.start()

    def _worker_run(self, goal: str, thread_id: str, route: Dict[str, Any]) -> None:
        try:
            result = self.capability.run(
                goal=goal,
                thread_id=thread_id,
                context={"entrypoint": "tui", "route": route},
                timeout=self.timeout,
                enable_vector_store=self.enable_vector_store,
                progress_callback=lambda stage, detail, progress: self._events.put(
                    ("progress", (stage, detail, progress))
                ),
            )
            self._events.put(("result", result))
        except Exception as exc:  # pragma: no cover - defensive worker boundary
            self._events.put(("result", {"success": False, "error": str(exc), "response": str(exc)}))

    def _drain_events(self) -> None:
        while True:
            try:
                kind, payload = self._events.get_nowait()
            except queue.Empty:
                return
            if kind == "progress":
                stage, detail, progress = payload
                self.state.phase = stage
                self.state.detail = detail
                self.state.progress = max(0.0, min(1.0, float(progress)))
                self._log(f"{STAGE_LABELS.get(stage, stage)} · {detail}")
            elif kind == "result":
                result = payload or {}
                self.state.running = False
                self.state.success = bool(result.get("success"))
                self.state.phase = "completed" if self.state.success else "failed"
                self.state.progress = 1.0
                self.state.result = str(result.get("response") or result.get("error") or result)
                self.state.detail = "任务完成" if self.state.success else "任务失败，详情见结果区。"
                self.state.history.append(
                    {
                        "goal": self.state.current_goal,
                        "status": "成功" if self.state.success else "失败",
                        "time": datetime.now().strftime("%H:%M:%S"),
                    }
                )
                self._log(self.state.detail)
                self.state.current_goal = ""
                self._start_next_queued()

    def _start_next_queued(self) -> None:
        if self.state.stop_requested or not self.state.queued:
            return
        next_goal = self.state.queued.popleft()
        self._start_task(next_goal)

    def _command(self, raw: str) -> None:
        command, _, argument = raw.partition(" ")
        command = command.lower()
        if command in {"/q", "/quit", "/exit"}:
            self.state.stop_requested = True
            self._log("退出请求已记录；当前任务完成后退出。")
        elif command in {"/new", "/reset"}:
            if self.state.running:
                self._log("当前任务执行中，完成后再新建会话。")
            else:
                self.state.thread_id = None
                self.state.last_goal = ""
                self.state.route = {}
                self.state.plan = []
                self.state.result = ""
                self.state.success = None
                self._log("已新建 OCO 会话，下一条复杂任务将创建新的 thread_id。")
        elif command in {"/detail", "/details"}:
            self.state.show_detail = not self.state.show_detail
        elif command == "/clear":
            self.state.events.clear()
            self.state.history.clear()
            self.state.result = ""
        elif command in {"/help", "/h"}:
            self._log("命令：/new 新会话 · /detail 展开/收起细节 · /clear 清屏 · /quit 退出")
        elif command == "/thread":
            self._log(f"当前 thread_id：{self.state.thread_id or '尚未创建'}")
        elif argument and command == "/run":
            self._submit(argument)
        else:
            self._log(f"未知命令：{command}；输入 /help 查看帮助。")

    def _handle_key(self, key: str) -> None:
        if key in {"\x03", "escape"}:
            if self.state.running:
                self._log("已请求退出；OCO 当前运行不支持强制取消。")
            else:
                self.state.stop_requested = True
            return
        if key in {"\x04"}:
            self.state.stop_requested = True
            return
        if key in {"\r", "\n"}:
            text = self._input
            self._input = ""
            self._submit(text)
            return
        if key == "backspace" or key == "\x7f":
            self._input = self._input[:-1]
            return
        if key == "up":
            if self._input_history:
                self._history_index = len(self._input_history) - 1 if self._history_index is None else max(0, self._history_index - 1)
                self._input = self._input_history[self._history_index]
            return
        if key == "down":
            if self._history_index is not None:
                self._history_index += 1
                if self._history_index >= len(self._input_history):
                    self._history_index = None
                    self._input = ""
                else:
                    self._input = self._input_history[self._history_index]
            return
        if key == "\x15":  # Ctrl-U
            self._input = ""
            return
        if key == "\x17":  # Ctrl-W
            self._input = self._input.rstrip()
            self._input = self._input.rsplit(" ", 1)[0] if " " in self._input else ""
            return
        if len(key) == 1 and key >= " ":
            self._input += key

    def _log(self, message: str) -> None:
        self.state.events.append(f"{datetime.now().strftime('%H:%M:%S')}  {message}")

    def _render(self) -> RenderableType:
        s = self.state
        title = Text()
        title.append(" OCO ", style="bold white on #6d4aff")
        title.append("  Cognitive Workbench", style="bold #d8ccff")
        title.append("\n  Router → Planner → Executor → Critic → Aggregator", style="#8c91a8")

        status = Text()
        if s.running:
            status.append("● RUNNING", style="bold #fbbf24")
        elif s.success is True:
            status.append("● READY", style="bold #55d187")
        elif s.success is False:
            status.append("● DEGRADED", style="bold #ff7676")
        else:
            status.append("● READY", style="bold #55d187")
        status.append(f"   thread  {s.thread_id or 'new session'}", style="#9aa1b5")
        status.append(f"   queue  {len(s.queued)}", style="#9aa1b5")

        flow = Text()
        for index, stage in enumerate(FLOW):
            if index:
                flow.append("  →  ", style="#555b73")
            label = stage.upper()
            if self._stage_active(stage):
                flow.append(f"◉ {label}", style="bold #b79cff")
            else:
                flow.append(f"○ {label}", style="#6d7285")

        progress_width = 34
        filled = int(progress_width * s.progress)
        bar = "━" * filled + "─" * (progress_width - filled)
        progress = Text()
        progress.append(f"{bar}  {int(s.progress * 100):3d}%", style="bold #9f83ff")
        progress.append(f"\n{s.detail}", style="#a6abc0")

        overview = Group(status, Text(""), flow, Text(""), progress)
        left = Panel(overview, title="[bold]执行状态[/bold]", border_style="#5f55a6", box=box.ROUNDED, padding=(1, 2))

        plan_table = Table.grid(expand=True, padding=(0, 1))
        plan_table.add_column(style="#b9bfd1", width=4, no_wrap=True)
        plan_table.add_column(style="bold #d7ccff", width=18, no_wrap=True, overflow="ellipsis")
        plan_table.add_column(style="#8f96aa", no_wrap=True, overflow="ellipsis")
        if s.plan:
            for index, item in enumerate(s.plan[:6], 1):
                plan_table.add_row(str(index), str(item.get("tool", "-")), str(item.get("description", ""))[:52])
        else:
            plan_table.add_row("—", "等待任务", "输入目标后展示离线计划预览")
        plan_panel = Panel(plan_table, title="[bold]计划预览[/bold]", border_style="#40506d", box=box.ROUNDED, padding=(1, 1))

        activity_lines = list(s.events)[-8:] if s.show_detail else ["细节已收起 · 输入 /detail 展开"]
        activity = Text("\n".join(activity_lines) or "暂无事件", style="#9ca3b8")
        detail_panel = Panel(activity, title="[bold]实时执行细节[/bold]", border_style="#40506d", box=box.ROUNDED, padding=(1, 1))

        body = Table.grid(expand=True)
        body.add_column(ratio=3)
        body.add_column(ratio=2)
        body.add_row(left, plan_panel)
        body.add_row(detail_panel, self._result_panel())

        input_text = Text()
        input_text.append("❯ ", style="bold #b79cff")
        input_text.append(self._input, style="white")
        input_text.append("▌", style="bold #b79cff")
        if s.queued:
            input_text.append(f"\n  已排队：{list(s.queued)[0][:70]}", style="#fbbf24")
        input_help = Text("Enter 发送/排队   ↑↓ 历史   Ctrl-U 清空   /help 帮助   Ctrl-C 退出", style="#777e96")
        editor = Panel(Group(input_text, input_help), title="[bold]常驻输入[/bold]", border_style="#6d4aff", box=box.ROUNDED, padding=(0, 1))

        return Panel(Group(title, Text(""), body, Text(""), editor), border_style="#302b52", box=box.SIMPLE, padding=(0, 1))

    def _result_panel(self) -> RenderableType:
        if not self.state.result:
            return Panel(Text("完成后的答案会显示在这里。", style="#727990"), title="[bold]最终结果[/bold]", border_style="#40506d", box=box.ROUNDED)
        text = self.state.result
        if len(text) > 3500:
            text = text[:3500] + "\n\n…（结果过长，已截断）"
        return Panel(Markdown(text), title="[bold]最终结果[/bold]", border_style="#3f8f6b" if self.state.success else "#a44c5c", box=box.ROUNDED, padding=(1, 1))

    def _stage_active(self, stage: str) -> bool:
        if self.state.phase in {"ready", "completed", "failed"}:
            return self.state.phase == "completed" and stage == "aggregator"
        current = {"initializing": 0, "connecting_mcp": 0, "starting": 0, "resuming": 0, "planning": 1, "executing": 2, "critic": 3, "aggregating": 4}.get(self.state.phase, 0)
        return FLOW.index(stage) == current


def run_tui(
    initial_goal: Optional[str] = None,
    *,
    timeout: int = 600,
    enable_vector_store: bool = False,
    capability: Optional[OCOCapability] = None,
) -> None:
    """Convenience entry point used by the Typer command."""
    OCOInteractiveTUI(
        capability=capability,
        timeout=timeout,
        enable_vector_store=enable_vector_store,
    ).run(initial_goal=initial_goal)
