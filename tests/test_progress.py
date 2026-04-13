"""Tests for the progress callback protocol."""

from familyarchive.progress import ProgressEvent, ProgressCallback


def test_progress_event_creation():
    """ProgressEvent can be created with required fields."""
    event = ProgressEvent(
        stage="transcribe",
        stage_number=2,
        total_stages=9,
        status="processing",
    )
    assert event.stage == "transcribe"
    assert event.stage_number == 2
    assert event.total_stages == 9
    assert event.status == "processing"
    assert event.file_path is None
    assert event.current is None
    assert event.total is None
    assert event.message is None
    assert event.detail is None


def test_progress_event_with_all_fields():
    """ProgressEvent accepts all optional fields."""
    event = ProgressEvent(
        stage="copy",
        stage_number=1,
        total_stages=9,
        status="processing",
        file_path="/archive/Letters/letter.pdf",
        current=47,
        total=500,
        message="Copying file 47 of 500",
        detail={"bytes_copied": 1024},
    )
    assert event.file_path == "/archive/Letters/letter.pdf"
    assert event.current == 47
    assert event.total == 500
    assert event.message == "Copying file 47 of 500"
    assert event.detail == {"bytes_copied": 1024}


def test_progress_event_status_values():
    """ProgressEvent status field accepts all valid values."""
    for status in ("started", "processing", "completed", "error", "skipped"):
        event = ProgressEvent(
            stage="test", stage_number=1, total_stages=1, status=status
        )
        assert event.status == status


def test_progress_callback_type():
    """ProgressCallback type alias works with a real function."""
    received = []

    def my_callback(event: ProgressEvent) -> None:
        received.append(event)

    callback: ProgressCallback = my_callback
    event = ProgressEvent(
        stage="format", stage_number=6, total_stages=9, status="started"
    )
    callback(event)
    assert len(received) == 1
    assert received[0].stage == "format"


def test_progress_event_to_dict():
    """ProgressEvent can be serialized to a dict for SSE/JSON."""
    event = ProgressEvent(
        stage="transcribe",
        stage_number=2,
        total_stages=9,
        status="processing",
        file_path="letter.pdf",
        current=3,
        total=10,
        message="Transcribing page 3",
    )
    d = event.to_dict()
    assert d["stage"] == "transcribe"
    assert d["stage_number"] == 2
    assert d["current"] == 3
    assert d["file_path"] == "letter.pdf"
    assert "detail" not in d or d["detail"] is None


def test_print_callback():
    """Built-in print_progress callback prints to stdout."""
    from familyarchive.progress import print_progress
    import io
    import sys

    event = ProgressEvent(
        stage="copy",
        stage_number=1,
        total_stages=9,
        status="processing",
        file_path="letter.pdf",
        current=3,
        total=10,
        message="Copying file 3 of 10",
    )

    captured = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = captured
    try:
        print_progress(event)
    finally:
        sys.stdout = old_stdout

    output = captured.getvalue()
    assert "copy" in output.lower() or "Copying" in output
