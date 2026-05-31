from abc import ABC, abstractmethod

class BaseMessagingGateway(ABC):
    """Abstract base class for all messaging integrations."""

    @abstractmethod
    async def start(self):
        """Initialize and start the gateway."""
        pass

    @abstractmethod
    async def stop(self):
        """Gracefully shut down the gateway."""
        pass

    @abstractmethod
    async def send_message(self, chat_id: int | str, text: str, is_markdown: bool = False) -> bool:
        """Send a text message to a recipient."""
        pass

    @abstractmethod
    async def register_workflow(self, workflow_id: int, trigger_keyword: str | None = None):
        """Associate a workflow with a trigger keyword or command."""
        pass
