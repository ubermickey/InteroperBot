"""Claude AI assistant layer.

Calls the Claude CLI as a subprocess — no API key needed.
Uses CLI session persistence (--resume) as the primary memory model.
SQLiteStore serves as a backup log for recovery when sessions expire.
"""

import json
import logging
import os
import subprocess
from typing import Optional

import config

logger = logging.getLogger(__name__)


class ClaudeAssistant:
    """Manages Claude CLI calls with session-based persistent memory."""

    def __init__(
        self,
        system_prompt: str = "You are a helpful assistant responding via iMessage. Keep responses concise and conversational.",
        timeout: int = 120,
    ):
        self.system_prompt = system_prompt
        self.timeout = timeout
        self.claude_bin = config.CLAUDE_CLI
        # Strip nesting guard so CLI works when launched from a Claude Code terminal
        self._env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    def respond(
        self,
        messages: list[dict],
        session_id: Optional[str] = None,
    ) -> tuple[str, Optional[str]]:
        """Get a response from Claude CLI.

        Args:
            messages: Conversation history (used for fallback recovery only).
            session_id: CLI session ID to resume. None starts a fresh session.

        Returns:
            (reply_text, session_id) tuple. session_id may be None on error.
        """
        if not messages:
            return "No message to respond to.", None

        latest = messages[-1]["content"]

        cmd = [self.claude_bin, "-p", latest, "--output-format", "json"]
        if session_id:
            cmd.extend(["--resume", session_id])
        elif self.system_prompt:
            cmd.extend(["--system-prompt", self.system_prompt])

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=self.timeout, env=self._env,
            )

            if result.returncode != 0 and session_id:
                logger.warning(
                    "Session %s failed (exit %d), falling back to history",
                    session_id, result.returncode,
                )
                return self._fallback_respond(messages)

            if result.returncode != 0:
                logger.error("Claude CLI error (exit %d): %s", result.returncode, result.stderr[:200])
                return "Sorry, I'm having trouble responding right now. Please try again.", None

            data = json.loads(result.stdout)
            reply = data.get("result", "").strip()
            new_session_id = data.get("session_id")
            return reply, new_session_id

        except json.JSONDecodeError:
            logger.error("Failed to parse CLI JSON output: %s", result.stdout[:200])
            # Try to use raw stdout as plain text fallback
            text = result.stdout.strip()
            return text if text else "Sorry, I couldn't parse the response.", None
        except FileNotFoundError:
            logger.error("Claude CLI not found at %s", self.claude_bin)
            return "Claude CLI is not installed. Check CLAUDE_CLI path.", None
        except subprocess.TimeoutExpired:
            logger.error("Claude CLI timed out after %ds", self.timeout)
            return "Sorry, the response took too long. Please try again.", None

    def _fallback_respond(self, messages: list[dict]) -> tuple[str, Optional[str]]:
        """Recovery: format history into prompt, start a fresh session."""
        history_text = self._format_history(messages)
        latest = messages[-1]["content"]

        if history_text:
            prompt = f"<conversation_history>\n{history_text}\n</conversation_history>\n\nUser: {latest}"
        else:
            prompt = latest

        cmd = [self.claude_bin, "-p", prompt, "--output-format", "json"]
        if self.system_prompt:
            cmd.extend(["--system-prompt", self.system_prompt])

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=self.timeout, env=self._env,
            )

            if result.returncode != 0:
                logger.error("Fallback CLI error (exit %d): %s", result.returncode, result.stderr[:200])
                return "Sorry, I'm having trouble responding right now. Please try again.", None

            data = json.loads(result.stdout)
            reply = data.get("result", "").strip()
            new_session_id = data.get("session_id")
            return reply, new_session_id

        except json.JSONDecodeError:
            logger.error("Failed to parse fallback CLI JSON: %s", result.stdout[:200])
            text = result.stdout.strip()
            return text if text else "Sorry, I couldn't parse the response.", None
        except FileNotFoundError:
            logger.error("Claude CLI not found at %s", self.claude_bin)
            return "Claude CLI is not installed. Check CLAUDE_CLI path.", None
        except subprocess.TimeoutExpired:
            logger.error("Fallback CLI timed out after %ds", self.timeout)
            return "Sorry, the response took too long. Please try again.", None

    @staticmethod
    def _format_history(messages: list[dict]) -> str:
        """Format conversation history as text (used in fallback recovery only)."""
        lines = []
        for msg in messages[:-1]:
            role = "User" if msg["role"] == "user" else "Assistant"
            lines.append(f"{role}: {msg['content']}")
        return "\n".join(lines)
