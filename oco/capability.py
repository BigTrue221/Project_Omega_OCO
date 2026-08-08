# -*- coding: utf-8 -*-
"""Stable capability interface for the OCO runtime.

This module is intentionally thin. It exposes the existing research modules
through a small, typed contract that can be called by CLI, botmux, MCP wrappers,
tests, and future UI surfaces.
"""

from __future__ import annotations

import importlib.util
from importlib import import_module
import json
import os
import platform
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_dotenv_if_present() -> None:
    """Load project-local configuration without overriding the shell."""
    env_path = PROJECT_ROOT / ".env"
    if not env_path.is_file():
        return
    try:
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except OSError:
        pass


_load_dotenv_if_present()


@dataclass
class OCOHealth:
    ok: bool
    python: str
    project_root: str
    mcp_package: bool
    langgraph_package: bool
    local_llm_url: str
    use_cloud_llm: bool
    openrouter_key_configured: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class OCOStatus:
    health: OCOHealth
    router_available: bool
    adapter_available: bool
    vector_store_enabled_by_default: bool

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["health"] = self.health.to_dict()
        return data


class OCOCapability:
    """Unified local capability facade for Project Omega OCO."""

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = Path(project_root or PROJECT_ROOT)
        # Keep one adapter per capability lifetime.  This matters for resident
        # surfaces (TUI/botmux): the graph/checkpoint connection and MCP
        # sessions should not be rebuilt for every turn.
        self._adapter = None
        self._adapter_vector_store: Optional[bool] = None

    def health(self) -> OCOHealth:
        mcp_package = importlib.util.find_spec("mcp") is not None
        langgraph_package = importlib.util.find_spec("langgraph") is not None
        use_cloud_llm = os.getenv("USE_CLOUD_LLM", "false").lower() == "true"
        openrouter_key = bool(os.getenv("OPENROUTER_API_KEY"))

        return OCOHealth(
            ok=True,
            python=f"{platform.python_implementation()} {platform.python_version()}",
            project_root=str(self.project_root),
            mcp_package=mcp_package,
            langgraph_package=langgraph_package,
            local_llm_url=os.getenv("OCO_LOCAL_LLM_URL", "http://127.0.0.1:8081/v1/chat/completions"),
            use_cloud_llm=use_cloud_llm,
            openrouter_key_configured=openrouter_key,
        )

    def status(self) -> OCOStatus:
        return OCOStatus(
            health=self.health(),
            router_available=self._module_available("router"),
            adapter_available=self._module_available("adapter"),
            vector_store_enabled_by_default=True,
        )

    def route(self, message: str, sender_id: str = "cli", context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self._ensure_project_on_path()
        route_message = self._import_symbol("router", "route_message")

        decision = route_message(message, sender_id, context or {})
        return {
            "path": decision.path.value,
            "thread_id": decision.thread_id,
            "complexity": decision.complexity.value,
            "reasoning": decision.reasoning,
            "metadata": decision.metadata,
        }

    def run(
        self,
        goal: str,
        thread_id: str,
        context: Optional[Dict[str, Any]] = None,
        timeout: int = 600,
        enable_vector_store: bool = False,
        progress_callback: Optional[Callable[[str, str, float], None]] = None,
    ) -> Dict[str, Any]:
        """Run the full OCO loop through the existing adapter.

        Vector store is disabled by default for CLI execution because public
        setup should work before ChromaDB is configured.
        """
        self._ensure_project_on_path()
        OCOCognitiveLoopAdapter = self._import_symbol("adapter", "OCOCognitiveLoopAdapter")

        if (
            self._adapter is None
            or not getattr(self._adapter, "initialized", False)
            or self._adapter_vector_store != enable_vector_store
        ):
            if self._adapter is not None:
                try:
                    self._adapter.close()
                except Exception:
                    pass
            self._adapter = OCOCognitiveLoopAdapter(enable_vector_store=enable_vector_store)
            self._adapter_vector_store = enable_vector_store

        adapter = self._adapter
        if not adapter.initialized:
            return {
                "success": False,
                "error": "OCO adapter failed to initialize",
                "response": "OCO adapter failed to initialize. Run `oco health --json` and check dependencies.",
            }
        return adapter.run(
            goal=goal,
            thread_id=thread_id,
            context=context or {},
            timeout=timeout,
            progress_callback=progress_callback,
        )

    def close(self) -> None:
        """Release a resident adapter and its MCP/checkpoint resources."""
        if self._adapter is not None:
            try:
                self._adapter.close()
            finally:
                self._adapter = None
                self._adapter_vector_store = None

    def plan(
        self,
        goal: str,
        context: Optional[Dict[str, Any]] = None,
        use_llm: bool = False,
    ) -> Dict[str, Any]:
        """Generate a plan preview without executing tools.

        The default path is deterministic and offline so eval/replay can run in
        clean GitHub environments. Set use_llm=True to ask the configured LLM for
        a richer plan.
        """
        route_decision = self.route(goal, sender_id="cli", context=context or {})
        if use_llm:
            return self._llm_plan(goal=goal, route_decision=route_decision, context=context or {})

        if route_decision["path"] == "legacy":
            plan = [
                {
                    "task_id": "direct_response",
                    "description": "Handle as a lightweight conversational response without entering the full OCO loop.",
                    "tool": "DIRECT_RESPONSE",
                    "params": {"reason": route_decision["reasoning"]},
                }
            ]
        else:
            plan = [
                {
                    "task_id": "route_context",
                    "description": "Confirm route decision, thread id, and task boundary.",
                    "tool": "ROUTER",
                    "params": {"path": route_decision["path"], "thread_id": route_decision["thread_id"]},
                },
                {
                    "task_id": "discover_capabilities",
                    "description": "Discover available MCP tools before execution.",
                    "tool": "MCP_DISCOVERY",
                    "params": {},
                },
                {
                    "task_id": "execute_subtasks",
                    "description": "Execute the task through MCP-backed Executor nodes.",
                    "tool": "MCP_EXECUTOR",
                    "params": {"goal": goal},
                },
                {
                    "task_id": "critic_gate",
                    "description": "Evaluate output against the original goal before final aggregation.",
                    "tool": "CRITIC",
                    "params": {"threshold": 0.7},
                },
            ]

        return {
            "goal": goal,
            "mode": "offline",
            "route": route_decision,
            "plan": plan,
        }

    def critic(
        self,
        goal: str,
        output: str,
        trace: Optional[Dict[str, Any]] = None,
        threshold: float = 0.7,
        use_llm: bool = False,
    ) -> Dict[str, Any]:
        """Evaluate output quality against the original goal."""
        if use_llm:
            return self._llm_critic(goal=goal, output=output, trace=trace, threshold=threshold)

        issues: List[str] = []
        recommendations: List[str] = []
        normalized_output = output.strip()
        normalized_goal = goal.strip()

        score = 0.0
        if normalized_output:
            score += 0.35
        else:
            issues.append("empty_output")
            recommendations.append("Produce a non-empty result before accepting the task.")

        error_markers = ["error", "exception", "traceback", "失败", "错误", "未初始化", "capability_missing"]
        if any(marker in normalized_output.lower() for marker in error_markers):
            score -= 0.25
            issues.append("error_marker_detected")
            recommendations.append("Inspect execution errors before accepting the result.")

        goal_tokens = self._tokenize(normalized_goal)
        output_tokens = self._tokenize(normalized_output)
        overlap = len(goal_tokens & output_tokens)
        if goal_tokens:
            overlap_ratio = overlap / max(len(goal_tokens), 1)
            score += min(overlap_ratio, 1.0) * 0.25
            if overlap_ratio < 0.1:
                issues.append("low_goal_overlap")
                recommendations.append("Check whether the output actually addresses the original goal.")
        else:
            score += 0.1

        if len(normalized_output) >= 80:
            score += 0.15
        else:
            issues.append("short_output")
            recommendations.append("Output is very short; verify whether it is sufficient.")

        if trace:
            score += 0.10
            if self._trace_has_failure(trace):
                score -= 0.20
                issues.append("trace_failure_detected")
                recommendations.append("Replay the failed trace and rerun from the failed stage.")

        score = max(0.0, min(1.0, score))
        return {
            "goal": goal,
            "mode": "offline",
            "score": round(score, 4),
            "threshold": threshold,
            "passed": score >= threshold,
            "issues": issues,
            "recommendations": recommendations,
        }

    def eval(
        self,
        dataset_path: Path,
        mode: str = "route",
        threshold: float = 0.7,
        timeout: int = 600,
    ) -> Dict[str, Any]:
        """Run a JSON/JSONL case set through route, plan, critic, or run mode."""
        cases = list(self._load_cases(Path(dataset_path)))
        results = []
        passed = 0

        for index, case in enumerate(cases):
            case_id = str(case.get("id", f"case_{index + 1}"))
            goal = case.get("goal") or case.get("input") or case.get("message") or ""
            output = case.get("output") or case.get("actual") or ""
            expected_path = case.get("expected_path")

            if not goal:
                result = {
                    "id": case_id,
                    "passed": False,
                    "error": "missing goal/input/message",
                }
                results.append(result)
                continue

            if mode == "route":
                route_result = self.route(goal, sender_id=case_id, context=case.get("context") or {})
                case_passed = expected_path is None or route_result["path"] == expected_path
                result = {"id": case_id, "mode": mode, "passed": case_passed, "route": route_result}
            elif mode == "plan":
                plan_result = self.plan(goal, context=case.get("context") or {})
                case_passed = bool(plan_result.get("plan"))
                result = {"id": case_id, "mode": mode, "passed": case_passed, "plan": plan_result}
            elif mode == "critic":
                critic_result = self.critic(goal, output, trace=case.get("trace"), threshold=threshold)
                case_passed = critic_result["passed"]
                result = {"id": case_id, "mode": mode, "passed": case_passed, "critic": critic_result}
            elif mode == "run":
                route_result = self.route(goal, sender_id=case_id, context=case.get("context") or {})
                thread_id = case.get("thread_id") or route_result["thread_id"] or case_id
                run_result = self.run(goal, thread_id=thread_id, context=case.get("context") or {}, timeout=timeout)
                case_passed = bool(run_result.get("success"))
                result = {"id": case_id, "mode": mode, "passed": case_passed, "run": run_result}
            else:
                raise ValueError(f"Unsupported eval mode: {mode}")

            if case_passed:
                passed += 1
            results.append(result)

        total = len(results)
        return {
            "dataset": str(dataset_path),
            "mode": mode,
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate": round(passed / total, 4) if total else 0.0,
            "results": results,
        }

    def replay(self, trace_path: Path) -> Dict[str, Any]:
        """Load a trace JSON/JSONL file and summarize replayable state."""
        trace_file = Path(trace_path)
        trace = self._load_trace(trace_file)
        events = self._extract_events(trace)

        stages: Dict[str, int] = {}
        failures: List[Dict[str, Any]] = []
        final_response = None
        goal = None

        for event in events:
            stage = str(event.get("stage") or event.get("node") or event.get("event") or "unknown")
            stages[stage] = stages.get(stage, 0) + 1
            if event.get("goal") and not goal:
                goal = event.get("goal")
            if event.get("final_response"):
                final_response = event.get("final_response")
            text = json.dumps(event, ensure_ascii=False, default=str).lower()
            if any(marker in text for marker in ["error", "exception", "failed", "失败", "错误"]):
                failures.append(event)

        if isinstance(trace, dict):
            goal = goal or trace.get("goal")
            context = trace.get("context") or {}
            final_response = final_response or context.get("final_response") or trace.get("final_response")

        return {
            "trace_path": str(trace_file),
            "event_count": len(events),
            "stages": stages,
            "goal": goal,
            "final_response": final_response,
            "failure_count": len(failures),
            "failures": failures[:10],
            "replayable": len(events) > 0 or isinstance(trace, dict),
        }

    def _module_available(self, module_name: str) -> bool:
        self._ensure_project_on_path()
        try:
            return importlib.util.find_spec(module_name) is not None
        except (ImportError, AttributeError, ValueError):
            return False

    def _ensure_project_on_path(self) -> None:
        for path in (str(self.project_root.parent), str(self.project_root)):
            if path not in sys.path:
                sys.path.insert(0, path)

    def _import_symbol(self, module_name: str, symbol_name: str):
        errors = []
        for candidate in (f"Project_Omega_OCO.{module_name}", module_name):
            try:
                module = import_module(candidate)
                return getattr(module, symbol_name)
            except Exception as exc:
                errors.append(f"{candidate}: {exc}")
        raise ImportError(f"Unable to import {symbol_name} from {module_name}. Attempts: {'; '.join(errors)}")

    def _llm_plan(self, goal: str, route_decision: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        LLMClient = self._import_symbol("core.llm", "LLMClient")
        llm = LLMClient()
        result = llm.generate_json(
            system_prompt=(
                "You are the OCO planner. Return strict JSON with a 'plan' array. "
                "Each item must include task_id, description, tool, and params."
            ),
            user_prompt=f"Goal: {goal}\nRoute: {route_decision}\nContext: {context}",
        )
        return {
            "goal": goal,
            "mode": "llm",
            "route": route_decision,
            "plan": result.get("plan", []),
            "raw": result,
        }

    def _llm_critic(
        self,
        goal: str,
        output: str,
        trace: Optional[Dict[str, Any]],
        threshold: float,
    ) -> Dict[str, Any]:
        LLMClient = self._import_symbol("core.llm", "LLMClient")
        llm = LLMClient()
        result = llm.generate_json(
            system_prompt=(
                "You are the OCO Critic gate. Return strict JSON with fields: "
                "score (0-1), passed (bool), issues (array), recommendations (array)."
            ),
            user_prompt=f"Goal: {goal}\nOutput: {output}\nTrace: {trace}\nThreshold: {threshold}",
        )
        score = float(result.get("score", 0.0) or 0.0)
        return {
            "goal": goal,
            "mode": "llm",
            "score": score,
            "threshold": threshold,
            "passed": bool(result.get("passed", score >= threshold)),
            "issues": result.get("issues", []),
            "recommendations": result.get("recommendations", []),
            "raw": result,
        }

    def _load_cases(self, dataset_path: Path) -> Iterable[Dict[str, Any]]:
        if not dataset_path.exists():
            raise FileNotFoundError(f"Dataset not found: {dataset_path}")
        text = dataset_path.read_text(encoding="utf-8").strip()
        if not text:
            return []
        if dataset_path.suffix.lower() == ".jsonl":
            return [json.loads(line) for line in text.splitlines() if line.strip()]
        data = json.loads(text)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and isinstance(data.get("cases"), list):
            return data["cases"]
        raise ValueError("Dataset must be a JSON array, {'cases': [...]}, or JSONL file.")

    def _load_trace(self, trace_path: Path) -> Any:
        if not trace_path.exists():
            raise FileNotFoundError(f"Trace not found: {trace_path}")
        text = trace_path.read_text(encoding="utf-8").strip()
        if not text:
            return []
        if trace_path.suffix.lower() == ".jsonl":
            return [json.loads(line) for line in text.splitlines() if line.strip()]
        return json.loads(text)

    def _extract_events(self, trace: Any) -> List[Dict[str, Any]]:
        if isinstance(trace, list):
            return [event for event in trace if isinstance(event, dict)]
        if isinstance(trace, dict):
            for key in ("events", "trace", "cognitive_trace"):
                value = trace.get(key)
                if isinstance(value, list):
                    return [
                        event if isinstance(event, dict) else {"event": str(event)}
                        for event in value
                    ]
            return [trace]
        return [{"event": str(trace)}]

    def _trace_has_failure(self, trace: Dict[str, Any]) -> bool:
        text = json.dumps(trace, ensure_ascii=False, default=str).lower()
        return any(marker in text for marker in ["error", "exception", "failed", "失败", "错误"])

    def _tokenize(self, text: str) -> set[str]:
        normalized = text.lower()
        tokens = []
        current = []
        for char in normalized:
            if char.isalnum() or "\u4e00" <= char <= "\u9fff":
                current.append(char)
            elif current:
                tokens.append("".join(current))
                current = []
        if current:
            tokens.append("".join(current))
        return set(tokens)
