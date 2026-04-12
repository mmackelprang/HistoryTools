# MS Office Document Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract text from DOC, DOCX, XLS, XLSX files and generate `.transcript.md` files so Office documents are searchable and integrated with the existing pipeline.

**Architecture:** A pluggable extractor registry in `scripts/core/extract.py` maps file extensions to extractor functions. A pipeline script `scripts/extract_docs.py` walks the archive and calls extractors. CLI command `family-archive extract` exposes the functionality.

**Tech Stack:** Python 3.10+, python-docx, openpyxl, xlrd, olefile

**Design spec:** `docs/2026-04-12-office-extraction-design.md`

---

## File Structure

| File | Responsibility |
|------|---------------|
| `scripts/core/extract.py` | Extractor registry, 4 extractors, transcript generation |
| `scripts/extract_docs.py` | CLI pipeline script (file collection, progress, summary) |
| `scripts/cli.py` | Add `extract` subcommand |
| `pyproject.toml` | Add 4 new dependencies |
| `tests/test_extract.py` | Extractor and pipeline tests |
| `docs/WORKFLOW.md` | Add extract step |

---

### Task 1: Add dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add extraction dependencies**

In `pyproject.toml`, add the 4 new libraries to the `dependencies` list:

```toml
dependencies = [
    "PyMuPDF>=1.23.0",
    "Pillow>=10.0.0",
    "python-dotenv>=1.0.0",
    "imagehash>=4.3.0",
    "python-docx>=1.0.0",
    "openpyxl>=3.1.0",
    "xlrd>=2.0.0",
    "olefile>=0.47",
]
```

- [ ] **Step 2: Install and verify**

Run: `pip install -e ".[all]"`
Run: `python -c "import docx; import openpyxl; import xlrd; import olefile; print('all imports ok')"`
Expected: prints "all imports ok"

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "build: add python-docx, openpyxl, xlrd, olefile for document extraction"
```

---

### Task 2: Extractor registry and DOCX extractor

**Files:**
- Create: `scripts/core/extract.py`
- Create: `tests/test_extract.py`

- [ ] **Step 1: Write failing tests for registry and DOCX extraction**

Create `tests/test_extract.py`:

```python
"""
Tests for the document extraction module (scripts/core/extract.py).
"""

from pathlib import Path

import pytest

from scripts.core.extract import (
    extract_file,
    get_supported_extensions,
    create_extract_transcript,
    UnsupportedFormatError,
)


def make_file(path: Path, content: str = "test") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


class TestRegistry:
    """Test the extractor registry."""

    def test_supported_extensions_includes_docx(self):
        exts = get_supported_extensions()
        assert ".docx" in exts

    def test_unsupported_extension_raises(self, tmp_path):
        path = make_file(tmp_path / "file.xyz", "content")
        with pytest.raises(UnsupportedFormatError):
            extract_file(path)


class TestDocxExtractor:
    """Test DOCX text extraction."""

    def _make_docx(self, path, paragraphs):
        """Create a test DOCX file with the given paragraphs."""
        from docx import Document
        doc = Document()
        for para in paragraphs:
            doc.add_paragraph(para)
        path.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(path))
        return path

    def test_extract_docx_text(self, tmp_path):
        path = self._make_docx(
            tmp_path / "letter.docx",
            ["Dear Alice,", "We drove to Springfield last week.", "Love, Bob"]
        )
        text, metadata = extract_file(path)
        assert "Dear Alice" in text
        assert "Springfield" in text
        assert "Love, Bob" in text

    def test_extract_docx_metadata(self, tmp_path):
        path = self._make_docx(tmp_path / "doc.docx", ["Hello world"])
        text, metadata = extract_file(path)
        assert metadata["format"] == "docx"
        assert metadata["word_count"] == 2

    def test_extract_docx_preserves_paragraphs(self, tmp_path):
        path = self._make_docx(tmp_path / "doc.docx", ["Paragraph one.", "Paragraph two."])
        text, metadata = extract_file(path)
        assert "Paragraph one." in text
        assert "Paragraph two." in text
        # Paragraphs should be separated
        assert text.index("Paragraph one.") < text.index("Paragraph two.")

    def test_extract_docx_with_table(self, tmp_path):
        """DOCX with a table should extract cell text."""
        from docx import Document
        doc = Document()
        doc.add_paragraph("Before table")
        table = doc.add_table(rows=2, cols=2)
        table.cell(0, 0).text = "Name"
        table.cell(0, 1).text = "Value"
        table.cell(1, 0).text = "Alice"
        table.cell(1, 1).text = "100"
        doc.add_paragraph("After table")
        path = tmp_path / "table.docx"
        doc.save(str(path))
        text, metadata = extract_file(path)
        assert "Name" in text
        assert "Alice" in text
        assert "100" in text


