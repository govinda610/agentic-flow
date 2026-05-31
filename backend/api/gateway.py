from fastapi import APIRouter
from engine.runner import start_run
from pydantic import BaseModel

router = APIRouter()


class SimulateRequest(BaseModel):
    workflow_id: int
    message: str
    user_id: str = "simulated_user"


@router.post("/simulate")
async def simulate_gateway_message(body: SimulateRequest):
    """
    Inject a simulated Telegram-style message to trigger a workflow run.
    Used by the UI's Simulated Gateway Chat box — no Telegram token required.
    """
    run_id = await start_run(
        workflow_id=body.workflow_id,
        initial_input={
            "message": body.message,
            "telegram_user_id": body.user_id,
            "source": "simulated",
        },
        telegram_chat_id=None,
    )
    return {"run_id": run_id, "status": "started", "source": "simulated"}
