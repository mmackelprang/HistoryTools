# Setting Up API Keys for AI Features

All AI features are **optional**. The toolkit works without them using free local tools
(Tesseract for OCR, Whisper for audio). AI features provide better quality, especially
for handwritten documents and speaker identification in audio.

---

## Quick Cost Estimator

Before setting up API keys, here's what processing typically costs:

| Archive size | PDFs (AI only) | Audio | Formatting | Renaming | Total |
|-------------|---------------|-------|------------|----------|-------|
| Small (100 files) | ~$0.05 | ~$1.00 | ~$0.02 | ~$0.02 | ~$1.10 |
| Medium (500 files) | ~$0.25 | ~$5.00 | ~$0.10 | ~$0.10 | ~$5.50 |
| Large (2000 files) | ~$1.00 | ~$20.00 | ~$0.40 | ~$0.40 | ~$22.00 |

**Important**: The tiered transcription approach means only handwritten/low-confidence
PDFs go to AI. Typically 20-30% of PDFs need AI -- the rest are handled free by
Tesseract OCR. Audio always requires AI (or local Whisper).

---

## AI Services and Recommended Models

### 1. Google Gemini -- PDF Transcription, Rename Proposals, Date Detection

**What it does**: Reads page images with AI vision to transcribe handwriting, proposes
descriptive filenames, and detects dates in undated documents.

**Recommended model**: `gemini-2.5-flash` (default) -- best cost/quality ratio

| Model | Input (per 1M tokens) | Output (per 1M tokens) | Best for |
|-------|----------------------|------------------------|----------|
| **gemini-2.5-flash** | ~$0.15 | ~$0.60 | Default. Fast, cheap, good quality |
| gemini-2.5-pro | ~$1.25-2.50 | ~$10.00-15.00 | Difficult handwriting, complex docs |

**Free tier**: 15 requests/minute, sufficient for small archives.

**To override model**: `family-archive transcribe --model gemini-2.5-pro`

#### Setup:

