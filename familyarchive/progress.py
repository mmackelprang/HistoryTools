"""
Progress callback protocol for pipeline operations.

Defines a standard event format that pipeline functions emit to report
progress. The CLI uses print_progress(); the web UI uses an SSE-emitting
callback. Both consume the same library functions.

Usage:
    from familyarchive.progress import ProgressEvent, ProgressCallback

    def my_pipeline(config, on_progress: ProgressCallback = None):
        if on_progress:
            on_progress(ProgressEvent(
                stage="transcribe", stage_number=2, total_stages=9,
                status="processing", file_path="letter.pdf",
                current=3, total=10, message="Transcribing page 3",
            ))
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Callable, Optional


@dataclass
class ProgressEvent:
    """A single progress update from a pipeline stage."""

    stage: str
    """Pipeline stage name: copy, transcribe, format, rename, etc."""

    stage_number: int
    """1-based index of the current stage."""

    total_stages: int
    """Total number of stages in the pipeline."""

    status: str
    """One of: started, processing, completed, error, skipped."""

    file_path: Optional[str] = None
    """Path of the file currently being processed."""

    current: Optional[int] = None
    """1-based index of the current item within this stage."""

    total: Optional[int] = None
    """Total items in this stage."""

    message: Optional[str] = None
    """Human-readable status message."""

    detail: Optional[dict] = None
    """Stage-specific metadata (e.g., bytes_copied, error_message)."""

    def to_dict(self) -> dict:
        """Serialize to a dict for JSON/SSE transmission."""
        return asdict(self)


# Type alias for progress callback functions
ProgressCallback = Callable[[ProgressEvent], None]


def print_progress(event: ProgressEvent) -> None:
    """Default progress callback that prints to stdout.

    Used by the CLI. Web UI replaces this with an SSE-emitting callback.
    """
    prefix = f"[{event.stage_number}/{event.total_stages}] {event.stage}"

    if event.status == "started":
        print(f"\n{'=' * 60}")
        print(f"{prefix}: Starting")
        print(f"{'=' * 60}")
    elif event.status == "processing":
        parts = [prefix]
        if event.current is not None and event.total is not None:
            parts.append(f"({event.current}/{event.total})")
        if event.message:
            parts.append(f"— {event.message}")
        elif event.file_path:
            parts.append(f"— {event.file_path}")
        print("  ".join(parts))
    elif event.status == "completed":
        print(f"{prefix}: Done")
    elif event.status == "error":
        msg = event.message or event.file_path or "unknown error"
        print(f"{prefix}: ERROR — {msg}")
    elif event.status == "skipped":
        msg = event.message or "nothing to do"
        print(f"{prefix}: Skipped — {msg}")
