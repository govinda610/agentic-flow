"""Shared singleton for the Telegram gateway instance.

This module breaks the circular import that would occur if api/workflows.py,
engine/parser.py, or engine/runner.py imported directly from main.py.
main.py sets `telegram_gateway` here during startup; all other modules
read it via `gateway.state.telegram_gateway`.
"""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gateway.telegram import TelegramGateway

telegram_gateway: "TelegramGateway | None" = None
