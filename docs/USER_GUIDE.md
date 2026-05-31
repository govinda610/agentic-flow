# User Guide

This guide walks an end user through building, running, and monitoring multi-agent workflows
in Agentic Flow. No coding is required.

## 1. The workspace

When you open http://localhost:5173 you see four areas:

- **Node palette (left)** — draggable building blocks: Flow Control (Start / End), Standard
  Nodes (agents and outputs), Templates, and your saved workflows.
- **Canvas (center)** — where you draw the workflow by dragging nodes and connecting them.
- **Right panel** — toggles between the **Simulated Gateway** chat and the **Design Copilot**.
- **Top bar** — workflow name, max-steps limit, and the New / Library / Save / Export / Run
  controls.

## 2. Building a workflow by hand

1. **Drag a Start node** from *Flow Control* onto the canvas. Every workflow needs exactly one
   Start and one End — they define the entry and exit of the graph.
2. **Drag the agents you need** from *Standard Nodes*:
   - `simple_llm` — a single LLM call with a system prompt.
   - `agent` — a tool-using agent; can return structured output.
   - `deep_agent` — an agent with a filesystem, memory, and skills for longer tasks.
   - `supervisor` — routes work to named child specialists.
   - `human_chat` — pauses the run and waits for a human reply.
   - `telegram_output` — delivers the result to a Telegram chat.
3. **Connect nodes** by dragging from one node's handle to the next. Wire `Start → … → End`.
4. **Configure a node** by clicking it. In the inspector you can set its name, system prompt,
   tools, and (for agents) a structured-output schema.
5. **Name the workflow** in the top bar, set **Max steps** if needed, and click **Save**. If
   you leave the name as "Untitled Workflow", Save will prompt you for a name.

> **Removing a node:** select it on the canvas and press **Delete** or **Backspace**.

## 3. Building a workflow with the Copilot

Open the **Copilot** tab and describe what you want in plain English, e.g.:

> "A researcher agent that feeds into a summary writer, then notify me via Telegram."

The Copilot generates the full workflow JSON, lays it out automatically on the canvas, and
**auto-saves** it so it is immediately runnable.

The Copilot is **canvas-aware**: if a workflow is already on the canvas, your message is
treated as an *edit*. For example, with a workflow open you can say:

> "Add a fact-checker between the researcher and the writer."

and it returns the full updated workflow, preserving the parts you didn't ask to change.

## 4. Conditional edges and feedback loops

Conditional edges let a workflow branch or loop based on an agent's output.

1. Give the deciding agent a **structured output** with a boolean field (e.g. an approver
   agent with `is_approved`). Note the node's id (snake_case, shown in the inspector).
2. Click the edge you want to make conditional. In the **Edge inspector**, choose
   **Conditional** and enter an expression evaluated against the run state, for example:

   ```
   state['node_outputs']['node_verifier']['is_approved'] == True
   ```
3. Add a second outgoing edge as the fallback (a **Normal** edge, or another conditional for
   the opposite case). Conditional edges are evaluated first, in order; a normal edge fires if
   none match.

A **feedback loop** is just a conditional edge pointing *backwards* — e.g. a verifier whose
"not approved" edge returns to the coder for another attempt. (See the *Data Science Loop*
template for a working example.)

> **Tip:** the condition must be a valid boolean expression against `state`. If you prefer to
> describe the branch in plain English, build it through the Copilot, then open the Edge
> inspector to see/tweak the generated expression.

## 5. Running a workflow

The **Simulated Gateway** chat (right panel) is the primary way to run a workflow — it mirrors
how a real user would talk to your agent over Telegram, but entirely locally.

1. Make sure the workflow you want is saved/active.
2. Type a message in the gateway and send it. This starts a run with your message as input.
3. Watch the **collapsible "Execution steps" panel** appear in the chat — it streams each node
   as it runs, including tool calls and token/cost. When the run finishes, the panel freezes as
   a record and the agent's final answer arrives as a chat bubble.

You can also press **Run** in the top bar; it asks for an input message and starts the run.

## 6. Live monitoring

While a run is active you get real-time visibility:

- **Canvas** — nodes light up as they move through running → completed → failed → paused.
- **Execution steps** (in the gateway chat) — a live feed of node transitions, tool calls, and
  token/cost.
- **Node inspector** — click any node and open the **Logs**, **I/O**, **Costs**, or **Inbox**
  tabs to inspect exactly what that node received, produced, spent, and any inter-agent
  messages.

## 7. Human-in-the-loop

Add a `human_chat` node anywhere in the flow. When the run reaches it, execution **pauses** and
the gateway prompts you to reply. Type your reply in the **same gateway chat** to resume the
run. (Start and continue HITL runs from the gateway chat so the resume control is available.)

## 8. Talking to your agent over Telegram

Once `TELEGRAM_BOT_TOKEN` is configured (see the README) and the backend is restarted:

- Send `/run <workflow name> <your input>` to start a specific workflow, **or** just send a
  plain message to start your most recently updated workflow.
- The bot replies with a run id and, on completion, delivers the result to the chat.
- For HITL: reply with plain text to continue a paused run, or use `/approve` / `/reject`.

A workflow ending in a `telegram_output` node will also push its report to the chat.

## 9. Templates

Open the **Library** (top bar) to browse pre-built workflows, or drag a template from the
palette. The included templates are:

- **Data Science Loop** — Coder → Verifier (retry loop) → Reporter.
- **Deep Researcher Swarm** — Coordinator → parallel researchers → Aggregator → Telegram.
- **AI Co-Scientist** — a chief scientist that delegates to sub-workflows as tools.

Open a template, run it, then save your own copy and modify it as a starting point.

## 10. Exporting

Click **Export** to download the active workflow as a standalone Python script — useful for
inspecting exactly what graph your visual workflow compiles to.
