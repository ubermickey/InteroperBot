#!/usr/bin/env python3
"""storyboard.py — Generate visual storyboards from video files.

Extracts frames at 1fps, transcribes audio with per-segment timestamps,
aligns frames to speech boundaries, and uses Claude CLI to describe each
panel. Outputs a self-contained HTML file with frame images.

Usage:
    python storyboard.py /path/to/video.mov
    python storyboard.py /path/to/video.mov --output my_storyboard.html
"""

import argparse
import json
import logging
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import config
from ai import ClaudeAssistant
from attachments import _run_helper, EXTRACT_KEYFRAMES, TRANSCRIBE_BIN

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("storyboard")


def align_frames_to_segments(
    frames: list[dict], segments: list[dict],
) -> list[dict]:
    """Align frames to speech segments by nearest timestamp.

    For each speech segment, picks the frame closest to the segment's
    midpoint. Frames with no matching speech become [silence] panels.
    Panels are sorted by timestamp.

    Returns list of {"frame": dict, "transcript": str, "timestamp": float}.
    """
    if not frames:
        return []

    panels = []
    used_frame_indices = set()

    # Match each speech segment to its nearest frame
    for seg in segments:
        midpoint = (seg["start"] + seg["end"]) / 2
        best_idx = min(range(len(frames)), key=lambda i: abs(frames[i]["time"] - midpoint))
        used_frame_indices.add(best_idx)
        panels.append({
            "frame": frames[best_idx],
            "transcript": seg["text"],
            "timestamp": seg["start"],
        })

    # Add silence panels for unmatched frames that are far from any speech panel
    for i, frame in enumerate(frames):
        if i in used_frame_indices:
            continue
        too_close = any(abs(frame["time"] - p["timestamp"]) < 3.0 for p in panels)
        if not too_close:
            panels.append({
                "frame": frame,
                "transcript": "[silence]",
                "timestamp": frame["time"],
            })

    # If no segments at all, create panels from frames at even intervals
    if not segments and not panels:
        step = max(1, len(frames) // 10)  # ~10 panels for long videos
        for i in range(0, len(frames), step):
            panels.append({
                "frame": frames[i],
                "transcript": "[silence]",
                "timestamp": frames[i]["time"],
            })

    panels.sort(key=lambda p: p["timestamp"])
    return panels


_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>Storyboard — {video_name}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #0f0f23;
            color: #e0e0e0;
            padding: 2rem;
        }}
        h1 {{
            text-align: center;
            color: #e94560;
            font-size: 1.8rem;
            margin-bottom: 0.5rem;
        }}
        .meta {{
            text-align: center;
            color: #666;
            margin-bottom: 2rem;
            font-size: 0.9rem;
        }}
        .panels {{
            max-width: 960px;
            margin: 0 auto;
        }}
        .panel {{
            background: #1a1a2e;
            border-radius: 12px;
            padding: 1.5rem;
            margin: 1.5rem 0;
            display: flex;
            gap: 1.5rem;
            border: 1px solid #16213e;
        }}
        .panel img {{
            width: 360px;
            min-width: 360px;
            height: 202px;
            object-fit: cover;
            border-radius: 8px;
            background: #111;
        }}
        .panel-content {{
            flex: 1;
            display: flex;
            flex-direction: column;
            justify-content: center;
        }}
        .timestamp {{
            color: #e94560;
            font-size: 0.8rem;
            font-weight: 700;
            letter-spacing: 0.05em;
            margin-bottom: 0.4rem;
        }}
        .description {{
            line-height: 1.6;
            margin-bottom: 0.6rem;
        }}
        .transcript {{
            font-style: italic;
            color: #999;
            border-left: 3px solid #e94560;
            padding-left: 1rem;
        }}
        .silence {{
            color: #555;
            font-style: italic;
        }}
        @media (max-width: 700px) {{
            .panel {{ flex-direction: column; }}
            .panel img {{ width: 100%; min-width: unset; height: auto; }}
        }}
    </style>
</head>
<body>
    <h1>Video Storyboard</h1>
    <div class="meta">{video_name} &mdash; {duration} &mdash; {panel_count} panels</div>
    <div class="panels">
{panels_html}
    </div>
