# OCO + botmux 飞书全链路测试计划

## 1. 测试目标

验证用户从飞书发起任务后，botmux 完成消息接入、话题会话和结果回传，
OCO 完成路由、认知闭环、MCP 工具执行与 checkpoint 续传。

OCO 不再直接持有飞书凭证，不启动 webhook 服务，也不依赖 Cloudflare Tunnel。

## 2. 链路拓扑

```text
飞书用户
  -> botmux 长连接
  -> botmux oco adapter
  -> oco botmux --session-id <botmux_session_id>
  -> OCO Capability
  -> Router -> Planner -> Executor(MCP) -> Critic -> Aggregator
  -> botmux 流式卡片 / 最终消息
  -> 飞书用户
```

职责边界：

| 组件 | 职责 |
|---|---|
| botmux | 飞书凭证、长连接、权限、话题、卡片、tmux 会话和消息回传 |
| OCO runner | botmux stdin/stdout 协议、进度输出、最终结果 OSC marker |
| OCO Capability | 路由、执行、checkpoint 和结果构建 |
| MCP servers | 工具发现与执行 |

## 3. 前置条件

- Python 3.10+
- Node.js 22+
- tmux 3.x
- OCO 已安装：`pip install -e ".[dev]"`
- botmux 版本包含原生 `oco` adapter
- 飞书应用已通过 `botmux setup` 配置并发布
- 需要执行复杂任务时，本地模型和 MCP servers 已就绪

## 4. 配置

通过 setup 创建或编辑机器人：

```bash
botmux setup add \
  --app-id "$LARK_APP_ID" \
  --app-secret "$LARK_APP_SECRET" \
  --allowed-users "$OCO_OWNER" \
  --cli oco \
  --cli-path "$(command -v oco)" \
  --default-working-dir "$PWD"
```

关键 `bots.json` 字段：

```json
{
  "cliId": "oco",
  "cliPathOverride": "/absolute/path/to/oco",
  "defaultWorkingDir": "/absolute/path/to/Project_Omega_OCO"
}
```

禁止把 `LARK_APP_ID`、`LARK_APP_SECRET` 或 webhook token 写入 OCO `.env`。

## 5. 启动与健康检查

```bash
oco health --json
oco status --json
botmux start
botmux status
```

确认 botmux 日志中没有以下错误：

- `Unknown CLI adapter: oco`
- `Could not find the local OCO executable`
- `OCO readyPattern did not arrive`
- `OCO exited`

## 6. 测试用例

| ID | 操作 | 预期结果 |
|---|---|---|
| FT-01 | 飞书发送“写一个赛博朋克侦探小说大纲” | botmux 创建 OCO 会话，卡片显示进度，最终收到大纲 |
| FT-02 | 在同一话题发送“增加一个反转” | 复用相同 botmux session ID 和 OCO checkpoint thread |
| FT-03 | 在新话题发送另一任务 | 创建新的 session ID，不串用旧 checkpoint |
| FT-04 | 发送多行中文任务 | runner base64 协议完整保留换行和 Unicode |
| FT-05 | 执行中重启 botmux daemon | tmux 内 OCO runner 保持存活，恢复后继续回传 |
| FT-06 | MCP 不可用时发送复杂任务 | OCO 返回明确能力缺失，不无限重试 |
| FT-07 | 未授权用户在群内触发 | botmux 权限层拒绝，OCO runner 不收到消息 |

## 7. 证据采集

```bash
botmux logs
botmux list
oco health --json
```

每个通过用例至少保留：

1. 飞书触发消息 ID / 话题。
2. botmux session ID。
3. OCO 进度和最终结果。
4. 同话题续传时 thread ID 未变化的证据。
5. MCP 工具调用与 Critic 结果。

## 8. 自动化回归

OCO：

```bash
pytest tests/test_botmux_bridge.py tests/test_capability_cli_contract.py
```

botmux：

```bash
pnpm vitest run --project unit \
  test/cli-adapters.test.ts \
  test/write-input.test.ts \
  test/bot-config-editor.test.ts \
  test/card-builder.test.ts
pnpm build
```

## 9. 验收标准

- OCO 仓库不存在现役飞书 webhook 服务或凭证配置。
- botmux 能选择 `cliId: "oco"` 并拉起 runner。
- 首轮、多轮、跨话题隔离、异常回传均通过。
- 飞书最终答复由 botmux 发出，OCO 只输出 runner 协议。
