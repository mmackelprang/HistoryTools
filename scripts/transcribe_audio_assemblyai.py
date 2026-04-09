#!/usr/bin/env python3
"""
Audio Transcription with AssemblyAI
- High-accuracy speech-to-text with speaker diarization
- Identifies speakers (Speaker A, Speaker B, etc.)
- Use label_speakers.py afterward to assign real names
- Generates companion .transcript.md files

Usage:
    python transcribe_audio_assemblyai.py                          # all audio files
    python transcribe_audio_assemblyai.py --file path/to/file.mp3  # single file
    python transcribe_audio_assemblyai.py --dry-run                # preview only
"""

import os
import sys
import json
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from config import load_config, load_env

TODAY = datetime.now().strftime("%Y-%m-%d")
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".wma"}


def get_audio_duration(filepath):
    """Get audio duration using ffprobe. Returns (display_string, total_seconds)."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(filepath)],
            capture_output=True, text=True, timeout=30,
        )
        seconds = float(result.stdout.strip())
        mins, secs = divmod(int(seconds), 60)
        hours, mins = divmod(mins, 60)
        display = f"{hours}h {mins}m {secs}s" if hours else f"{mins}m {secs}s"
        return display, seconds
    except Exception:
        return "unknown", 0


def format_timestamp(ms):
    """Convert milliseconds to HH:MM:SS or MM:SS format."""
    total_secs = ms // 1000
    mins, secs = divmod(total_secs, 60)
    hours, mins = divmod(mins, 60)
    if hours:
        return f"{hours}:{mins:02d}:{secs:02d}"
    return f"{mins}:{secs:02d}"


def transcribe_with_assemblyai(audio_path, api_key):
    """Transcribe an audio file using AssemblyAI with speaker diarization."""
    import assemblyai as aai

    aai.settings.api_key = api_key

    config = aai.TranscriptionConfig(
        speaker_labels=True,
        language_code="en",
        speech_models=["universal-3-pro"],
    )

    transcriber = aai.Transcriber()
    transcript = transcriber.transcribe(str(audio_path), config=config)

    if transcript.status == aai.TranscriptStatus.error:
        raise RuntimeError(f"AssemblyAI error: {transcript.error}")

    return transcript


def build_speaker_segments(transcript):
    """Build formatted text with speaker labels and timestamps."""
    segments = []
    speakers_seen = set()

    for utterance in transcript.utterances:
        speaker = f"Speaker {utterance.speaker}"
        speakers_seen.add(utterance.speaker)
        start = format_timestamp(utterance.start)
        end = format_timestamp(utterance.end)
        segments.append(f"**{speaker}** ({start} - {end}): {utterance.text}")

    return "\n\n".join(segments), sorted(speakers_seen)


def create_transcript_md(audio_path, transcript, duration_display):
    """Create a companion .transcript.md file with speaker-labeled segments."""
    stem = audio_path.stem
    parts = stem.split("_", 1)
    date_str = parts[0] if len(parts) > 1 else "undated"

    speaker_text, speaker_list = build_speaker_segments(transcript)
    word_count = len(speaker_text.split())

    if word_count > 200:
        confidence = "high"
    elif word_count > 50:
        confidence = "medium"
    else:
        confidence = "low"

    # Build speaker assignment map
    speaker_map_lines = []
    for s in speaker_list:
        speaker_map_lines.append(f"  {s}: unknown")

    md_path = audio_path.with_suffix(".transcript.md")

    content = f"""---
source_file: {audio_path.name}
transcription_date: {TODAY}
transcription_confidence: {confidence}
transcription_tool: AssemblyAI (speaker diarization)
estimated_date: {date_str}
duration: {duration_display}
speaker_count: {len(speaker_list)}
word_count: {word_count}
notes: Transcribed from {audio_path.name} using AssemblyAI
speaker_assignments:
{chr(10).join(speaker_map_lines)}
---

# {stem.replace('-', ' ').replace('_', ' ').title()}

