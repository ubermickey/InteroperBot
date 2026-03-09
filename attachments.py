"""Attachment enrichment layer.

Coordinates on-device processing (Swift helpers, ffmpeg) to produce
text descriptions of iMessage attachments — photos, voice memos, videos.
Enriched descriptions are injected into the text prompt sent to Claude.
"""

import json
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import config
from imessage import Attachment

logger = logging.getLogger(__name__)

# Paths to compiled Swift helpers (relative to project root)
_PROJECT_DIR = Path(__file__).parent
DESCRIBE_IMAGE_BIN = _PROJECT_DIR / "helpers" / "describe_image"
TRANSCRIBE_BIN = _PROJECT_DIR / "helpers" / "transcribe"
EXTRACT_KEYFRAMES = _PROJECT_DIR / "helpers" / "extract_keyframes.sh"


def _human_size(total_bytes: int) -> str:
    """Format byte count as human-readable string."""
    if total_bytes < 1024:
        return f"{total_bytes} B"
    elif total_bytes < 1024 * 1024:
        return f"{total_bytes / 1024:.1f} KB"
    elif total_bytes < 1024 * 1024 * 1024:
        return f"{total_bytes / (1024 * 1024):.1f} MB"
    return f"{total_bytes / (1024 * 1024 * 1024):.1f} GB"


def _run_helper(cmd: list[str], timeout: int) -> Optional[dict]:
    """Run a helper subprocess and parse its JSON stdout."""
    try:
        result = subprocess.run(
            [str(c) for c in cmd],
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode != 0:
            logger.warning("Helper %s failed (exit %d): %s", cmd[0], result.returncode, result.stderr[:200])
            return None
        if result.stdout.strip():
            return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        logger.warning("Helper %s timed out after %ds", cmd[0], timeout)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        logger.warning("Helper %s error: %s", cmd[0], e)
    return None


def _describe_image(file_path: str, timeout: int) -> Optional[str]:
    """Run on-device image description (Vision framework labels + OCR)."""
    if not DESCRIBE_IMAGE_BIN.exists():
        return None
    data = _run_helper([DESCRIBE_IMAGE_BIN, file_path], timeout)
    if not data:
        return None

    parts = []
    desc = data.get("description", "")
    if desc and desc != "image":
        parts.append(desc)
    ocr = data.get("ocr_text", "").strip()
    if ocr:
        parts.append(f"text visible: '{ocr}'")
    return "; ".join(parts) if parts else None


def _transcribe_audio(file_path: str, timeout: int) -> Optional[str]:
    """Run on-device audio transcription (SFSpeechRecognizer)."""
    if not TRANSCRIBE_BIN.exists():
        return None
    data = _run_helper([TRANSCRIBE_BIN, file_path], timeout)
    if not data:
        return None
    transcript = data.get("transcript", "").strip()
    return transcript if transcript else None


def _process_video(file_path: str, timeout: int) -> Optional[str]:
    """Extract keyframes + audio from video, describe frames, transcribe audio."""
    if not EXTRACT_KEYFRAMES.exists():
        return None

    with tempfile.TemporaryDirectory(prefix="interoperbot_video_") as tmpdir:
        # Extract keyframes + audio
        data = _run_helper([EXTRACT_KEYFRAMES, file_path, tmpdir], timeout)
        if not data:
            return None

        parts = []
        duration = data.get("duration", "unknown")
        if duration and duration != "unknown":
            parts.append(f"{duration}")

        # Describe keyframes
        keyframes = data.get("keyframes", [])
        frame_descs = []
        per_frame_timeout = max(5, timeout // max(len(keyframes), 1))
        for frame_path in keyframes[:3]:  # limit to 3 frames
            desc = _describe_image(frame_path, per_frame_timeout)
            if desc:
                frame_descs.append(desc)
        if frame_descs:
            parts.append("shows " + ", ".join(frame_descs))

        # Transcribe audio track
        audio_path = data.get("audio")
        if audio_path:
            transcript = _transcribe_audio(audio_path, timeout)
            if transcript:
                parts.append(f"audio: '{transcript}'")

        return "; ".join(parts) if parts else None


def enrich_attachment(att: Attachment, timeout: int) -> str:
    """Process a single attachment and return a text description.

    Always returns a string — falls back to metadata-only on any error.
    """
    name = att.transfer_name or (Path(att.filename).name if att.filename else "file")
    size = _human_size(att.total_bytes)
    mime = att.mime_type or "unknown type"
    metadata_desc = f"{att.media_type}: {name} ({size}, {mime})"

    # If file doesn't exist on disk, return metadata only
    if not att.filename or not Path(att.filename).exists():
        return f"{metadata_desc}, file unavailable"

    detail = None
    if att.media_type == "image":
        detail = _describe_image(att.filename, timeout)
    elif att.media_type == "audio":
        transcript = _transcribe_audio(att.filename, timeout)
        if transcript:
            detail = f"transcript: '{transcript}'"
    elif att.media_type == "video":
        detail = _process_video(att.filename, timeout)

    if detail:
        return f"{metadata_desc} — {detail}"
    return metadata_desc


def enrich_attachments(attachments: list[Attachment]) -> list[str]:
    """Process all attachments and return text descriptions."""
    timeout = config.ATTACHMENT_TIMEOUT
    descriptions = []
    for att in attachments:
        try:
            desc = enrich_attachment(att, timeout)
        except Exception as e:
            logger.error("Attachment enrichment failed for %s: %s", att.transfer_name, e)
            name = att.transfer_name or "file"
            desc = f"{att.media_type}: {name} (processing failed)"
        descriptions.append(desc)
    return descriptions
