# MS Office Document Extraction — Design Spec

## Goal

Extract text from DOC, DOCX, XLS, XLSX files and generate `.transcript.md` files, making Office documents searchable and integrated with the existing pipeline (search index, duplicate detection, etc.). Pluggable extractor design makes it easy to add new formats later.

## Architecture

- **`scripts/core/extract.py`** — Registry of extension-to-extractor-function mappings, 4 extractors (DOCX, DOC, XLSX, XLS), and transcript generation. Single file, ~250 lines.
- **`scripts/extract_docs.py`** — CLI pipeline script. Walks archive, finds supported files, calls extractors, writes transcripts.
- No AI calls, no batching — extraction is local and instant.

## Design Principles

- **Pluggable extractors** — registry pattern maps file extensions to extractor functions. Adding a new format is one decorated function.
- **Same output format** — `.transcript.md` files use the same frontmatter format as PDF transcripts, so they integrate with search, duplicates, and everything else.
- **Pure Python** — no external tools required. python-docx, openpyxl, xlrd, olefile handle all formats.
- **Easy to extend** — when new formats appear in the archive, add an extractor function and register it.

## Extractor Registry

```python
EXTRACTORS = {}

def register(ext):
    """Decorator to register an extractor for a file extension."""
    def decorator(fn):
        EXTRACTORS[ext] = fn
        return fn
    return decorator

def extract_file(path):
    """Extract text and metadata from a supported file.
    
    Returns (text, metadata) where metadata includes word_count, format,
    and format-specific fields.
    
    Raises UnsupportedFormatError if no extractor registered.
    """

def get_supported_extensions():
    """Return all registered extensions."""
    return set(EXTRACTORS.keys())
```

## Extractors

### `.docx` — python-docx

- Reads all paragraphs, preserves paragraph breaks
- Extracts text from tables (row by row)
- Metadata: word_count, format="docx"

### `.doc` — olefile

- Parses the binary OLE2 compound document format
- Extracts text from the WordDocument stream
- Metadata: word_count, format="doc"

### `.xlsx` — openpyxl

- Reads all sheets, extracts cell values
- Each sheet becomes a section with header
- Metadata: word_count, format="xlsx", sheet_count

### `.xls` — xlrd

- Reads all sheets from the legacy binary format
- Same output structure as XLSX (sheet sections)
- Metadata: word_count, format="xls", sheet_count

## Transcript Output

Each extractor produces a `.transcript.md` alongside the source file:

```markdown
---
source_file: letter.docx
transcription_date: 2026-04-12
transcription_confidence: high
transcription_method: extract (python-docx)
word_count: 842
---

[extracted text body]
```

- Confidence is always `high` (exact text extraction, not OCR)
- `transcription_method` uses `extract (<library>)` to distinguish from AI vision
- Body text preserves paragraphs; Excel files have `## Sheet: <name>` headers

## CLI Command

```
family-archive extract                              # extract all supported files
family-archive extract --folder NeedsReview          # limit to folder
family-archive extract --file path/to/doc.docx       # single file
family-archive extract --dry-run                     # preview without extracting
family-archive extract --force                       # overwrite existing transcripts
```

Synchronous command — no batch/collect workflow. Walks the archive, finds files with supported extensions that lack `.transcript.md` files (or all files with `--force`), extracts text, writes transcripts, prints progress.

## Dependencies

New entries in `pyproject.toml` dependencies:

- `python-docx>=1.0.0` — DOCX extraction
- `openpyxl>=3.1.0` — XLSX extraction
- `xlrd>=2.0.0` — XLS extraction (legacy binary format)
- `olefile>=0.47` — DOC binary format parsing

All pure Python, no external tools.

## File Map

### New files
- `scripts/core/extract.py` — registry, 4 extractors, transcript generation
- `scripts/extract_docs.py` — CLI pipeline script
- `tests/test_extract.py` — extractor tests

### Modified files
- `scripts/cli.py` — add `extract` subcommand
- `pyproject.toml` — add 4 new dependencies
- `docs/WORKFLOW.md` — add extract step

## Future Extensions

New formats can be added by writing one function and decorating it:

```python
@register(".rtf")
def extract_rtf(path):
    # ... parse RTF ...
    return text, {"word_count": len(text.split()), "format": "rtf"}
```

Candidates for future extractors: RTF, PPT/PPTX, ODT/ODS, plain text (.txt), CSV, HTML.
