"""Core message router — central brain of the multi-transport architecture.

Receives messages from any transport, routes through Store -> AI -> Store -> Transport.
All transports plug into this single router instead of duplicating the flow.
"""

import logging
import time

import config
from ai import ClaudeAssistant
from store import MessageStore
from transport import IncomingMessage, Transport

logger = logging.getLogger(__name__)


class MessageRouter:
    """Routes messages between transports and the AI layer."""

    def __init__(self, store: MessageStore, assistant: ClaudeAssistant):
        self.store = store
        self.assistant = assistant
        self.transports: dict[str, Transport] = {}
        self._shutdown = False

    def register(self, transport: Transport) -> None:
        """Register a transport with the router."""
        self.transports[transport.name] = transport
        logger.info("Registered transport: %s", transport.name)

    def handle_message(self, msg: IncomingMessage) -> str:
        """Universal flow: receive -> store -> enrich -> ai -> store -> send."""
        content = msg.text
        metadata = None

        if msg.attachments and config.ENABLE_ATTACHMENTS:
            from attachments import enrich_message_attachments

            descriptions = enrich_message_attachments(msg.attachments)
            attachment_context = "\n".join(
                f"[Attached: {d}]" for d in descriptions
            )
            content = f"{msg.text}\n{attachment_context}" if msg.text else attachment_context
            metadata = {
                "attachments": [
                    {
                        "filename": a.filename,
                        "mime_type": a.mime_type,
                        "size": a.size_bytes,
                        "media_type": a.media_type,
                    }
                    for a in msg.attachments
                ]
            }

        logger.info("[%s] Message from %s: %s", msg.transport, msg.sender, content[:80])

        contact_id = self.store.get_or_create_contact(msg.sender)
        session_id = self.store.get_metadata(contact_id, "cli_session_id")

        self.store.log_message(
            contact_id=contact_id,
            role="user",
            content=content,
            timestamp=msg.timestamp,
            metadata=metadata,
        )

        history = self.store.get_history(contact_id, limit=config.MAX_HISTORY)
        reply, new_session_id = self.assistant.respond(history, session_id=session_id)

        if new_session_id:
            self.store.set_metadata(contact_id, "cli_session_id", new_session_id)

        self.store.log_message(
            contact_id=contact_id,
            role="assistant",
            content=reply,
        )

        transport = self.transports.get(msg.transport)
        if transport:
            transport.send(msg.sender, reply)

        return reply

    def shutdown(self) -> None:
        """Signal the router to stop."""
        self._shutdown = True

    def run(self) -> None:
        """Main loop: starts push transports, polls pull transports."""
        # Start all transports (push transports begin receiving)
        for t in self.transports.values():
            t.start(self.handle_message)

        # Poll loop for pull transports (iMessage)
        while not self._shutdown:
            for t in self.transports.values():
                t.poll(self.handle_message)
            time.sleep(config.POLL_INTERVAL)

        # Graceful shutdown
        for t in self.transports.values():
            t.stop()
        logger.info("MessageRouter stopped.")
