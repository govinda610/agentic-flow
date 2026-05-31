# Extending the Platform

How to add new workflow templates, wire in a new messaging channel, and register new tools.

## 1. Adding a workflow template

Templates are JSON files in `backend/templates/`, seeded into the database on startup by
`seed_templates()`.

1. Create a new file, e.g. `backend/templates/my_workflow.json`.
2. Follow the schema below. The **template slug** is the filename stem (`my_workflow.json` →
   slug `my_workflow`).
3. Restart the backend — `seed_templates()` picks up new files automatically.

### Schema shape

```json
{
  "name": "My Workflow",
  "description": "What this workflow does.",
  "recursion_limit": 50,
  "nodes": [
    { "id": "node_start", "type": "start", "position": {"x": 50, "y": 200},
      "config": {"label": "Start"} },

    { "id": "node_writer", "type": "agent", "position": {"x": 300, "y": 200},
      "config": {
        "name": "Writer",
        "system_prompt": "Write a clear article on the topic.",
        "tools": [],
        "structured_output": null
      } },

    { "id": "node_end", "type": "end", "position": {"x": 600, "y": 200},
      "config": {"label": "End"} }
  ],
  "edges": [
    {"id": "e1", "source": "node_start",  "target": "node_writer", "type": "normal", "condition": null},
    {"id": "e2", "source": "node_writer", "target": "node_end",    "type": "normal", "condition": null}
  ]
}
```

### Node `type` values

| Type | Purpose |
|---|---|
| `start` / `end` | Graph entry / exit (exactly one each) |
| `simple_llm` | Single LLM call with a system prompt |
| `agent` | Tool-using ReAct agent; supports `structured_output` |
| `deep_agent` | Agent with filesystem, memory, and skills (`max_depth`, `max_breadth`) |
| `supervisor` | Routes to named child specialist agents |
| `human_chat` | Pauses for human input via `interrupt()` |
| `telegram_output` | Delivers the resolved message to the Telegram chat |
| `webhook_trigger` | Entry point triggered by an external webhook |
| `subgraph` | Embeds another saved workflow as a node (`config.workflow_id`) |

### Edge `type` values

| Type | Behaviour |
|---|---|
| `normal` | Unconditional fallback |
| `conditional` | Followed when its `condition` expression is true (evaluated against `state`) |
| `error` | Followed when the source node raised an error |
| `parallel_fan_out` | Iterates an array field (`fan_out_from`) into parallel branches |
| `parallel_fan_in` | Aggregates parallel branch results |

### Structured output

To make a node return typed fields (required for conditional edges that read them):

```json
"structured_output": {
  "fields": [
    {"name": "is_approved", "type": "boolean"},
    {"name": "feedback", "type": "string"}
  ]
}
```

Supported types: `string`, `boolean`, `integer`, `number`, `array`.

## 2. Adding a messaging channel

The Telegram gateway is the reference implementation. To add another channel (e.g. Slack or
WhatsApp), follow the same shape.

1. **Implement the gateway.** Subclass `BaseMessagingGateway` (`backend/gateway/base.py`) and
   implement `start()`, `stop()`, `send_message()`, and `register_workflow()`. Use
   `backend/gateway/telegram.py` as the template.
2. **Route inbound messages to the runtime.** On an incoming message, call
   `engine.runner.start_run(workflow_id=..., initial_input={"message": text, ...},
   <channel>_chat_id=...)`. To support replies to paused runs, look up the most recent
   `paused` run for that chat and call `resume_run(run_id, text)` instead.
3. **Hold a process-wide handle.** Store the live gateway in a module like
   `backend/gateway/state.py` so node functions (e.g. `telegram_output`) can reach it to send
   messages.
4. **Start it in the lifespan.** In `backend/main.py`, start your gateway inside the `lifespan`
   startup block (guarded by its config token) and stop it on shutdown — exactly as the
   Telegram gateway is wired today.
5. **Persist the channel id on the run.** Add the chat id to the run record / state so outbound
   nodes and HITL resume can target the right conversation.

Because every channel ultimately calls the same `start_run` / `resume_run`, the runtime,
persistence, and UI need no changes — only the new gateway file plus a few lines in `main.py`.

## 3. Adding a tool

Built-in tools are registered in `BUILTIN_TOOL_FACTORIES` in `backend/engine/parser.py`. Each
entry is `name → factory(ctx)` returning a LangChain tool. A node opts in by listing the tool
name in its `config.tools`.

User-defined tools are persisted as **capabilities** (`backend/models/capability.py`) and
loaded at startup via `engine/user_tools.py` (`load_user_tool`, `load_mcp_server_map`), which
are wired into the resolver in `main.py`. MCP servers are integrated the same way through
`langchain-mcp-adapters`.

## 4. Adding a node type

1. Add a node function file under `backend/engine/nodes/`.
2. Register the new `type` in `WorkflowParser` (`backend/engine/parser.py`) so the compiler maps
   it to your function.
3. Add the type to the frontend `nodeTypes` map and the palette
   (`frontend/src/components/canvas/`) so users can drag it onto the canvas.
