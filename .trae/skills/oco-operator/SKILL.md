---
name: "oco-operator"
description: "Operates Project Omega OCO through its CLI. Invoke when routing, checking, running, or validating OCO Agent tasks."
---

# OCO Operator

Use this skill when the user asks to work with Project Omega OCO, including:

- Checking OCO runtime health or dependency status.
- Routing a task through OCO Router.
- Running a task through the OCO cognitive loop.
- Validating the persistent OCO runner used by botmux for Feishu sessions.
- Verifying whether OCO is ready for CLI, MCP, Harness, or Critic integration.
- Debugging the public OCO capability surface before deeper code changes.

## Operating Principle

Do not treat this Skill as the execution logic. The Skill is only an entry instruction layer.

Actual control and execution must go through:

```text
OCO CLI -> OCO Capability Interface -> Router -> Planner -> Executor(MCP) -> Critic
```

This keeps the prompt layer small and prevents long Skill instructions from becoming the control plane.

## Commands

Run all commands from the repository root:

```bash
cd /Users/bytedance/VO/QY/LBE/AI_Ori/Project_Omega_OCO
```

Check health:

```bash
oco health --json
```

Check public capability status:

```bash
oco status --json
```

Route without executing:

```bash
oco route "用户输入" --json
```

Run the full loop:

```bash
oco run "复杂任务" --timeout 600 --json
```

Start the botmux runner (normally launched by botmux, not by a human):

```bash
oco botmux --session-id <botmux-session-id>
```

Feishu transport, credentials, permissions, cards, and topic lifecycle belong
to botmux. Do not create or invoke an OCO-owned Feishu webhook server.

Preview a plan without executing tools:

```bash
oco plan "复杂任务" --json
```

Evaluate an output with the Critic gate:

```bash
oco critic --goal "原始目标" --output "执行结果" --json
```

Run eval cases:

```bash
oco eval tests/fixtures/eval_cases.jsonl --mode route --json
oco eval tests/fixtures/eval_cases.jsonl --mode critic --json
```

Replay a trace:

```bash
oco replay tests/fixtures/trace_sample.jsonl --json
```

## Safety Rules

- Prefer `oco route` before `oco run` when the user is exploring behavior.
- Prefer `oco plan`, `oco critic`, `oco eval`, and `oco replay` when validating behavior without needing a live LLM/MCP environment.
- Prefer `--json` when another Agent, MCP wrapper, or test will consume the output.
- Do not bypass the CLI by calling internal modules unless the user explicitly asks for code-level debugging.
- Do not run destructive shell commands as part of an OCO task unless the user explicitly approves them.
- If MCP tools are unavailable, report the capability gap instead of inventing tool results.

## Expected Use

Use this Skill as a bridge between user intent and the OCO engineering interface:

```text
User request -> route -> plan -> inspect decision -> run/eval/replay if appropriate -> summarize result
```

If the user asks for publication readiness, check:

```bash
oco health --json
oco status --json
pytest tests/test_router.py tests/test_state.py tests/test_capability_cli_contract.py tests/test_botmux_bridge.py
```