1. Go to [Google AI Studio](https://aistudio.google.com/apikey)
2. Sign in with your Google account
3. Click **"Create API Key"**
4. Select or create a Google Cloud project
5. Copy the generated API key

---

### 2. AssemblyAI -- Audio Transcription with Speaker Diarization

**What it does**: Transcribes audio files with speaker identification (Speaker A, Speaker B, etc.)
and timestamps.

**Recommended model**: `universal-3-pro` (default) -- highest accuracy

| Feature | Cost |
|---------|------|
| Speech-to-Text | $0.0062/minute |
| Speaker Diarization | included |
| **Total** | **~$0.37/hour** |

**Free tier**: New accounts get ~$50 in free credit (enough for ~135 hours of audio).

**Alternative (free)**: Use local Whisper instead (`python scripts/transcribe_audio.py`).
Whisper is free but slower, requires more RAM, and doesn't identify speakers.

#### Setup:

1. Go to [AssemblyAI Dashboard](https://www.assemblyai.com/app/account)
2. Create a free account
3. Copy your API key from the dashboard

---

### 3. Anthropic Claude -- Transcript Formatting

**What it does**: Adds summaries, markdown headers, topic sections, and clean formatting
to raw transcripts. Makes transcripts readable and searchable.

**Recommended model**: `claude-haiku-4-5-20251001` (default) -- fast, cheap, excellent at formatting

| Model | Input (per 1M tokens) | Output (per 1M tokens) | Best for |
|-------|----------------------|------------------------|----------|
| **claude-haiku-4-5** | ~$0.80 | ~$4.00 | Default. Fast, cheap, great at formatting |
| claude-sonnet-4 | ~$3.00 | ~$15.00 | Better summaries for important documents |

**To override model**: `family-archive format --model claude-sonnet-4-20250514`

#### Setup:

1. Go to [Anthropic Console](https://console.anthropic.com)
2. Create an account
3. Navigate to API Keys -> Create key
4. Copy the key

---

## Adding Keys to Your `.env` File

```bash
cp .env.example .env
```

Edit `.env` with your keys:

```ini
# Required for: PDF transcription (handwriting), rename proposals, date detection
GEMINI_API_KEY=your-gemini-key-here

# Required for: Audio transcription with speaker identification
ASSEMBLYAI_API_KEY=your-assemblyai-key-here

# Required for: Transcript formatting with summaries
ANTHROPIC_API_KEY=your-anthropic-key-here
```

You don't need all three -- only set up the services you want to use:

| If you only want... | You need... |
|---------------------|-------------|
| PDF handwriting transcription | Gemini |
| Audio transcription | AssemblyAI (or use free Whisper) |
| Transcript formatting | Anthropic |
| Rename proposals + date detection | Gemini |
| Everything | All three |

### Verify:

```bash
family-archive verify
```

---

## Model Selection Best Practices

### For PDF Transcription (Gemini)

- **Start with `gemini-2.5-flash`** -- it handles 95% of documents well
- **Use `gemini-2.5-pro`** only for difficult handwriting that Flash misreads
- **Run free Tesseract first** -- `python scripts/transcribe_pdfs.py` handles typed/printed docs for free
- **Use `--low-confidence-only`** to only send handwritten docs to AI

```bash
# Best practice workflow:
python scripts/transcribe_pdfs.py                    # free: handles printed text
family-archive transcribe --low-confidence-only       # paid: only handwriting
```

### For Audio Transcription (AssemblyAI vs Whisper)

| Feature | AssemblyAI (paid) | Whisper (free) |
|---------|------------------|----------------|
| Accuracy | Excellent | Good |
| Speaker ID | Yes (Speaker A, B, C) | No |
| Speed | Fast (cloud) | Slow (local CPU) |
| Cost | ~$0.37/hour | Free |
| GPU needed | No | Helps a lot |
| Best for | Important recordings | Background processing |

**Best practice**: Use AssemblyAI for recordings with multiple speakers. Use Whisper
for single-speaker recordings or when you don't need speaker identification.

### For Transcript Formatting (Claude)

- **Use Haiku** for batch formatting -- it's 4x cheaper than Sonnet and handles formatting well
- **Use Sonnet** for your most important documents where summary quality matters
- **For very large files** (50K+ words), the formatter automatically chunks and processes serially

### Cost Control Tips

1. **Run free tools first**: `python scripts/transcribe_pdfs.py` before AI transcription
2. **Use `--dry-run`** on every AI command to see what it will process
3. **Process one folder at a time**: `--folder Letters` to control spending
4. **Use `--low-confidence-only`** to only pay for files that need AI
5. **Check your API dashboard** regularly for usage

---

## Swapping AI Vendors

Each AI step supports model override via CLI flags:

| Step | Default vendor/model | Override flag |
|------|---------------------|---------------|
| PDF transcription | Gemini 2.5 Flash | `--model gemini-2.5-pro` |
| Audio transcription | AssemblyAI universal-3-pro | Use Whisper: `python scripts/transcribe_audio.py` |
| Formatting | Claude Haiku 4.5 | `--model claude-sonnet-4-20250514` |
| Rename proposals | Gemini 2.5 Flash | `--model gemini-2.5-pro` |
| Date detection | Gemini 2.5 Flash | `--model gemini-2.5-pro` |

**Full vendor swapping** (e.g., using OpenAI instead of Gemini, or Gemini instead of Claude)
is planned for a future release via the config system. The prompts are vendor-agnostic --
only the API client code is vendor-specific.

---

## Security Notes

- **Never commit `.env` to version control.** It's in `.gitignore` by default.
- If you accidentally expose a key, revoke it immediately:
  - Gemini: [Google AI Studio](https://aistudio.google.com/apikey)
  - AssemblyAI: [Dashboard](https://www.assemblyai.com/app/account)
  - Anthropic: [Console](https://console.anthropic.com)
