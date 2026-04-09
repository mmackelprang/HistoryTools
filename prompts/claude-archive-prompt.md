# Claude Prompt — Archive Organization (Standalone)

Use this prompt when starting a new Claude Code session to process a new archive.
Copy the entire block below and paste it as your first message.

---

## Prompt

I have a collection of scanned documents, photos, and audio recordings that I need
organized into a structured, searchable archive.

**Source files:** `[INSERT SOURCE PATH HERE]`
**Output folder:** `[INSERT DESTINATION PATH HERE]`

The HistoryTools toolkit is installed at `[INSERT TOOLKIT PATH HERE]`.

Please process this archive using the following steps:

### 1. Discovery
Scan the source folder recursively. Build an inventory of all files grouped by type
(PDF, image, audio, video, other). Show me file counts, total sizes, and flag any
potential duplicates. Present the inventory and wait for my approval.

### 2. Configure and Preview
Create a `config.json` in the Toolkit folder with the source and destination paths.
Run the organize script in dry-run mode and show me the classification preview.
Wait for my feedback on any misclassified files.

### 3. Process
After I approve:
1. Run the file classification and copying
2. Run PDF transcription (OCR for scans, native extraction for digital PDFs)
3. Run Whisper audio transcription (can be run in background)
4. Generate the photo catalog
5. Run duplicate detection
6. Generate the archive summary report

### 4. Review
Present the final report. Flag any files in NeedsReview, low-confidence
transcriptions, or other items needing my attention.

### Configuration Notes
- Exclude these file types: `.ini`, `.lnk`, `.aup3`, `.db`, `.tmp`
- Exclude these folders: `.organizer`, `.trashbox`
- Use Whisper `base` model for audio (or `medium` if a GPU is available)
- Never modify or delete source files — all work produces copies
- [ADD ANY CUSTOM CLASSIFICATION RULES HERE]
