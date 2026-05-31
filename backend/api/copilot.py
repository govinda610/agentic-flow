from fastapi import APIRouter
from pydantic import BaseModel
from providers.registry import get_llm
from langchain_core.messages import HumanMessage, SystemMessage
from engine.node_input import text_of
import json
import re

router = APIRouter()

COPILOT_SYSTEM_PROMPT = """
You are an expert AI workflow architect. Convert natural language workflow descriptions into a structured JSON schema.

RULES:
1. Return ONLY valid JSON — no markdown, no explanation, no code blocks.
2. Use these node types: start, end, simple_llm, agent, deep_agent, supervisor, telegram_output, webhook_trigger, human_chat
3. Each node must have: id (snake_case), type, position ({x, y}), config
4. Each edge must have: id, source, target, type (normal|conditional|error|parallel_fan_out|parallel_fan_in), condition (null or string), label
5. For conditional edges, condition must use: state['node_outputs']['NODE_ID']['FIELD'] == VALUE
6. Nodes that need structured output must have: structured_output.fields as [{name, type}] (types: string|boolean|integer|number|array)
7. For verifier nodes: always force structured_output with is_approved (boolean) and feedback (string)
8. Node positions: space 300px horizontally between columns, 150px vertically between rows in same column
9. The first node is always "start" and the last is always "end"
10. For parallel fan-out edges, add fan_out_from: "node_outputs.NODE_ID.FIELD" pointing to the array field to iterate
11. EDIT MODE: If an "Existing workflow context" is provided, treat the request as an edit of THAT workflow. Return the FULL updated schema, preserving the existing node ids, positions, and config for anything the user did not ask to change. Only add, modify, or remove the parts the request calls for, and keep start/end intact.

OUTPUT FORMAT:
{
  "name": "<workflow name>",
  "description": "<brief description>",
  "nodes": [...],
  "edges": [...]
}

EXAMPLE: If asked for "a researcher that feeds a writer", output:
{
  "name": "Researcher to Writer",
  "description": "Research agent feeds into a writing agent",
  "nodes": [
    {"id": "node_start", "type": "start", "position": {"x": 50, "y": 200}, "config": {"label": "Start"}},
    {"id": "node_researcher", "type": "agent", "position": {"x": 350, "y": 200}, "config": {"name": "Researcher", "system_prompt": "Research the given topic thoroughly.", "tools": [], "structured_output": null}},
    {"id": "node_writer", "type": "agent", "position": {"x": 650, "y": 200}, "config": {"name": "Writer", "system_prompt": "Write a clear article based on the research.", "tools": [], "structured_output": null}},
    {"id": "node_end", "type": "end", "position": {"x": 950, "y": 200}, "config": {"label": "End"}}
  ],
  "edges": [
    {"id": "e1", "source": "node_start", "target": "node_researcher", "type": "normal", "condition": null, "label": ""},
    {"id": "e2", "source": "node_researcher", "target": "node_writer", "type": "normal", "condition": null, "label": ""},
    {"id": "e3", "source": "node_writer", "target": "node_end", "type": "normal", "condition": null, "label": ""}
  ]
}
"""

class CopilotRequest(BaseModel):
    prompt: str
    context: dict = {}  # Optional: existing nodes to extend

class CopilotResponse(BaseModel):
    workflow_schema: dict
    message: str

@router.post("/generate-workflow", response_model=CopilotResponse)
async def generate_workflow(body: CopilotRequest):
    """
    Design-Time Copilot: converts a natural language prompt into a workflow JSON schema.
    The frontend applies autoLayout() to the returned schema before rendering.
    """
    llm = get_llm(temperature=0.1)

    user_message = body.prompt
    if body.context:
        user_message += f"\n\nExisting workflow context: {json.dumps(body.context)}"

    messages = [
        SystemMessage(content=COPILOT_SYSTEM_PROMPT),
        HumanMessage(content=user_message),
    ]

    response = await llm.ainvoke(messages)
    # FIX: use text_of() to handle LangChain 1.x content blocks (list vs str)
    content = text_of(response).strip()

    # Strip markdown code blocks if LLM wraps output in them
    content = re.sub(r'^```(?:json)?\n?', '', content)
    content = re.sub(r'\n?```$', '', content)

    try:
        schema = json.loads(content)
        return CopilotResponse(
            workflow_schema=schema,
            message=f"Generated workflow '{schema.get('name', 'Unnamed')}' with {len(schema.get('nodes', []))} nodes."
        )
    except json.JSONDecodeError as e:
        # Attempt to extract JSON from partial output
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            schema = json.loads(json_match.group())
            return CopilotResponse(workflow_schema=schema, message="Workflow generated (partial recovery).")
        raise ValueError(f"Copilot returned invalid JSON: {e}")
