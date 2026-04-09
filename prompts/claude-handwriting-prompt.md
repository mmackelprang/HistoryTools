# Claude Prompt — Handwritten Letter Transcription

Use this when you want Claude to transcribe a handwritten letter or document
that Tesseract OCR couldn't handle well.

Open a new Claude conversation (web or desktop) and use this prompt.
Drag and drop the PDF or image file into the conversation.

---

## Prompt

I'm building a family archive. Please transcribe this handwritten document.

Rules:
1. Preserve the original formatting: salutation, paragraphs, closing, signature
2. Mark illegible words with `[illegible]`
3. Mark uncertain readings with `[possibly: word]`
4. After the transcription, provide:
   - Your best estimate of the date (from content clues or the document itself)
   - The sender and recipient if determinable
   - Any notable observations (paper condition, ink color, emotional tone)

Format the transcription in Markdown. Start with this metadata block:

```
---
source_file: [filename]
transcription_date: [today]
transcription_confidence: [high/medium/low]
estimated_date: [YYYY-MM-DD]
sender: [name]
recipient: [name]
notes: [observations]
---
```

Then the full transcription text.
