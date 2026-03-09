"""InteroperBot — Web chat interface.

Reuses the existing Store and AI layers to provide a browser-based
chat UI as an alternative transport to iMessage.

Usage:
    python web.py              # Start on http://localhost:8000
    python web.py --port 3000  # Custom port
"""

import argparse
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import uvicorn

import config
from ai import ClaudeAssistant
from store import SQLiteStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("web")

app = FastAPI(title="InteroperBot")

store = SQLiteStore(db_path=config.DB_PATH)
assistant = ClaudeAssistant(
    system_prompt=config.SYSTEM_PROMPT,
    timeout=config.CLI_TIMEOUT,
)

WEB_CONTACT = "web-user"


class ChatRequest(BaseModel):
    message: str


@app.get("/")
async def index():
    return FileResponse(Path(__file__).parent / "chat.html")


@app.get("/api/history")
async def history():
    contact_id = store.get_or_create_contact(WEB_CONTACT)
    messages = store.get_history(contact_id, limit=config.MAX_HISTORY)
    return JSONResponse(messages)


@app.post("/api/chat")
async def chat(req: ChatRequest):
    contact_id = store.get_or_create_contact(WEB_CONTACT)
    session_id = store.get_metadata(contact_id, "cli_session_id")

    store.log_message(contact_id, "user", req.message)

    history = store.get_history(contact_id, limit=config.MAX_HISTORY)
    reply, new_session_id = assistant.respond(history, session_id=session_id)

    if new_session_id:
        store.set_metadata(contact_id, "cli_session_id", new_session_id)

    store.log_message(contact_id, "assistant", reply)

    return JSONResponse({"reply": reply})


@app.post("/api/clear")
async def clear():
    contact_id = store.get_or_create_contact(WEB_CONTACT)
    store.clear_history(contact_id)
    store.set_metadata(contact_id, "cli_session_id", "")
    return JSONResponse({"status": "cleared"})


def main():
    parser = argparse.ArgumentParser(description="InteroperBot web interface")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    logger.info("Starting web UI at http://%s:%d", args.host, args.port)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
