# -*- coding: utf-8 -*-
"""Command line interface for Project Omega OCO."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from .botmux import OCOBotmuxRunner
from .capability import OCOCapability
from .tui import run_tui


app = typer.Typer(
    name="oco",
    help="Project Omega OCO command line interface.",
    no_args_is_help=True,
)
console = Console()


def _print(data, as_json: bool) -> None:
    if as_json:
        console.print_json(json.dumps(data, ensure_ascii=False, default=str))
    else:
        console.print(data)


@app.command()
def health(json_output: bool = typer.Option(False, "--json", help="Output machine-readable JSON.")) -> None:
    """Check local OCO runtime prerequisites."""
    capability = OCOCapability()
    health_result = capability.health().to_dict()
    if json_output:
        _print(health_result, True)
        return

    table = Table(title="OCO Health")
    table.add_column("Item")
    table.add_column("Value")
    for key, value in health_result.items():
        table.add_row(key, str(value))
    console.print(table)


@app.command()
def status(json_output: bool = typer.Option(False, "--json", help="Output machine-readable JSON.")) -> None:
    """Show OCO capability status."""
    capability = OCOCapability()
    status_result = capability.status().to_dict()
    if json_output:
        _print(status_result, True)
        return

    console.print("[bold]OCO Status[/bold]")
    console.print(f"router_available: {status_result['router_available']}")
    console.print(f"adapter_available: {status_result['adapter_available']}")
    console.print(f"project_root: {status_result['health']['project_root']}")


@app.command()
def route(
    message: str = typer.Argument(..., help="User message to route."),
    sender_id: str = typer.Option("cli", "--sender-id", help="Sender/session identifier."),
    json_output: bool = typer.Option(False, "--json", help="Output machine-readable JSON."),
) -> None:
    """Run Router only and print the route decision."""
    capability = OCOCapability()
    decision = capability.route(message=message, sender_id=sender_id)
    if json_output:
        _print(decision, True)
        return

    console.print(f"path: [bold]{decision['path']}[/bold]")
    console.print(f"complexity: {decision['complexity']}")
    console.print(f"thread_id: {decision['thread_id']}")
    console.print(f"reasoning: {decision['reasoning']}")


@app.command()
def plan(
    goal: str = typer.Argument(..., help="Goal to plan without executing tools."),
    llm: bool = typer.Option(False, "--llm", help="Use configured LLM instead of deterministic offline planning."),
    json_output: bool = typer.Option(False, "--json", help="Output machine-readable JSON."),
) -> None:
    """Preview an OCO execution plan without tool execution."""
    capability = OCOCapability()
    result = capability.plan(goal=goal, use_llm=llm)
    if json_output:
        _print(result, True)
        return

    console.print(f"goal: [bold]{result['goal']}[/bold]")
    console.print(f"mode: {result['mode']}")
    console.print(f"route: {result['route']['path']} ({result['route']['complexity']})")
    table = Table(title="Plan")
    table.add_column("Task")
    table.add_column("Tool")
    table.add_column("Description")
    for item in result.get("plan", []):
        table.add_row(str(item.get("task_id")), str(item.get("tool")), str(item.get("description")))
    console.print(table)


@app.command()
def run(
    goal: str = typer.Argument(..., help="Goal to execute through the full OCO loop."),
    thread_id: Optional[str] = typer.Option(None, "--thread-id", help="Thread id for checkpoint isolation."),
    timeout: int = typer.Option(600, "--timeout", help="Execution timeout in seconds."),
    vector_store: bool = typer.Option(False, "--vector-store", help="Enable vector store during execution."),
    json_output: bool = typer.Option(False, "--json", help="Output machine-readable JSON."),
) -> None:
    """Run the full OCO loop through the existing adapter."""
    capability = OCOCapability()
    route_decision = capability.route(goal, sender_id="cli")
    resolved_thread_id = thread_id or route_decision["thread_id"] or "cli_default_thread"

    result = capability.run(
        goal=goal,
        thread_id=resolved_thread_id,
        context={"entrypoint": "cli", "route": route_decision},
        timeout=timeout,
        enable_vector_store=vector_store,
    )
    if json_output:
        _print(result, True)
        return

    console.print(result.get("response", result))


@app.command()
def tui(
    goal: Optional[str] = typer.Argument(None, help="Optional first task to run after the UI opens."),
    timeout: int = typer.Option(600, "--timeout", help="Execution timeout per task in seconds."),
    vector_store: bool = typer.Option(False, "--vector-store", help="Enable vector store during execution."),
) -> None:
    """Open the resident OCO workbench with a persistent input bar."""
    try:
        run_tui(goal, timeout=timeout, enable_vector_store=vector_store)
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc


@app.command()
def botmux(
    session_id: str = typer.Option(..., "--session-id", help="Botmux session id used as the OCO checkpoint thread id."),
    timeout: int = typer.Option(600, "--timeout", help="Execution timeout per turn in seconds."),
    vector_store: bool = typer.Option(False, "--vector-store", help="Enable vector store during execution."),
) -> None:
    """Run the persistent stdin/stdout bridge used by botmux."""
    runner = OCOBotmuxRunner(
        session_id=session_id,
        timeout=timeout,
        enable_vector_store=vector_store,
    )
    runner.serve(sys.stdin, sys.stdout)


@app.command()
def critic(
    goal: str = typer.Option(..., "--goal", help="Original goal."),
    output: Optional[str] = typer.Option(None, "--output", help="Output text to evaluate."),
    output_file: Optional[Path] = typer.Option(None, "--output-file", help="Read output text from file."),
    trace_file: Optional[Path] = typer.Option(None, "--trace", help="Optional trace JSON/JSONL file."),
    threshold: float = typer.Option(0.7, "--threshold", help="Pass threshold."),
    llm: bool = typer.Option(False, "--llm", help="Use configured LLM critic instead of offline heuristics."),
    json_output: bool = typer.Option(False, "--json", help="Output machine-readable JSON."),
) -> None:
    """Evaluate a result against the original goal."""
    if output_file:
        resolved_output = output_file.read_text(encoding="utf-8")
    else:
        resolved_output = output or ""

    capability = OCOCapability()
    trace = None
    if trace_file:
        trace = capability._load_trace(trace_file)
    result = capability.critic(
        goal=goal,
        output=resolved_output,
        trace=trace,
        threshold=threshold,
        use_llm=llm,
    )
    if json_output:
        _print(result, True)
        return

    status_text = "PASSED" if result["passed"] else "FAILED"
    console.print(f"[bold]{status_text}[/bold] score={result['score']} threshold={result['threshold']}")
    if result.get("issues"):
        console.print(f"issues: {', '.join(result['issues'])}")
    if result.get("recommendations"):
        console.print("recommendations:")
        for item in result["recommendations"]:
            console.print(f"- {item}")


@app.command("eval")
def eval_cases(
    dataset: Path = typer.Argument(..., help="JSON/JSONL dataset path."),
    mode: str = typer.Option("route", "--mode", help="Evaluation mode: route, plan, critic, run."),
    threshold: float = typer.Option(0.7, "--threshold", help="Critic pass threshold."),
    timeout: int = typer.Option(600, "--timeout", help="Run mode timeout in seconds."),
    json_output: bool = typer.Option(False, "--json", help="Output machine-readable JSON."),
) -> None:
    """Run a case set through route, plan, critic, or full run mode."""
    capability = OCOCapability()
    result = capability.eval(dataset_path=dataset, mode=mode, threshold=threshold, timeout=timeout)
    if json_output:
        _print(result, True)
        return

    console.print(f"dataset: {result['dataset']}")
    console.print(f"mode: {result['mode']}")
    console.print(f"passed: {result['passed']}/{result['total']} ({result['pass_rate']})")


@app.command()
def replay(
    trace: Path = typer.Argument(..., help="Trace JSON/JSONL file to replay."),
    json_output: bool = typer.Option(False, "--json", help="Output machine-readable JSON."),
) -> None:
    """Summarize a trace and expose replayable state."""
    capability = OCOCapability()
    result = capability.replay(trace_path=trace)
    if json_output:
        _print(result, True)
        return

    console.print(f"trace: {result['trace_path']}")
    console.print(f"events: {result['event_count']}")
    console.print(f"replayable: {result['replayable']}")
    console.print(f"failures: {result['failure_count']}")
    if result.get("goal"):
        console.print(f"goal: {result['goal']}")
    if result.get("stages"):
        table = Table(title="Stages")
        table.add_column("Stage")
        table.add_column("Count")
        for stage, count in result["stages"].items():
            table.add_row(stage, str(count))
        console.print(table)


if __name__ == "__main__":
    app()
