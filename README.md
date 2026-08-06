# Project Omega OCO

Project Omega OCO (Omega Cognitive Object) is an experimental Agent engineering runtime built around an explicit cognitive loop:

```text
Router -> Planner -> Executor(MCP) -> Critic -> Aggregator
```

The project does not treat long prompt-based skills as the core control layer. Instead, it separates:

- **Control plane**: Router, LangGraph state machine, Planner, Critic.
- **Execution plane**: MCP client and MCP servers.
- **Governance layer**: Harness-style pre/post checks, trace, validation, retry, and quality gate.

The design goal is not to make LLM hallucination disappear. The goal is to prevent hallucination from directly owning the control flow, tool execution, and final acceptance decision.

## Status

This repository is an early public整理 of the Project Omega OCO prototype.

Stable entry points added for publication:

- `oco health`
- `oco status`
- `oco route`
- `oco plan`
- `oco run`
- `oco botmux`
- `oco critic`
- `oco eval`
- `oco replay`
- `.trae/skills/oco-operator/SKILL.md`

Some historical files are still research notes and debug records. Treat the CLI and `oco.capability` as the public integration surface.

## Architecture

```text
Human / Feishu
       |
       v
 botmux daemon
       |
       v
oco botmux runner / CLI / MCP wrapper
       |
       v
 OCO Capability Interface
              |
              v
           Router
              |
              v
          Planner
              |
              v
      Executor through MCP
              |
              v
           Critic
              |
     pass ----+---- fail
      |              |
      v              v
  Aggregator      Planner
```

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Check runtime:

```bash
oco health
oco status --json
```

Route a task without running the full graph:

```bash
oco route "写一个科幻小说大纲"
oco route "你好" --json
```

Preview a deterministic execution plan:

```bash
oco plan "写一个科幻小说大纲" --json
```

Run the full cognitive loop:

```bash
oco run "分析这个任务并给出执行方案" --timeout 600
```

## Feishu Through botmux

OCO does not own Feishu credentials, webhooks, tunnels, cards, or topic
sessions. Those transport responsibilities belong to botmux. The integration
boundary is a persistent runner:

```text
Feishu -> botmux daemon -> oco botmux -> OCO cognitive loop
```

Install OCO and botmux, then configure a bot with the native `oco` adapter:

```bash
pip install -e ".[dev]"
npm install -g botmux

botmux setup add \
  --app-id "$LARK_APP_ID" \
  --app-secret "$LARK_APP_SECRET" \
  --allowed-users "$OCO_OWNER" \
  --cli oco \
  --cli-path "$(command -v oco)" \
  --default-working-dir "$PWD"

botmux start
```

The equivalent `bots.json` fields are:

```json
{
  "cliId": "oco",
  "cliPathOverride": "/absolute/path/to/oco",
  "defaultWorkingDir": "/absolute/path/to/Project_Omega_OCO"
}
```

Each botmux session ID is reused as the OCO checkpoint `thread_id`, so follow-up
messages in the same Feishu topic continue the same cognitive state. Do not add
Feishu credentials to the OCO `.env`.

By default, `oco run` disables vector store initialization to keep the first run lightweight. Enable it explicitly:

```bash
oco run "检索长期记忆并生成方案" --vector-store
```

Evaluate output with the Critic gate:

```bash
oco critic --goal "分析 OCO 架构" --output "这里是执行结果" --json
```

Run offline eval cases:

```bash
oco eval tests/fixtures/eval_cases.jsonl --mode route --json
oco eval tests/fixtures/eval_cases.jsonl --mode critic --json
```

Replay a trace:

```bash
oco replay tests/fixtures/trace_sample.jsonl --json
```

## Runtime Requirements

Minimum:

- Python 3.10+
- `langgraph`
- `langgraph-checkpoint-sqlite`
- `mcp`
- `typer`
- `rich`

Optional:

- ChromaDB for L3 vector memory.
- Local OpenAI-compatible `llama.cpp` server at `http://127.0.0.1:8081/v1/chat/completions` (default).
- Optional Ollama native chat API at `http://127.0.0.1:11434/api/chat`.
- OpenRouter-compatible cloud model if `USE_CLOUD_LLM=true`.

Copy `.env.example` if you need local configuration:

```bash
cp .env.example .env
```

The default local backend is llama.cpp. To opt into Ollama, set:

```bash
OCO_LOCAL_LLM_PROVIDER=ollama
OCO_LOCAL_LLM_URL=http://127.0.0.1:11434/api/chat
OCO_LOCAL_LLM_MODEL=ollama/dolphin3-mistral-32k:latest
OCO_OLLAMA_NUM_CTX=2048
OCO_OLLAMA_TIMEOUT=300
```

Ollama uses its native response format and strips the optional `ollama/` model
prefix before sending the request. Existing llama.cpp settings remain the
baseline when `OCO_LOCAL_LLM_PROVIDER` is not `ollama`.

## CLI Contract

The CLI is intentionally designed as an Agent-facing engineering interface, not just a human shell shortcut.

```bash
oco health --json
oco status --json
oco route "用户输入" --json
oco plan "复杂任务" --json
oco run "复杂任务" --thread-id demo --json
oco critic --goal "原始目标" --output-file result.md --json
oco eval cases.jsonl --mode route --json
oco replay trace.jsonl --json
```

The expected long-term contract is:

```text
route(input, context) -> RouteDecision
plan(goal, context) -> Plan
run(goal, mode, context) -> TaskResult
critic(goal, output, trace) -> CriticResult
eval(dataset, config) -> EvalReport
replay(trace_id) -> ReplayResult
status() -> SystemStatus
```

The current code implements the first replayable layer: `route`, `plan`, `run`, `critic`, `eval`, `replay`, `health`, and `status`.

## Trae Skill

This repository includes a local Trae Skill:

```text
.trae/skills/oco-operator/SKILL.md
```

The Skill tells an AI assistant when to use OCO CLI commands for routing, health checks, and controlled execution. It keeps Skill as an entry instruction layer while the actual control and execution remain in OCO/MCP/Harness/Critic.

## Tests

Run lightweight tests:

```bash
pytest tests/test_router.py tests/test_state.py
pytest tests/test_capability_cli_contract.py
```

Some integration tests require a configured local model, MCP servers, or vector database. They are kept as reference tests and may need environment setup before running.

## Publication Notes

Before pushing to GitHub:

```bash
find . -name "__pycache__" -type d -prune -print
find . -name "*.sqlite*" -o -name "*.log" -o -name "*.pid"
```

Do not publish `.env`, credentials, local checkpoints, local vector stores, logs, or generated cache files.

## License

MIT. See `LICENSE`.
