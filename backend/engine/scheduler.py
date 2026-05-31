from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlmodel import Session, select
from database import engine as db_engine
from models.workflow import Workflow
from engine.runner import start_run
import logging

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def run_cron_workflow(workflow_id: int):
    """Triggered by APScheduler when a workflow cron schedule fires."""
    logger.info(f"Triggering scheduled workflow execution for ID {workflow_id}")
    try:
        await start_run(
            workflow_id=workflow_id,
            initial_input={"message": "Proactive Cron Heartbeat", "source": "cron"},
            telegram_chat_id=None,
        )
    except Exception as exc:
        logger.error(f"Failed to execute scheduled workflow {workflow_id}: {exc}")


def start_scheduler():
    """Initialize schedules from database and start background scheduler."""
    scheduler.start()

    with Session(db_engine) as session:
        workflows = session.exec(
            select(Workflow).where(Workflow.cron_schedule != None)  # noqa: E711
        ).all()
        for wf in workflows:
            try:
                scheduler.add_job(
                    run_cron_workflow,
                    trigger=CronTrigger.from_crontab(wf.cron_schedule),
                    args=[wf.id],
                    id=f"workflow_cron_{wf.id}",
                    replace_existing=True,
                )
                logger.info(f"Registered cron '{wf.cron_schedule}' for workflow '{wf.name}'")
            except Exception as exc:
                logger.error(f"Invalid cron expression '{wf.cron_schedule}' for workflow {wf.id}: {exc}")


def update_workflow_job(workflow_id: int, cron_schedule: str | None):
    """Dynamically add, update, or remove a cron job for a workflow."""
    job_id = f"workflow_cron_{workflow_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        logger.info(f"Removed existing cron job for workflow {workflow_id}")
    if cron_schedule:
        try:
            scheduler.add_job(
                run_cron_workflow,
                trigger=CronTrigger.from_crontab(cron_schedule),
                args=[workflow_id],
                id=job_id,
                replace_existing=True,
            )
            logger.info(f"Updated dynamic cron '{cron_schedule}' for workflow {workflow_id}")
        except Exception as exc:
            logger.error(f"Failed to register dynamic cron '{cron_schedule}' for workflow {workflow_id}: {exc}")


def remove_workflow_job(workflow_id: int):
    """Dynamically remove a cron job for a workflow."""
    job_id = f"workflow_cron_{workflow_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        logger.info(f"Dynamically removed cron job for workflow {workflow_id}")
