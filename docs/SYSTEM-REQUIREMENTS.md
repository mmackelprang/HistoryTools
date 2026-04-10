# System Requirements

## Operating System

- **Windows 10/11** — fully tested
- **macOS** — should work (not yet tested)
- **Linux** — should work (CI runs on Ubuntu)

## Python

- **Python 3.10 or later** (tested on 3.10, 3.11, 3.12, 3.13)
- Install from [python.org](https://www.python.org/downloads/)

## Disk Space

- **Archive source files**: varies (your scans, photos, audio)
- **Organized archive**: approximately the same size as source (files are copied, not moved)
- **Temp space for ZIP extraction**: up to 2x the ZIP file size during processing
- **Transcripts**: negligible (~1KB per file)
- **Python packages**: ~500MB (mostly Whisper model data if installed)

## RAM

- **Minimum**: 4GB
- **Recommended**: 8GB+ (Whisper `medium` model needs ~5GB, `large` needs ~10GB)
- **For local OCR**: Tesseract uses ~200MB per page

## Required System Tools

These must be installed separately (not Python packages):

| Tool | Purpose | Install |
|------|---------|---------|
| **Tesseract OCR** | Local OCR for scanned documents | [Download](https://github.com/tesseract-ocr/tesseract) — on Windows, auto-detected at `C:\Program Files\Tesseract-OCR\` |
| **FFmpeg** | Audio/video metadata and conversion | [Download](https://ffmpeg.org/download.html) — on Windows: `winget install Gyan.FFmpeg` |

## Python Packages

All installed automatically via `pip install -e ".[all]"`:

### Core (always needed)

| Package | Purpose | Size |
|---------|---------|------|
| PyMuPDF | PDF text extraction and page rendering | ~30MB |
| Pillow | Image processing | ~10MB |
| python-dotenv | Load API keys from .env | <1MB |

### AI Features (optional)

| Package | Purpose | Size | Required for |
|---------|---------|------|-------------|
| google-genai | Google Gemini API client | ~5MB | PDF transcription (handwriting), rename proposals, date detection |
| assemblyai | AssemblyAI API client | ~2MB | Audio transcription with speaker diarization |
| anthropic | Anthropic Claude API client | ~5MB | Transcript formatting |

### Local Processing (optional)

| Package | Purpose | Size | Required for |
|---------|---------|------|-------------|
| openai-whisper | Local audio transcription | ~400MB+ | Audio transcription without API costs |
| exifread | EXIF metadata reader | <1MB | Photo cataloging |

### Install Options

```bash
# Core only (free features)
pip install -e .

# Core + AI features
pip install -e ".[ai]"

# Core + local audio (Whisper)
pip install -e ".[audio]"

# Everything
pip install -e ".[all]"
```

## GPU (Optional)

A CUDA-capable GPU dramatically speeds up local Whisper transcription:

| Setup | Speed | Install |
|-------|-------|---------|
| CPU only | ~5-10x realtime (1 hour audio = 5-10 hours) | Default |
| NVIDIA GPU | ~0.5-1x realtime (1 hour audio = 30-60 min) | `pip install torch --index-url https://download.pytorch.org/whl/cu121` |

GPU is NOT needed for any AI features (Gemini, AssemblyAI, Claude) — those run in the cloud.
