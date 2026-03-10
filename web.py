"""InteroperBot — Web chat interface.

Provides a browser-based chat UI and unified API endpoints.
Works both standalone (python web.py) and as a WebTransport
plugged into the MessageRouter.

Usage:
    python web.py              # Standalone on http://localhost:8000
    python web.py --port 3000  # Custom port
"""

import asyncio
import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import uvicorn

import config
from transport import Transport, IncomingMessage

logger = logging.getLogger("web")

WEB_CONTACT = "web-user"


class ChatRequest(BaseModel):
    message: str


class SendRequest(BaseModel):
    transport: str
    to: str
    text: str


class WebTransport(Transport):
    """Web chat transport — sends via HTTP response, not push.

    Registers FastAPI routes that call router.handle_message() for the
    Store -> AI -> Store flow instead of duplicating it.
    """

    name = "web"

    def __init__(self, router):
        self.router = router
        self.app = FastAPI(title="InteroperBot")
        self._register_routes()

    def send(self, recipient: str, text: str) -> bool:
        # Web sends via HTTP response — this is a no-op
        return True

    def _register_routes(self) -> None:
        app = self.app
        router = self.router

        @app.get("/")
        async def index():
            return FileResponse(Path(__file__).parent / "chat.html")

        @app.get("/api/history")
        async def history():
            contact_id = router.store.get_or_create_contact(WEB_CONTACT)
            messages = router.store.get_history(contact_id, limit=config.MAX_HISTORY)
            return JSONResponse(messages)

        @app.post("/api/chat")
        async def chat(req: ChatRequest):
            msg = IncomingMessage(
                transport="web",
                sender=WEB_CONTACT,
                text=req.message,
                timestamp=datetime.now(timezone.utc),
            )
            reply = await asyncio.to_thread(router.handle_message, msg)
            return JSONResponse({"reply": reply})

        @app.post("/api/clear")
        async def clear():
            contact_id = router.store.get_or_create_contact(WEB_CONTACT)
            router.store.clear_history(contact_id)
            router.store.set_metadata(contact_id, "cli_session_id", "")
            return JSONResponse({"status": "cleared"})

        # --- Unified API endpoints ---

        @app.get("/api/status")
        async def status():
            return JSONResponse({
                "project": "InteroperBot",
                "transports": list(router.transports.keys()),
                "web_enabled": config.WEB_ENABLED,
                "whatsapp_enabled": config.WHATSAPP_ENABLED,
            })

        @app.get("/api/transports")
        async def transports():
            info = []
            for name, t in router.transports.items():
                info.append({"name": name, "type": type(t).__name__})
            return JSONResponse(info)

        @app.post("/api/send")
        async def send(req: SendRequest):
            transport = router.transports.get(req.transport)
            if not transport:
                return JSONResponse(
                    {"error": f"Unknown transport: {req.transport}"},
                    status_code=400,
                )
            success = await asyncio.to_thread(transport.send, req.to, req.text)
            return JSONResponse({"sent": success})


def create_standalone_app() -> FastAPI:
    """Create a standalone web app (not plugged into MessageRouter)."""
    from ai import ClaudeAssistant
    from core import MessageRouter
    from store import SQLiteStore

    store = SQLiteStore(db_path=config.DB_PATH)
    assistant = ClaudeAssistant(
        system_prompt=config.SYSTEM_PROMPT,
        timeout=config.CLI_TIMEOUT,
    )
    router = MessageRouter(store, assistant)
    web = WebTransport(router)
    router.register(web)
    return web.app


def main():
    parser = argparse.ArgumentParser(description="InteroperBot web interface")
    parser.add_argument("--port", type=int, default=config.WEB_PORT)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    app = create_standalone_app()
    logger.info("Starting web UI at http://%s:%d", args.host, args.port)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
