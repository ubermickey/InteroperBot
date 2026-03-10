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
        # Strip all Claude Code env vars so CLI subprocess isn't blocked
        # by re-entrancy guards (CLAUDECODE, session tokens, entrypoint, etc.)
        self._env = {
            k: v for k, v in os.environ.items()
            if not k.upper().startswith("CLAUDE")
        }

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
            result = self._run_cli(cmd)

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

    def _run_cli(self, cmd: list[str]) -> subprocess.CompletedProcess:
        """Run a Claude CLI command with proper isolation.

        Uses start_new_session and DEVNULL stdin to prevent re-entrancy
        hangs when called from within a Claude Code terminal session.
        """
        return subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=self.timeout, env=self._env,
            stdin=subprocess.DEVNULL, start_new_session=True,
        )

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
            result = self._run_cli(cmd)

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

    def describe_video(
        self,
        frames: list[dict],
        transcript_segments: list[dict],
        duration: str,
    ) -> str:
        """Describe a video by passing frame images to Claude CLI's Read tool.

        Instead of Vision framework labels, Claude reads the actual frame
        images (multimodal) and produces rich action/scene descriptions.

        Args:
            frames: List of {"path": str, "time": float} dicts.
            transcript_segments: List of {"text": str, "start": float, "end": float}.
            duration: Human-readable duration string.

        Returns:
            Rich text description, or empty string on failure.
        """
        if not frames:
            return ""

        # Build frame refs with motion annotations
        frame_lines = []
        for f in frames:
            motion = f.get("motion", 0)
            tag = ""
            if motion > 0.15:
                tag = " [HIGH MOTION — interpret blur as movement]"
            elif motion > 0.05:
                tag = " [motion detected]"
            frame_lines.append(
                f"- Frame at {f['time']:.1f}s (motion:{motion:.3f}): {f['path']}{tag}"
            )
        frame_refs = "\n".join(frame_lines)

        if transcript_segments:
            transcript_text = "\n".join(
                f"[{seg['start']:.1f}s - {seg['end']:.1f}s] {seg['text']}"
                for seg in transcript_segments
            )
        else:
            transcript_text = "(no speech detected)"

        prompt = (
            f"Analyze this video ({duration}). "
            f"I've extracted {len(frames)} frames and transcribed the audio.\n\n"
            f"Frames (use the Read tool to view each image file):\n{frame_refs}\n\n"
            f"Audio transcript:\n{transcript_text}\n\n"
            f"MOTION BLUR INTERPRETATION:\n"
            f"Some frames may contain motion blur. This is signal, not noise:\n"
            f"- Direction of blur reveals direction of movement\n"
            f"- Amount of blur indicates speed (more blur = faster motion)\n"
            f"- Selective blur (sharp background, blurry subject) means the subject moved\n"
            f"- Compare blurry frames with sharp frames before/after to deduce the action\n"
            f"- The 'motion' score shows how different each frame is from its predecessor "
            f"(0=identical, >0.1=significant change)\n\n"
            f"Describe what's happening in this video in 2-3 sentences. "
            f"What are people doing? What gestures or movements occur? "
            f"What's the setting and context?"
        )

        cmd = [
            self.claude_bin, "-p", prompt,
            "--allowedTools", "Read",
            "--output-format", "json",
        ]

        try:
            result = self._run_cli(cmd)
            if result.returncode != 0:
                logger.warning(
                    "Video description failed (exit %d): %s",
                    result.returncode, result.stderr[:200],
                )
                return ""

            data = json.loads(result.stdout)
            return data.get("result", "").strip()

        except json.JSONDecodeError:
            logger.warning("Video description: failed to parse JSON")
            return ""
        except subprocess.TimeoutExpired:
            logger.warning("Video description timed out after %ds", self.timeout)
            return ""
        except FileNotFoundError:
            logger.warning("Claude CLI not found at %s", self.claude_bin)
            return ""

    def describe_storyboard_panels(
        self,
        panels: list[dict],
        duration: str,
    ) -> list[str]:
        """Describe each storyboard panel by reading its frame image.

        Args:
            panels: List of {"frame": {"path", "time"}, "transcript": str, "timestamp": float}.
            duration: Human-readable duration string.

        Returns:
            List of description strings, one per panel (empty string on failure).
        """
        if not panels:
            return []

        panel_refs = []
        for i, p in enumerate(panels, 1):
            speech = p["transcript"]
            panel_refs.append(
                f"Panel {i} ({p['timestamp']:.1f}s): {p['frame']['path']}"
                f" — Speech: \"{speech}\""
            )

        prompt = (
            f"I'm creating a storyboard from a video ({duration}). "
            f"Here are {len(panels)} panels, each with a frame image and speech.\n\n"
            + "\n".join(panel_refs) + "\n\n"
            f"Read each frame image with the Read tool, then provide a brief "
            f"visual description (1 sentence each) of what's shown.\n"
            f"Output ONLY a JSON array of strings, one description per panel:\n"
            f'["Person walks toward camera in a kitchen", "Close-up of hands on counter", ...]'
        )

        cmd = [
            self.claude_bin, "-p", prompt,
            "--allowedTools", "Read",
            "--output-format", "json",
        ]

        try:
            result = self._run_cli(cmd)
            if result.returncode != 0:
                logger.warning(
                    "Storyboard description failed (exit %d)", result.returncode,
                )
                return [""] * len(panels)

            data = json.loads(result.stdout)
            reply = data.get("result", "").strip()

            # Parse the JSON array from Claude's response
            # Try to find a JSON array in the response
            start = reply.find("[")
            end = reply.rfind("]")
            if start != -1 and end != -1:
                descriptions = json.loads(reply[start:end + 1])
                if isinstance(descriptions, list):
                    # Pad or trim to match panel count
                    while len(descriptions) < len(panels):
                        descriptions.append("")
                    return descriptions[:len(panels)]

            logger.warning("Storyboard: couldn't parse description array")
            return [""] * len(panels)

        except (json.JSONDecodeError, subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.warning("Storyboard description error: %s", e)
            return [""] * len(panels)

    @staticmethod
    def _format_history(messages: list[dict]) -> str:
        """Format conversation history as text (used in fallback recovery only)."""
        lines = []
        for msg in messages[:-1]:
            role = "User" if msg["role"] == "user" else "Assistant"
            lines.append(f"{role}: {msg['content']}")
        return "\n".join(lines)
