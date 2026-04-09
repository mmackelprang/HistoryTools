# Setting Up API Keys for AI Features

This guide walks you through getting API keys for the AI-powered features.
All AI features are optional — the toolkit works without them using local tools
(Tesseract for OCR, Whisper for audio).

---

## 1. Google Gemini API Key (PDF transcription, rename proposals, date detection)

The Gemini tools use Google's multimodal AI for handwriting recognition,
intelligent file naming, and date detection.

### Steps:

1. Go to [Google AI Studio](https://aistudio.google.com/apikey)
2. Sign in with your Google account
3. Click **"Create API Key"**
4. Select an existing Google Cloud project, or create a new one
5. Copy the generated API key

### Pricing:

| Model | Input (per 1M tokens) | Output (per 1M tokens) |
|-------|----------------------|------------------------|
| Gemini 2.5 Flash | ~$0.10 | ~$0.40 |
| Gemini 2.5 Pro | ~$1.25 | ~$10.00 |

Google offers a free tier with rate limits (15 requests/minute for Flash).

---

## 2. AssemblyAI API Key (audio transcription with speaker diarization)

AssemblyAI provides high-accuracy speech-to-text with speaker identification.

### Steps:

1. Go to [AssemblyAI](https://www.assemblyai.com/app/account)
2. Create a free account
3. Your API key is shown on the dashboard
4. Copy the API key

### Pricing:

| Feature | Cost per minute |
|---------|----------------|
| Speech-to-Text (Best) | $0.0062 |
| Speaker Diarization | included |

AssemblyAI gives new accounts free credit (typically $50).

---

## 3. Anthropic API Key (transcript formatting)

The formatter uses Claude to add summaries and markdown structure to transcripts.

### Steps:

1. Go to [Anthropic Console](https://console.anthropic.com)
2. Create an account
3. Navigate to API Keys
4. Create and copy a key

### Pricing:

| Model | Input (per 1M tokens) | Output (per 1M tokens) |
|-------|----------------------|------------------------|
| Claude Haiku 4.5 | $0.80 | $4.00 |
| Claude Sonnet 4 | $3.00 | $15.00 |

---

## 4. Adding Keys to Your `.env` File

```bash
cp .env.example .env
```

Edit `.env`:

```ini
GEMINI_API_KEY=your-gemini-key-here
ASSEMBLYAI_API_KEY=your-assemblyai-key-here
ANTHROPIC_API_KEY=your-anthropic-key-here
```

### Verify:

```bash
python scripts/verify_tools.py
```

---

## Security Notes

- **Never commit `.env` to version control.** It's in `.gitignore` by default.
- If you accidentally expose a key, revoke it immediately at the provider's dashboard.
