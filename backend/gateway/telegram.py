from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from gateway.base import BaseMessagingGateway
from engine.runner import start_run
from config import settings
import logging
from sqlmodel import Session, select
from models.run import WorkflowRun
from models.workflow import Workflow
from database import engine as db_engine

logger = logging.getLogger(__name__)

# Global mapping: keyword → workflow_id (populated by register_workflow)
_workflow_triggers: dict[str, int] = {}


class TelegramGateway(BaseMessagingGateway):
    """
    Telegram integration using python-telegram-bot v21 in polling mode.
    Managed within FastAPI's lifespan context (shared asyncio event loop).

    Commands:
      /start                        — welcome message
      /run <workflow_name> <input>  — start a workflow by keyword
      /status <run_id>              — check run status
      /approve <run_id>             — approve a HITL pause
      /reject <run_id>              — reject a HITL pause
      /help                         — list all commands
    """

    def __init__(self, token: str):
        self.token = token
        self.app = ApplicationBuilder().token(token).build()
        self._setup_handlers()

    def _setup_handlers(self):
        self.app.add_handler(CommandHandler("start",   self._handle_start))
        self.app.add_handler(CommandHandler("run",     self._handle_run))
        self.app.add_handler(CommandHandler("status",  self._handle_status))
        self.app.add_handler(CommandHandler("approve", self._handle_approve))
        self.app.add_handler(CommandHandler("reject",  self._handle_reject))
        self.app.add_handler(CommandHandler("help",    self._handle_help))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))

    async def start(self):
        """Start polling — integrated into FastAPI lifespan."""
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        logger.info("Telegram gateway started (polling mode)")

    async def stop(self):
        """Gracefully stop polling."""
        try:
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()
            logger.info("Telegram gateway stopped")
        except Exception as exc:
            logger.error(f"Error during Telegram gateway shutdown: {exc}")

    async def send_message(self, chat_id: int | str, text: str, is_markdown: bool = False) -> bool:
        try:
            parse_mode = "Markdown" if is_markdown else None
            await self.app.bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
            return True
        except Exception as exc:
            logger.error(f"Failed to send Telegram message to {chat_id}: {exc}")
            return False

    async def register_workflow(self, workflow_id: int, trigger_keyword: str | None = None):
        if trigger_keyword:
            _workflow_triggers[trigger_keyword.lower()] = workflow_id

    def _is_allowed(self, user_id: int) -> bool:
        if not settings.telegram_allowed_users:
            return True
        return user_id in settings.telegram_allowed_users

    async def _handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_allowed(update.effective_user.id):
            return
        await update.message.reply_text(
            "👋 Welcome to *Agentic Flow*!\n\n"
            "Use `/run <workflow_name> <your input>` to start a workflow.\n"
            "Use `/help` for all commands.",
            parse_mode="Markdown",
        )

    async def _handle_run(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_allowed(update.effective_user.id):
            return
        args = context.args
        if not args:
            await update.message.reply_text("Usage: `/run <workflow_name> <input>`", parse_mode="Markdown")
            return

        # Try progressively longer prefixes of args to match a workflow name or slug.
        # e.g. "/run Data Science Loop hello" → name="Data Science Loop", input="hello"
        workflow_id = None
        matched_len = 0
        with Session(db_engine) as session:
            workflows = session.exec(select(Workflow)).all()
        for i in range(len(args), 0, -1):
            candidate = " ".join(args[:i]).lower()
            candidate_slug = "_".join(args[:i]).lower()
            for wf in workflows:
                if wf.name.lower() == candidate or (wf.template_slug and wf.template_slug.lower() == candidate_slug):
                    workflow_id = wf.id
                    matched_len = i
                    break
            if workflow_id:
                break
        # Fall back to trigger keyword registry
        if not workflow_id:
            for i in range(len(args), 0, -1):
                candidate = " ".join(args[:i]).lower()
                if candidate in _workflow_triggers:
                    workflow_id = _workflow_triggers[candidate]
                    matched_len = i
                    break

        if not workflow_id:
            await update.message.reply_text(f"❌ No workflow found for `{' '.join(args)}`", parse_mode="Markdown")
            return

        workflow_input = " ".join(args[matched_len:])
        run_id = await start_run(
            workflow_id=workflow_id,
            initial_input={"message": workflow_input, "telegram_user_id": update.effective_user.id},
            telegram_chat_id=update.effective_chat.id,
        )

        await update.message.reply_text(
            f"✅ Workflow started!\nRun ID: `{run_id}`\n\nYou'll receive results when completed.",
            parse_mode="Markdown",
        )

    async def _handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_allowed(update.effective_user.id) or not context.args:
            return
        run_id = context.args[0]
        from models.run import WorkflowRun
        from sqlmodel import Session
        from database import engine as db_engine
        with Session(db_engine) as session:
            run = session.get(WorkflowRun, run_id)
        if run:
            await update.message.reply_text(
                f"Status for `{run_id[:8]}...`: *{run.status}*", parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("Run not found.")

    async def _handle_approve(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_allowed(update.effective_user.id):
            return
        if context.args:
            run_id = context.args[0]
        else:
            # Find most recent paused run for this chat
            with Session(db_engine) as session:
                run = session.exec(
                    select(WorkflowRun)
                    .where(WorkflowRun.telegram_chat_id == update.effective_chat.id)
                    .where(WorkflowRun.status == "paused")
                    .order_by(WorkflowRun.created_at.desc())
                ).first()
            if not run:
                await update.message.reply_text("No paused run found for this chat.")
                return
            run_id = run.id
        from engine.runner import resume_run
        try:
            await resume_run(run_id, "approved")
            await update.message.reply_text(
                f"✅ Run `{run_id[:8]}` approved and resumed.", parse_mode="Markdown"
            )
        except ValueError as e:
            await update.message.reply_text(f"❌ {e}")

    async def _handle_reject(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_allowed(update.effective_user.id):
            return
        if context.args:
            run_id = context.args[0]
        else:
            # Find most recent paused run for this chat
            with Session(db_engine) as session:
                run = session.exec(
                    select(WorkflowRun)
                    .where(WorkflowRun.telegram_chat_id == update.effective_chat.id)
                    .where(WorkflowRun.status == "paused")
                    .order_by(WorkflowRun.created_at.desc())
                ).first()
            if not run:
                await update.message.reply_text("No paused run found for this chat.")
                return
            run_id = run.id
        from engine.runner import _run_tasks
        task = _run_tasks.get(run_id)
        if task and not task.done():
            task.cancel()
        with Session(db_engine) as session:
            run = session.get(WorkflowRun, run_id)
            if not run:
                await update.message.reply_text(f"❌ Run `{run_id[:8]}` not found.")
                return
            run.status = "cancelled"
            session.commit()
        await update.message.reply_text(
            f"🛑 Run `{run_id[:8]}` rejected and cancelled.", parse_mode="Markdown"
        )

    async def _handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "*Available Commands:*\n"
            "`/run <name> <input>` — Start a workflow\n"
            "`/status <run_id>` — Check run status\n"
            "`/approve <run_id>` — Approve HITL pause\n"
            "`/reject <run_id>` — Reject HITL pause\n",
            parse_mode="Markdown",
        )

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle plain text messages. Routes to a paused run or starts a new one."""
        if not self._is_allowed(update.effective_user.id):
            return

        from models.run import WorkflowRun
        from models.workflow import Workflow
        from sqlmodel import Session, select
        from engine.runner import start_run, resume_run
        from database import engine as db_engine

        chat_id = update.effective_chat.id
        text = update.message.text

        # 1. Resume any active paused run for this chat
        with Session(db_engine) as session:
            paused_run = session.exec(
                select(WorkflowRun)
                .where(WorkflowRun.telegram_chat_id == chat_id)
                .where(WorkflowRun.status == "paused")
                .order_by(WorkflowRun.created_at.desc())
            ).first()

        if paused_run:
            await resume_run(paused_run.id, text)
            await update.message.reply_text("📥 Input forwarded to active workflow.")
            return

        # 2. Start a new run on the most recently updated non-template workflow
        with Session(db_engine) as session:
            workflow = session.exec(
                select(Workflow)
                .where(Workflow.is_template == False)  # noqa: E712
                .order_by(Workflow.updated_at.desc(), Workflow.id.desc())
            ).first()

        if workflow:
            run_id = await start_run(
                workflow_id=workflow.id,
                initial_input={"message": text, "source": "telegram"},
                telegram_chat_id=chat_id,
            )
            await update.message.reply_text(
                f"🤖 *Started workflow '{workflow.name}'* (Run: `{run_id[:8]}`)\n\nProcessing...",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(
                "No workflows are currently configured. Please open the Web UI and create one!"
            )
