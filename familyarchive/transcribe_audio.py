#!/usr/bin/env python3
"""
Audio Transcription Script (Generalized)
Uses OpenAI Whisper to transcribe MP3/WAV/M4A files.
Generates companion .transcript.md files.

Usage:
    python transcribe_audio.py                    # uses config.json
    python transcribe_audio.py --config path.json
    python transcribe_audio.py --model medium      # override whisper model
"""

import os
import sys
import json
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from config import load_config

TODAY = datetime.now().strftime("%Y-%m-%d")
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".wma"}

def get_audio_duration(filepath):
    """Get audio duration using ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(filepath)],
            capture_output=True, text=True, timeout=30
        )
        seconds = float(result.stdout.strip())
        mins, secs = divmod(int(seconds), 60)
        hours, mins = divmod(mins, 60)
        return f"{hours}h {mins}m {secs}s" if hours else f"{mins}m {secs}s"
    except Exception:
        return "unknown"

def create_transcript_md(audio_path, transcript_text, duration, model_name):
    """Create a companion .transcript.md file."""
    stem = audio_path.stem
    parts = stem.split("_", 1)
    date_str = parts[0] if len(parts) > 1 else "undated"

    confidence = "high" if len(transcript_text) > 200 else ("medium" if len(transcript_text) > 50 else "low")
    md_path = audio_path.with_suffix(".transcript.md")

    content = f"""---
source_file: {audio_path.name}
transcription_date: {TODAY}
transcription_confidence: {confidence}
transcription_tool: OpenAI Whisper ({model_name} model)
estimated_date: {date_str}
duration: {duration}
notes: Auto-transcribed from {audio_path.name}
---

# {stem.replace('-', ' ').replace('_', ' ').title()}

{transcript_text}
"""
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(content)
    return md_path

def main():
    parser = argparse.ArgumentParser(description="Audio Transcription with Whisper")
    parser.add_argument("--config", default=None)
    parser.add_argument("--model", default=None, help="Whisper model: tiny, base, small, medium, large")
    args = parser.parse_args()

    config = load_config(args.config)
    dest_root = config["dest_root"]
    model_name = args.model or config.get("whisper_model", "base")
    skip_existing = config["skip_existing_transcripts"]

    # Find all audio files
    audio_files = []
    for ext in AUDIO_EXTS:
        audio_files.extend(dest_root.rglob(f"*{ext}"))
    audio_files = sorted(audio_files)

    if skip_existing:
        audio_files = [f for f in audio_files if not f.with_suffix(".transcript.md").exists()]

    print(f"Found {len(audio_files)} audio files to transcribe")
    if not audio_files:
        print("Nothing to do.")
        return

    # Load Whisper
    import whisper
    print(f"Loading Whisper model ({model_name})...")
    model = whisper.load_model(model_name)
    print("Model loaded.")

    results = []
    for i, audio in enumerate(audio_files, 1):
        rel = audio.relative_to(dest_root)
        duration = get_audio_duration(audio)
        print(f"\n[{i}/{len(audio_files)}] {rel} ({duration})")

        try:
            result = model.transcribe(str(audio), language="en")
            text = result["text"].strip()
            print(f"  Transcribed: {len(text)} characters")

            create_transcript_md(audio, text, duration, model_name)
            results.append({"file": str(rel), "duration": duration,
                          "chars": len(text), "status": "ok"})
        except Exception as e:
            print(f"  ERROR: {e}")
            # Create error stub
            md_path = audio.with_suffix(".transcript.md")
            with open(md_path, 'w', encoding='utf-8') as f:
                f.write(f"---\nsource_file: {audio.name}\ntranscription_date: {TODAY}\n"
                       f"transcription_confidence: pending\nduration: {duration}\n"
                       f"notes: Transcription failed — {e}\n---\n\n"
                       f"[Audio transcription failed — process manually]\nDuration: {duration}\n")
            results.append({"file": str(rel), "duration": duration,
                          "status": "error", "error": str(e)})

    ok = sum(1 for r in results if r["status"] == "ok")
    err = sum(1 for r in results if r["status"] == "error")
    print(f"\n{'='*60}")
    print(f"Complete: {ok} succeeded, {err} failed")

    # Write queue file
    failed = [r for r in results if r["status"] == "error"]
    queue_path = dest_root / "_audio-transcription-queue.md"
    if failed:
        lines = [f"# Audio Transcription Queue\n\nGenerated: {TODAY}\n\n"]
        for r in failed:
            lines.append(f"- `{r['file']}` — Duration: {r['duration']} — Error: {r.get('error','unknown')}\n")
        with open(queue_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
    else:
        with open(queue_path, 'w', encoding='utf-8') as f:
            f.write(f"# Audio Transcription Queue\n\nGenerated: {TODAY}\n\n"
                   f"All {len(results)} audio files successfully transcribed.\n")

    with open(dest_root / "_audio-results.json", 'w') as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    main()