</body>
</html>
"""

_PANEL_TEMPLATE = """\
        <div class="panel">
            <img src="{img_src}" alt="Frame at {time}s">
            <div class="panel-content">
                <div class="timestamp">{time}s</div>
                <p class="description">{description}</p>
                {transcript_html}
            </div>
        </div>"""


def generate_html(
    panels: list[dict],
    descriptions: list[str],
    video_name: str,
    duration: str,
    output_path: Path,
    frames_dir: Path,
):
    """Generate the storyboard HTML file.

    Copies frame images into a frames/ subdirectory next to the HTML file
    and references them with relative paths.
    """
    # Create frames directory next to output HTML
    out_frames = output_path.parent / "frames"
    out_frames.mkdir(parents=True, exist_ok=True)

    panels_html_parts = []
    for i, panel in enumerate(panels):
        # Copy frame to output directory
        src = Path(panel["frame"]["path"])
        dst = out_frames / src.name
        if src.exists():
            shutil.copy2(src, dst)

        img_src = f"frames/{src.name}"
        time_str = f"{panel['timestamp']:.1f}"
        desc = descriptions[i] if i < len(descriptions) else ""

        if panel["transcript"] == "[silence]":
            transcript_html = '<p class="silence">[silence]</p>'
        else:
            transcript_html = f'<p class="transcript">&ldquo;{panel["transcript"]}&rdquo;</p>'

        panels_html_parts.append(_PANEL_TEMPLATE.format(
            img_src=img_src,
            time=time_str,
            description=desc,
            transcript_html=transcript_html,
        ))

    html = _HTML_TEMPLATE.format(
        video_name=video_name,
        duration=duration,
        panel_count=len(panels),
        panels_html="\n".join(panels_html_parts),
    )

    output_path.write_text(html)
    logger.info("Storyboard written to %s (%d panels)", output_path, len(panels))


def main():
    parser = argparse.ArgumentParser(
        description="Generate a visual storyboard from a video file",
    )
    parser.add_argument("video", help="Path to the video file")
    parser.add_argument(
        "--output", "-o", default=None,
        help="Output HTML file path (default: <video_name>_storyboard.html)",
    )
    args = parser.parse_args()

    video_path = Path(args.video).resolve()
    if not video_path.exists():
        print(f"Error: video not found: {video_path}", file=sys.stderr)
        sys.exit(1)

    video_name = video_path.stem
    if args.output:
        output_path = Path(args.output).resolve()
    else:
        output_path = video_path.parent / f"{video_name}_storyboard.html"

    # Use a persistent temp directory for processing (frames persist for HTML)
    work_dir = Path(tempfile.mkdtemp(prefix="storyboard_"))
    logger.info("Processing %s → %s", video_path, output_path)

    try:
        # 1. Extract frames + audio
        timeout = config.ATTACHMENT_TIMEOUT
        data = _run_helper([EXTRACT_KEYFRAMES, str(video_path), str(work_dir)], timeout)
        if not data:
            print("Error: frame extraction failed", file=sys.stderr)
            sys.exit(1)

        duration = data.get("duration", "unknown")
        frames = data.get("frames", [])
        frame_count = data.get("frame_count", len(frames))
        logger.info("Extracted %d frames, duration %s", frame_count, duration)

        if not frames:
            print("Error: no frames extracted", file=sys.stderr)
            sys.exit(1)

        # 2. Transcribe audio with timestamps
        segments = []
        audio_path = data.get("audio")
        if audio_path:
            logger.info("Transcribing audio...")
            audio_data = _run_helper(
                [TRANSCRIBE_BIN, audio_path, str(timeout)], timeout + 5,
            )
            if audio_data:
                segments = audio_data.get("segments", [])
                transcript = audio_data.get("transcript", "")
                logger.info(
                    "Transcribed %d segments: %s",
                    len(segments), transcript[:80],
                )

        # 3. Align frames to speech segments
        panels = align_frames_to_segments(frames, segments)
        logger.info("Aligned %d panels", len(panels))

        # 4. Ask Claude to describe each panel
        logger.info("Generating panel descriptions via Claude CLI...")
        assistant = ClaudeAssistant(timeout=config.CLI_TIMEOUT)
        descriptions = assistant.describe_storyboard_panels(panels, duration)

        # 5. Generate HTML
        generate_html(panels, descriptions, video_name, duration, output_path, work_dir)
        print(f"Storyboard: {output_path}")

    finally:
        # Clean up work dir (frames were copied to output location)
        shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