class TestTranscriptGeneration:
    """Test .transcript.md creation from extracted text."""

    def test_creates_transcript_file(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        source = make_file(dest / "Letters" / "letter.docx", "dummy")
        md_path = create_extract_transcript(
            source, "Dear Alice, hello.", {"word_count": 3, "format": "docx"}, dest
        )
        assert md_path.exists()
        assert md_path.name == "letter.transcript.md"

    def test_transcript_has_frontmatter(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        source = make_file(dest / "doc.docx", "dummy")
        md_path = create_extract_transcript(
            source, "Hello world.", {"word_count": 2, "format": "docx"}, dest
        )
        content = md_path.read_text(encoding="utf-8")
        assert "source_file: doc.docx" in content
        assert "transcription_confidence: high" in content
        assert "transcription_method: extract (docx)" in content
        assert "word_count: 2" in content

    def test_transcript_has_body(self, tmp_path):
        dest = tmp_path / "archive"
        dest.mkdir()
        source = make_file(dest / "doc.docx", "dummy")
        md_path = create_extract_transcript(
            source, "The full body text.", {"word_count": 4, "format": "docx"}, dest
        )
        content = md_path.read_text(encoding="utf-8")
        assert "The full body text." in content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_extract.py -v`
Expected: FAIL — `scripts.core.extract` doesn't exist

- [ ] **Step 3: Implement registry, DOCX extractor, and transcript generation**

Create `scripts/core/extract.py`:

```python
"""
Document text extraction for the Family Archive.

Pluggable registry of extractors that map file extensions to extraction
functions. Each extractor takes a file path and returns (text, metadata).
Adding a new format is one decorated function.
"""

import os
from pathlib import Path
from datetime import datetime

TODAY = datetime.now().strftime("%Y-%m-%d")

# ── Registry ──────────────────────────────────────────────────────────────

EXTRACTORS = {}


class UnsupportedFormatError(ValueError):
    """Raised when no extractor is registered for a file extension."""
    pass


def register(ext):
    """Decorator to register an extractor for a file extension."""
    def decorator(fn):
        EXTRACTORS[ext.lower()] = fn
        return fn
    return decorator


def extract_file(path):
    """Extract text and metadata from a supported file.

    Args:
        path: Path to the file.

    Returns:
        Tuple of (text, metadata) where text is the extracted content
        and metadata is a dict with keys like word_count, format.

    Raises:
        UnsupportedFormatError if no extractor registered for the extension.
    """
    path = Path(path)
    ext = path.suffix.lower()
    if ext not in EXTRACTORS:
        raise UnsupportedFormatError(f"No extractor for {ext}")
    return EXTRACTORS[ext](path)


def get_supported_extensions():
    """Return set of all registered file extensions."""
    return set(EXTRACTORS.keys())


# ── Transcript generation ─────────────────────────────────────────────────


def create_extract_transcript(file_path, text, metadata, dest_root):
    """Write a .transcript.md file for an extracted document.

    Args:
        file_path: Path to the source document.
        text: Extracted text body.
        metadata: Dict with word_count, format, and optional fields.
        dest_root: Archive root directory.

    Returns:
        Path to the created .transcript.md file.
    """
    file_path = Path(file_path)
    md_path = file_path.with_suffix(".transcript.md")
    fmt = metadata.get("format", "unknown")
    word_count = metadata.get("word_count", len(text.split()))

    content = f"""---
source_file: {file_path.name}
transcription_date: {TODAY}
transcription_confidence: high
transcription_method: extract ({fmt})
word_count: {word_count}
---

{text}
"""
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(content)
    return md_path


# ── Extractors ────────────────────────────────────────────────────────────


@register(".docx")
def extract_docx(path):
    """Extract text from a DOCX file using python-docx."""
    from docx import Document

    doc = Document(str(path))
    parts = []

    # Extract paragraphs
    for para in doc.paragraphs:
        if para.text.strip():
            parts.append(para.text)

    # Extract tables
    for table in doc.tables:
        for row in table.rows:
            row_text = "\t".join(cell.text.strip() for cell in row.cells if cell.text.strip())
            if row_text:
                parts.append(row_text)

    text = "\n\n".join(parts)
    word_count = len(text.split())
    return text, {"word_count": word_count, "format": "docx"}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_extract.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/core/extract.py tests/test_extract.py
git commit -m "feat: add extractor registry and DOCX extraction

- Pluggable registry maps extensions to extractor functions
- extract_file() entry point with UnsupportedFormatError
- DOCX extractor using python-docx (paragraphs + tables)
- create_extract_transcript() writes .transcript.md files
- get_supported_extensions() for discovery"
```

---

### Task 3: DOC extractor (binary Word)

**Files:**
- Modify: `scripts/core/extract.py`
- Modify: `tests/test_extract.py`

- [ ] **Step 1: Write failing tests for DOC extraction**

Add to `tests/test_extract.py`:

```python
class TestDocExtractor:
    """Test DOC (binary Word) text extraction."""

    def _make_doc(self, path, text):
        """Create a minimal DOC file using olefile.

        Real DOC files are complex OLE2 compound documents. For testing,
        we create a DOCX and verify the extractor handles DOC extension.
        For integration testing with real DOC files, use actual samples.
        """
        # We can't easily create real DOC files programmatically,
        # so we test that the extractor is registered and handles errors
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write a minimal binary file (not a real DOC — tests error handling)
        path.write_bytes(b"\x00" * 100)
        return path

    def test_doc_extension_registered(self):
        exts = get_supported_extensions()
        assert ".doc" in exts

    def test_extract_invalid_doc_returns_empty(self, tmp_path):
        """Invalid DOC file should return empty text, not crash."""
        path = tmp_path / "bad.doc"
        path.write_bytes(b"\x00" * 100)
        text, metadata = extract_file(path)
        assert metadata["format"] == "doc"
        assert isinstance(text, str)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_extract.py::TestDocExtractor -v`
Expected: FAIL — `.doc` not registered

- [ ] **Step 3: Implement DOC extractor**

Add to `scripts/core/extract.py`:

```python
@register(".doc")
def extract_doc(path):
    """Extract text from a DOC (binary Word) file using olefile.

    DOC files store text in the WordDocument stream as a sequence of
    bytes. This extracts readable ASCII/UTF-8 text. Complex formatting
    and embedded objects are skipped.
    """
    import olefile

    text = ""
    try:
        if not olefile.isOleFile(str(path)):
            return "", {"word_count": 0, "format": "doc"}

        ole = olefile.OleFileIO(str(path))
        # The main text is in the 'WordDocument' stream
        if ole.exists("WordDocument"):
            data = ole.openstream("WordDocument").read()
            # Extract printable text (basic approach)
            text = data.decode("latin-1", errors="replace")
            # Filter to printable characters and normalize whitespace
            text = "".join(c if c.isprintable() or c in "\n\r\t" else " " for c in text)
            # Collapse multiple spaces/newlines
            lines = [line.strip() for line in text.split("\n") if line.strip()]
            text = "\n\n".join(lines)
        ole.close()
    except Exception:
        text = ""

    word_count = len(text.split()) if text else 0
    return text, {"word_count": word_count, "format": "doc"}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_extract.py::TestDocExtractor -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/core/extract.py tests/test_extract.py
git commit -m "feat: add DOC (binary Word) extractor using olefile

- Parses OLE2 compound document format
- Extracts printable text from WordDocument stream
- Gracefully handles invalid/corrupt DOC files"
```

---

### Task 4: XLSX extractor

**Files:**
- Modify: `scripts/core/extract.py`
- Modify: `tests/test_extract.py`

- [ ] **Step 1: Write failing tests for XLSX extraction**

Add to `tests/test_extract.py`:

```python
class TestXlsxExtractor:
    """Test XLSX text extraction."""

    def _make_xlsx(self, path, sheets):
        """Create a test XLSX file.

        Args:
            path: Output path.
            sheets: Dict of {sheet_name: [[row1_values], [row2_values], ...]}
        """
        from openpyxl import Workbook
        wb = Workbook()
        first = True
        for name, rows in sheets.items():
            if first:
                ws = wb.active
                ws.title = name
                first = False
            else:
                ws = wb.create_sheet(name)
            for row in rows:
                ws.append(row)
        path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(str(path))
        return path

    def test_extract_xlsx_text(self, tmp_path):
        path = self._make_xlsx(tmp_path / "data.xlsx", {
            "People": [["Name", "Age"], ["Alice", 30], ["Bob", 25]]
        })
        text, metadata = extract_file(path)
        assert "Alice" in text
        assert "Bob" in text
        assert "30" in text

    def test_extract_xlsx_metadata(self, tmp_path):
        path = self._make_xlsx(tmp_path / "data.xlsx", {
            "Sheet1": [["A", "B"], ["C", "D"]]
        })
        text, metadata = extract_file(path)
        assert metadata["format"] == "xlsx"
        assert metadata["sheet_count"] == 1
        assert metadata["word_count"] > 0

    def test_extract_xlsx_multiple_sheets(self, tmp_path):
        path = self._make_xlsx(tmp_path / "multi.xlsx", {
            "People": [["Name"], ["Alice"]],
            "Places": [["City"], ["Springfield"]],
        })
        text, metadata = extract_file(path)
        assert "Alice" in text
        assert "Springfield" in text
        assert metadata["sheet_count"] == 2
        # Sheet names should appear as headers
        assert "People" in text
        assert "Places" in text

    def test_extract_xlsx_empty_cells_skipped(self, tmp_path):
        path = self._make_xlsx(tmp_path / "sparse.xlsx", {
            "Sheet1": [["A", None, "B"], [None, None, None], ["C", "D", None]]
        })
        text, metadata = extract_file(path)
        assert "A" in text
        assert "B" in text
        assert "C" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_extract.py::TestXlsxExtractor -v`
Expected: FAIL — `.xlsx` not registered

- [ ] **Step 3: Implement XLSX extractor**

Add to `scripts/core/extract.py`:

```python
@register(".xlsx")
def extract_xlsx(path):
    """Extract text from an XLSX file using openpyxl."""
    from openpyxl import load_workbook

    wb = load_workbook(str(path), read_only=True, data_only=True)
    parts = []
    sheet_count = len(wb.sheetnames)

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        if sheet_count > 1:
            parts.append(f"## Sheet: {sheet_name}")

        for row in ws.iter_rows(values_only=True):
            cells = [str(c) for c in row if c is not None]
            if cells:
                parts.append("\t".join(cells))

    wb.close()
    text = "\n\n".join(parts)
    word_count = len(text.split())
    return text, {"word_count": word_count, "format": "xlsx", "sheet_count": sheet_count}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_extract.py::TestXlsxExtractor -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/core/extract.py tests/test_extract.py
git commit -m "feat: add XLSX extractor using openpyxl

- Reads all sheets with cell values
- Sheet names as section headers for multi-sheet files
- Skips empty cells, tab-separated values per row"
```

---

### Task 5: XLS extractor

**Files:**
- Modify: `scripts/core/extract.py`
- Modify: `tests/test_extract.py`

- [ ] **Step 1: Write failing tests for XLS extraction**

Add to `tests/test_extract.py`:

```python
class TestXlsExtractor:
    """Test XLS (legacy binary) text extraction."""

    def _make_xls(self, path, sheets):
        """Create a test XLS file using xlrd's companion xlwt."""
        import xlwt
        wb = xlwt.Workbook()
        for name, rows in sheets.items():
            ws = wb.add_sheet(name)
            for r, row in enumerate(rows):
                for c, val in enumerate(row):
                    if val is not None:
                        ws.write(r, c, val)
        path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(str(path))
        return path

    def test_xls_extension_registered(self):
        exts = get_supported_extensions()
        assert ".xls" in exts

    def test_extract_xls_text(self, tmp_path):
        try:
            import xlwt
        except ImportError:
            pytest.skip("xlwt not installed")
        path = self._make_xls(tmp_path / "data.xls", {
            "People": [["Name", "Age"], ["Alice", 30]]
        })
        text, metadata = extract_file(path)
        assert "Alice" in text
        assert metadata["format"] == "xls"
        assert metadata["sheet_count"] == 1

    def test_extract_xls_multiple_sheets(self, tmp_path):
        try:
            import xlwt
        except ImportError:
            pytest.skip("xlwt not installed")
        path = self._make_xls(tmp_path / "multi.xls", {
            "Names": [["Alice"]],
            "Cities": [["Springfield"]],
        })
        text, metadata = extract_file(path)
        assert "Alice" in text
        assert "Springfield" in text
        assert metadata["sheet_count"] == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_extract.py::TestXlsExtractor -v`
Expected: FAIL — `.xls` not registered

- [ ] **Step 3: Implement XLS extractor**

Add to `scripts/core/extract.py`:

```python
@register(".xls")
def extract_xls(path):
    """Extract text from an XLS (legacy binary) file using xlrd."""
    import xlrd

    wb = xlrd.open_workbook(str(path))
    parts = []
    sheet_count = wb.nsheets

    for sheet_idx in range(sheet_count):
        ws = wb.sheet_by_index(sheet_idx)
        if sheet_count > 1:
            parts.append(f"## Sheet: {ws.name}")

        for row_idx in range(ws.nrows):
            cells = []
            for col_idx in range(ws.ncols):
                val = ws.cell_value(row_idx, col_idx)
                if val != "":
                    # xlrd returns floats for numbers — format cleanly
                    if isinstance(val, float) and val == int(val):
                        cells.append(str(int(val)))
                    else:
                        cells.append(str(val))
            if cells:
                parts.append("\t".join(cells))

    text = "\n\n".join(parts)
    word_count = len(text.split())
    return text, {"word_count": word_count, "format": "xls", "sheet_count": sheet_count}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_extract.py::TestXlsExtractor -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/core/extract.py tests/test_extract.py
git commit -m "feat: add XLS (legacy binary) extractor using xlrd

- Reads all sheets with cell values
- Same output format as XLSX extractor (sheet headers, tab-separated)
- Handles float-to-int conversion for clean number display"
```

---

### Task 6: Pipeline script and CLI command

**Files:**
- Create: `scripts/extract_docs.py`
- Modify: `scripts/cli.py`
- Modify: `tests/test_extract.py`

- [ ] **Step 1: Write failing test for pipeline**

Add to `tests/test_extract.py`:

```python
class TestExtractPipeline:
    """Test the extract_docs pipeline."""

    def test_extract_creates_transcripts(self, tmp_path):
        from scripts.extract_docs import run_extraction
        from docx import Document

        dest = tmp_path / "archive"
        dest.mkdir()

        # Create a DOCX file
        doc = Document()
        doc.add_paragraph("Hello from the test document.")
        docx_path = dest / "NeedsReview" / "letter.docx"
        docx_path.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(docx_path))

        results = run_extraction(dest, folder="NeedsReview")

        assert len(results) == 1
        assert results[0]["status"] == "ok"
        transcript = docx_path.with_suffix(".transcript.md")
        assert transcript.exists()
        content = transcript.read_text(encoding="utf-8")
        assert "Hello from the test document" in content

    def test_extract_skips_existing_transcripts(self, tmp_path):
        from scripts.extract_docs import run_extraction
        from docx import Document

        dest = tmp_path / "archive"
        dest.mkdir()

        doc = Document()
        doc.add_paragraph("Content")
        docx_path = dest / "letter.docx"
        doc.save(str(docx_path))

        # Pre-create transcript
        docx_path.with_suffix(".transcript.md").write_text("existing", encoding="utf-8")

        results = run_extraction(dest)
        assert len(results) == 0  # skipped because transcript exists

    def test_extract_force_overwrites(self, tmp_path):
        from scripts.extract_docs import run_extraction
        from docx import Document

        dest = tmp_path / "archive"
        dest.mkdir()

        doc = Document()
        doc.add_paragraph("New content")
        docx_path = dest / "letter.docx"
        doc.save(str(docx_path))

        docx_path.with_suffix(".transcript.md").write_text("old", encoding="utf-8")

        results = run_extraction(dest, force=True)
        assert len(results) == 1
        content = docx_path.with_suffix(".transcript.md").read_text(encoding="utf-8")
        assert "New content" in content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_extract.py::TestExtractPipeline -v`
Expected: FAIL — `scripts.extract_docs` doesn't exist

- [ ] **Step 3: Implement extract_docs.py**

Create `scripts/extract_docs.py`:

```python
#!/usr/bin/env python3
"""
Document Text Extraction — Extract text from Office documents.

Walks the archive, finds supported document files (DOC, DOCX, XLS, XLSX),
extracts text, and creates companion .transcript.md files.

Usage:
    python extract_docs.py                          # all folders
    python extract_docs.py --folder NeedsReview     # one folder
    python extract_docs.py --file path/to/doc.docx  # single file
    python extract_docs.py --dry-run                # preview only
    python extract_docs.py --force                  # overwrite existing
"""

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import load_config
from core.extract import extract_file, get_supported_extensions, create_extract_transcript


def collect_files(dest_root, folder=None, target_file=None):
    """Collect extractable files from the archive."""
    supported = get_supported_extensions()

    if target_file:
        p = Path(target_file)
        if not p.is_absolute():
            p = dest_root / p
        if p.exists() and p.suffix.lower() in supported:
            return [p]
        return []

    skip_dirs = {".organizer", ".trashbox", "__pycache__", "_historytools_temp", "_duplicates", "_compilations"}
    files = []

    for dirpath, dirnames, filenames in Path(dest_root).walk():
        dirnames[:] = [d for d in dirnames if d not in skip_dirs and not d.startswith(".")]

        if folder:
            try:
                rel = dirpath.relative_to(dest_root)
                if not str(rel).replace("\\", "/").startswith(folder):
                    continue
            except ValueError:
                continue

        for fname in sorted(filenames):
            if fname.startswith("."):
                continue
            fpath = dirpath / fname
            if fpath.suffix.lower() in supported:
                files.append(fpath)

    return files


def run_extraction(dest_root, folder=None, target_file=None, force=False, dry_run=False):
    """Run extraction on all supported files.

    Args:
        dest_root: Archive root directory.
        folder: Optional folder filter.
        target_file: Optional single file path.
        force: Overwrite existing transcripts.
        dry_run: Preview without extracting.

    Returns:
        List of result dicts.
    """
    dest_root = Path(dest_root)
    files = collect_files(dest_root, folder, target_file)

    # Filter to files without existing transcripts (unless --force)
    if not force:
        filtered = []
        for f in files:
            md = f.with_suffix(".transcript.md")
            if not md.exists():
                filtered.append(f)
        skipped = len(files) - len(filtered)
        files = filtered
        if skipped:
            print(f"Skipping {skipped} files with existing transcripts (use --force to overwrite)")

    if not files:
        print("No files found to extract.")
        return []

    print(f"Found {len(files)} files to extract")

    if dry_run:
        print("\n--- DRY RUN (no files created) ---")
        for f in files:
            rel = f.relative_to(dest_root) if f.is_relative_to(dest_root) else f
            existing = f.with_suffix(".transcript.md").exists()
            status = "EXISTS (will overwrite)" if existing else "new"
            print(f"  {rel} [{status}]")
        return []

    results = []
    for i, fpath in enumerate(files, 1):
        rel = fpath.relative_to(dest_root) if fpath.is_relative_to(dest_root) else fpath
        try:
            text, metadata = extract_file(fpath)
            md_path = create_extract_transcript(fpath, text, metadata, dest_root)
            word_count = metadata.get("word_count", 0)
            print(f"  [{i}/{len(files)}] {rel}: {word_count} words ({metadata['format']})")
            results.append({
                "file": str(rel),
                "words": word_count,
                "format": metadata["format"],
                "status": "ok",
            })
        except Exception as e:
            print(f"  [{i}/{len(files)}] {rel}: ERROR — {e}")
            results.append({
                "file": str(rel),
                "status": "error",
                "error": str(e),
            })

    ok = sum(1 for r in results if r["status"] == "ok")
    err = sum(1 for r in results if r["status"] == "error")
    total_words = sum(r.get("words", 0) for r in results)
    print(f"\nComplete: {ok} extracted, {err} errors, {total_words:,} words total")

    return results


def main():
    parser = argparse.ArgumentParser(description="Extract text from Office documents")
    parser.add_argument("--config", default=None, help="Path to config.json")
    parser.add_argument("--folder", default=None, help="Only extract from this subfolder")
    parser.add_argument("--file", default=None, help="Extract a single file")
    parser.add_argument("--force", action="store_true", help="Overwrite existing transcripts")
    parser.add_argument("--dry-run", action="store_true", help="Preview without extracting")
    args = parser.parse_args()

    config = load_config(args.config)
    dest_root = config["dest_root"]

    run_extraction(dest_root, folder=args.folder, target_file=args.file,
                   force=args.force, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Add CLI command**

In `scripts/cli.py`, add the command function (after `cmd_photos`):

```python
def cmd_extract(args):
    """Extract text from Office documents (DOC, DOCX, XLS, XLSX)."""
    sys.argv = ['extract_docs'] + args
    from .extract_docs import main
    main()
```

Add the subparser entry (after the `photos` line):

```python
    subparsers.add_parser('extract', help='Extract text from Office documents (DOC, DOCX, XLS, XLSX)')
```

Add to the dispatch dict:

```python
        'extract': cmd_extract,
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_extract.py -v`
Expected: All PASS

Run: `python -m pytest --tb=short`
Expected: Full suite PASS

- [ ] **Step 6: Commit**

```bash
git add scripts/extract_docs.py scripts/cli.py tests/test_extract.py
git commit -m "feat: add document extraction pipeline and CLI command

- family-archive extract walks archive, extracts supported Office files
- Supports --folder, --file, --force, --dry-run flags
- Writes .transcript.md files using same format as PDF transcripts
- Integrates with existing search, duplicates, and indexing pipeline"
```

---

### Task 7: Update docs and add CI dependency

**Files:**
- Modify: `docs/WORKFLOW.md`
- Modify: `.github/workflows/tests.yml`

- [ ] **Step 1: Update WORKFLOW.md**

Find the "2. Transcribe PDFs" section in `docs/WORKFLOW.md`. Add a new step before it (making it step 2, and bumping Transcribe PDFs to step 3):

```markdown
### 2. Extract Office Documents

```bash
# Extract text from DOC, DOCX, XLS, XLSX files
family-archive extract                              # all supported files
family-archive extract --folder NeedsReview          # limit to folder
family-archive extract --file path/to/doc.docx       # single file
family-archive extract --dry-run                     # preview only
family-archive extract --force                       # overwrite existing transcripts
```

Creates `.transcript.md` files from Office documents using local text extraction
(no API calls, instant results). Supports DOC, DOCX, XLS, XLSX formats.
```

- [ ] **Step 2: Add dependencies to CI**

In `.github/workflows/tests.yml`, update the pip install line to include the new libraries:

```yaml
          pip install pytest PyMuPDF Pillow python-dotenv imagehash python-docx openpyxl xlrd olefile xlwt
```

Note: `xlwt` is added for tests only (creating test XLS files).

- [ ] **Step 3: Run full test suite**

Run: `python -m pytest --tb=short`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add docs/WORKFLOW.md .github/workflows/tests.yml
git commit -m "docs: add Office document extraction to workflow and CI

- New step 2 in workflow: family-archive extract for Office documents
- Add python-docx, openpyxl, xlrd, olefile, xlwt to CI dependencies"
```
