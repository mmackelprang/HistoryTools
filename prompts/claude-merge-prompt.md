# Claude Prompt — Merge Into Existing Archive

Use this prompt when you have a new batch of files to add into an existing
organized archive. Copy the block below and paste as your first message.

---

## Prompt

I have new files to merge into my existing organized archive.

**New source files:** `[INSERT SOURCE PATH HERE]`
**Existing archive:** `[INSERT ARCHIVE PATH HERE]`

The HistoryTools toolkit is at `[INSERT TOOLKIT PATH HERE]`.

Please merge these new files into the existing archive:

### 1. Discovery
Scan the new source folder. Show me what's there — file counts by type,
total size, and any files that might duplicate what's already in the archive.

### 2. Configure
Create a `config.json` with:
- `source_root` pointing to the new files
- `dest_root` pointing to your existing archive
- `mode` set to `"merge"`

Run `organize.py --dry-run` to preview where new files will land.
Show me the preview and wait for approval.

### 3. Merge
After I approve:
1. Run the organize script (merge mode skips existing files)
2. Transcribe any new PDFs in Letters/Journals/Cards/Documents/FamilyMembers
3. Transcribe any new audio files
4. Update the photo catalog
5. Run deduplication across old + new files
6. Regenerate the summary report

### 4. Review
Show me:
- How many new files were added vs skipped
- Any merge conflicts (files that would have overwritten existing ones)
- New files that landed in NeedsReview
- Updated archive statistics