{speaker_text}
"""
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(content)
    return md_path


def collect_audio_files(dest_root, target_file=None):
    """Collect audio files to process."""
    if target_file:
        p = Path(target_file)
        if not p.is_absolute():
            p = dest_root / p
        if not p.exists():
            print(f"ERROR: File not found: {p}")
            return []
        return [p]

    audio_files = []
    for ext in AUDIO_EXTS:
        audio_files.extend(dest_root.rglob(f"*{ext}"))
    return sorted(audio_files)


def main():
    parser = argparse.ArgumentParser(description="Audio Transcription with AssemblyAI")
    parser.add_argument("--config", default=None, help="Path to config.json")
    parser.add_argument("--file", default=None, help="Transcribe a single audio file")
    parser.add_argument("--force", action="store_true", help="Overwrite existing transcripts")
    parser.add_argument("--dry-run", action="store_true", help="List files without transcribing")
    args = parser.parse_args()

    # Load environment and config
    if not args.dry_run:
        if not load_env():
            sys.exit(1)
        api_key = os.environ.get("ASSEMBLYAI_API_KEY")
        if not api_key:
            print("ERROR: ASSEMBLYAI_API_KEY not set in .env file.")
            print("See SETUP-API-KEYS.md for instructions.")
            sys.exit(1)

    config = load_config(args.config)
    dest_root = config["dest_root"]

    audio_files = collect_audio_files(dest_root, args.file)

    # Skip existing transcripts unless --force
    if not args.force:
        skip_existing = config.get("skip_existing_transcripts", True)
        if skip_existing:
            before = len(audio_files)
            audio_files = [f for f in audio_files if not f.with_suffix(".transcript.md").exists()]
            skipped = before - len(audio_files)
            if skipped:
                print(f"Skipping {skipped} files with existing transcripts (use --force to overwrite)")

    if not audio_files:
        print("No audio files found to transcribe.")
        return

    # Calculate totals
    total_seconds = 0
    file_info = []
    for af in audio_files:
        display, secs = get_audio_duration(af)
        total_seconds += secs
        file_info.append((af, display, secs))

    total_mins = total_seconds / 60
    est_cost = total_mins * 0.01
    print(f"Found {len(audio_files)} audio files ({total_mins:.0f} minutes total)")
    print(f"Estimated cost: ${est_cost:.2f}")

    if args.dry_run:
        print("\n--- DRY RUN (no API calls) ---")
        for af, display, secs in file_info:
            rel = af.relative_to(dest_root) if af.is_relative_to(dest_root) else af
            existing = af.with_suffix(".transcript.md").exists()
            status = "EXISTS (will overwrite)" if existing else "new"
            print(f"  {rel} ({display}) [{status}]")
        print(f"\nTotal: {len(audio_files)} files, {total_mins:.0f} minutes, ~${est_cost:.2f}")
        return

    results = []
    for i, (af, display, secs) in enumerate(file_info, 1):
        rel = af.relative_to(dest_root) if af.is_relative_to(dest_root) else af
        print(f"\n[{i}/{len(audio_files)}] {rel} ({display})")

        try:
            transcript = transcribe_with_assemblyai(af, api_key)
            _, speakers = build_speaker_segments(transcript)
            md_path = create_transcript_md(af, transcript, display)
            word_count = len(transcript.text.split()) if transcript.text else 0
            print(f"  Done: {word_count} words, {len(speakers)} speakers detected")
            results.append({
                "file": str(rel),
                "duration": display,
                "words": word_count,
                "speakers": len(speakers),
                "status": "ok",
            })
        except Exception as e:
            print(f"  ERROR: {e}")
            md_path = af.with_suffix(".transcript.md")
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(
                    f"---\nsource_file: {af.name}\ntranscription_date: {TODAY}\n"
                    f"transcription_confidence: pending\nduration: {display}\n"
                    f"notes: AssemblyAI transcription failed — {e}\n---\n\n"
                    f"[Audio transcription failed — retry or process manually]\n"
                    f"Duration: {display}\n"
                )
            results.append({
                "file": str(rel),
                "duration": display,
                "status": "error",
                "error": str(e),
            })

    ok = sum(1 for r in results if r["status"] == "ok")
    err = sum(1 for r in results if r["status"] == "error")
    print(f"\n{'=' * 60}")
    print(f"Complete: {ok} succeeded, {err} failed")
    print(f"\nNext step: assign speaker names with label_speakers.py")
    print(f"  python label_speakers.py --dir AudioRecordings --map \"A=Alice,B=Bob\"")

    results_path = dest_root / "_assemblyai-audio-results.json"
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Results saved to {results_path}")


if __name__ == "__main__":
    main()
