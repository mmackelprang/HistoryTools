#!/usr/bin/env python3
"""
Run All Steps — Master orchestrator that runs the full pipeline.

Usage:
    python run_all.py                    # uses config.json
    python run_all.py --config path.json
    python run_all.py --dry-run          # preview organize step only
    python run_all.py --skip-audio       # skip slow audio transcription
    python run_all.py --step organize    # run only one step
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent

# Steps that require API keys in .env
AI_STEPS = {"gemini", "assemblyai", "format", "propose"}

STEPS = [
    ("verify",      "verify_tools.py",     "Verifying tools"),
    ("organize",    "organize.py",         "Classifying and copying files"),
    ("transcribe",  "transcribe_pdfs.py",  "Transcribing PDFs"),
    ("audio",       "transcribe_audio.py", "Transcribing audio (Whisper local)"),
    ("gemini",      "transcribe_pdfs_gemini.py",      "Transcribing PDFs with Gemini AI"),
    ("assemblyai",  "transcribe_audio_assemblyai.py",  "Transcribing audio with AssemblyAI"),
    ("format",      "format_transcripts.py",  "Formatting transcripts with AI"),
    ("propose",     "propose_renames.py",     "Proposing file renames"),
    ("photos",      "catalog_photos.py",   "Cataloging photos"),
    ("duplicates",  "duplicate_detect.py", "Detecting duplicates"),
    ("report",      "generate_report.py",  "Generating report"),
]

def run_script(script_name, extra_args=None):
    """Run a toolkit script."""
    script_path = SCRIPTS_DIR / script_name
    cmd = [sys.executable, str(script_path)]
    if extra_args:
        cmd.extend(extra_args)
    print(f"\n{'='*60}")
    print(f"Running: {script_name}")
    print(f"{'='*60}\n")
    result = subprocess.run(cmd)
    return result.returncode == 0

def main():
    parser = argparse.ArgumentParser(description="Run full archive processing pipeline")
    parser.add_argument("--config", default=None, help="Path to config.json")
    parser.add_argument("--dry-run", action="store_true", help="Preview organize step only")
    parser.add_argument("--skip-audio", action="store_true", help="Skip audio transcription")
    parser.add_argument("--with-ai", action="store_true", help="Include AI transcription steps (Gemini, AssemblyAI)")
    parser.add_argument("--step", default=None, help="Run only a specific step")
    args = parser.parse_args()

    extra = []
    if args.config:
        extra.extend(["--config", args.config])

    if args.step:
        for name, script, desc in STEPS:
            if name == args.step:
                step_args = extra.copy()
                if args.dry_run and name == "organize":
                    step_args.append("--dry-run")
                run_script(script, step_args)
                return
        print(f"Unknown step: {args.step}")
        print(f"Available: {', '.join(name for name, _, _ in STEPS)}")
        return

    for name, script, desc in STEPS:
        if name == "audio" and args.skip_audio:
            print(f"\n[SKIPPED] {desc}")
            continue

        if name in AI_STEPS and not args.with_ai:
            print(f"\n[SKIPPED] {desc} (use --with-ai to include)")
            continue

        step_args = extra.copy()
        if args.dry_run:
            if name == "organize":
                step_args.append("--dry-run")
            elif name != "verify":
                print(f"\n[SKIPPED in dry-run] {desc}")
                continue

        success = run_script(script, step_args)
        if not success and name == "verify":
            print("\nTool verification failed. Install missing tools before proceeding.")
            print("Run with --step organize to skip verification.")
            return

    print(f"\n{'='*60}")
    print("Pipeline complete!")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
