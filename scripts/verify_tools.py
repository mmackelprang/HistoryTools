#!/usr/bin/env python3
"""
Tool Verification Script
Checks that all required tools are installed and working.
Run this first before processing any archive.
"""

import os
import subprocess
import sys
from pathlib import Path

def check(name, test_fn):
    """Run a check and report result."""
    try:
        result = test_fn()
        print(f"  [OK]  {name}: {result}")
        return True
    except Exception as e:
        print(f"  [FAIL] {name}: {e}")
        return False

def main():
    print("=" * 60)
    print("Archive Organizer — Tool Verification")
    print("=" * 60)

    # Load .env if it exists (for API key checks)
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        from config import load_env
        load_env()
    except Exception:
        pass

    results = []

    # Python version
    results.append(check("Python", lambda: f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"))

    # Pillow
    results.append(check("Pillow (image processing)", lambda: __import__("PIL").__version__))

    # PyMuPDF
    def check_pymupdf():
        import fitz
        return f"version {fitz.version[0]}"
    results.append(check("PyMuPDF (PDF processing)", check_pymupdf))

    # exifread
    results.append(check("exifread (EXIF metadata)", lambda: __import__("exifread").__version__))

    # Whisper
    def check_whisper():
        import whisper
        return f"version {whisper.__version__}"
    results.append(check("OpenAI Whisper (audio transcription)", check_whisper))

    # Google Generative AI (Gemini)
    def check_genai():
        from google import genai
        key = os.environ.get("GEMINI_API_KEY", "")
        status = "API key set" if key else "API key NOT set (check .env)"
        return f"installed — {status}"
    results.append(check("Google GenAI / Gemini (AI PDF transcription)", check_genai))

    # AssemblyAI
    def check_assemblyai():
        import assemblyai
        key = os.environ.get("ASSEMBLYAI_API_KEY", "")
        status = "API key set" if key else "API key NOT set (check .env)"
        return f"installed — {status}"
    results.append(check("AssemblyAI (AI audio transcription)", check_assemblyai))

    # python-dotenv
    results.append(check("python-dotenv (.env loader)", lambda: __import__("dotenv").__name__))

    # Tesseract
    def check_tesseract():
        paths = [
            "tesseract",
        ]
        for p in paths:
            try:
                r = subprocess.run([p, "--version"], capture_output=True, text=True, timeout=10)
                version = r.stdout.split("\n")[0] if r.stdout else r.stderr.split("\n")[0]
                return f"{version} at {p}"
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
        raise FileNotFoundError("tesseract not found — install from https://github.com/UB-Mannheim/tesseract/wiki")
    results.append(check("Tesseract OCR", check_tesseract))

    # FFmpeg
    def check_ffmpeg():
        r = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=10)
        return r.stdout.split("\n")[0]
    results.append(check("FFmpeg (audio metadata)", check_ffmpeg))

    # CUDA / GPU
    def check_gpu():
        import torch
        if torch.cuda.is_available():
            return f"CUDA available — {torch.cuda.get_device_name(0)}"
        return "CPU only (Whisper will be slow for long audio files)"
    results.append(check("GPU acceleration", check_gpu))

    # Summary
    passed = sum(results)
    total = len(results)
    print(f"\n{'=' * 60}")
    print(f"Results: {passed}/{total} checks passed")

    if passed < total:
        print("\nTo install missing tools:")
        print("  pip install PyMuPDF exifread openai-whisper Pillow")
        print("  Install Tesseract OCR from: https://github.com/UB-Mannheim/tesseract/wiki")
        print("  Install FFmpeg from: https://ffmpeg.org/download.html")
    else:
        print("\nAll tools ready. You can proceed with archive processing.")

    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
