#!/usr/bin/env python3
"""
AI-Powered File Rename Proposals (Phase 1)
- Scans folders for files with generic names (unknown, numeric, etc.)
- Reads existing transcripts or uses Gemini vision to understand content
- Proposes descriptive filenames following folder-specific conventions
- Outputs _rename-proposals.json and _rename-proposals.md for review

Usage:
    python propose_renames.py                          # all configured folders
    python propose_renames.py --folder FamilyMembers   # one folder only
    python propose_renames.py --dry-run                # list files, no API calls
    python propose_renames.py --model gemini-2.5-pro   # override model
"""

import os
import re
import sys
import json
import time
import argparse
from pathlib import Path
from datetime import datetime

import fitz  # PyMuPDF

sys.path.insert(0, str(Path(__file__).parent))
from config import load_config, load_env

TODAY = datetime.now().strftime("%Y-%m-%d")
DEFAULT_MODEL = "gemini-2.5-flash"
REQUESTS_PER_MINUTE = 200  # paid tier allows 2000 RPM; 200 is conservative

# Folders to scan for generic names (Photos excluded by design)
RENAME_FOLDERS = [
    "FamilyMembers",
    "Recipes",
    "Medical",
    "Financial",
    "Documents/Church",
    "Documents/Writings",
    "Documents/Misc",
]

# Per-folder naming conventions for the AI prompt
FOLDER_CONVENTIONS = {
    "FamilyMembers": {
        "pattern": "{person}-{doctype}-{topic}",
        "description": "Start with the person's first name, then document type and topic.",
        "examples": [
            "joshua-eagle-scout-certificate",
            "leah-school-attendance-report",
            "richard-efy-grant-proposal",
            "jenna-strength-of-youth-award",
        ],
    },
    "Recipes": {
        "pattern": "recipe-{dish}",
        "description": "Start with 'recipe-' followed by the dish name.",
        "examples": [
            "recipe-banana-bread",
            "recipe-christmas-fudge",
            "recipe-slow-cooker-chili",
            "recipe-grandma-rose-rolls",
        ],
    },
    "Medical": {
        "pattern": "{doctype}-{person}-{topic}",
        "description": "Start with document type (dental, insurance, prescription, lab-result, etc.), then person and topic.",
        "examples": [
            "dental-xray-alice",
            "insurance-claim-bob",
            "prescription-alice-thyroid",
            "lab-results-bob-blood-panel",
        ],
    },
    "Financial": {
        "pattern": "{doctype}-{institution}-{topic}",
        "description": "Start with document type (statement, check, invoice, tax-return, receipt, etc.), then institution and topic.",
        "examples": [
            "statement-merrill-lynch-q1",
            "tax-return-2018-federal",
            "check-22305-merrill-lynch",
            "invoice-cary-utilities-water",
            "receipt-autopark-honda-service",
        ],
    },
    "Documents/Church": {
        "pattern": "{doctype}-{topic}",
        "description": "Start with document type (certificate, food-order, reimbursement, program, etc.), then topic.",
        "examples": [
            "duty-to-god-certificate",
            "food-order-cary-ward-jan",
            "reimbursement-form-stake",
            "tithing-settlement-2015",
        ],
    },
    "Documents/Writings": {
        "pattern": "{doctype}-{person}-{topic}",
        "description": "Start with document type (homework, essay, report, notes), then person and topic.",
        "examples": [
            "homework-alice-ece106-design-project",
            "essay-bob-alex-haley",
            "book-report-alice-day-after-tomorrow",
        ],
    },
    "Documents/Misc": {
        "pattern": "{doctype}-{topic}",
        "description": "Start with document type, then topic. Be descriptive.",
        "examples": [
            "flyer-neighborhood-block-party",
            "warranty-samsung-dishwasher",
            "manual-scanner-ix1500",
        ],
    },
}


def is_generic_name(filename):
    """Check if a filename has a generic/unhelpful slug."""
    stem = Path(filename).stem

    # Extract the slug (part after date prefix)
    # Patterns: YYYY-MM-DD_slug or undated_slug
    match = re.match(r"^(?:\d{4}-\d{2}-\d{2}|undated)_(.+)$", stem)
    if not match:
        # No standard prefix — check the whole stem
        slug = stem
    else:
        slug = match.group(1)

    # Generic if contains "unknown"
    if "unknown" in slug.lower():
        return True

    # Generic if purely numeric
    if re.match(r"^\d+$", slug):
        return True

    # Generic if scanner timestamp pattern (digits and underscores)
    if re.match(r"^[\d_]+$", slug):
        return True

    # Generic if very short (less than 4 chars)
    if len(slug) < 4:
        return True

    return False


def get_date_prefix(filename):
    """Extract the date prefix from a filename."""
    stem = Path(filename).stem
    match = re.match(r"^(\d{4}-\d{2}-\d{2}|undated)_", stem)
    if match:
        return match.group(1)
    return None


def get_folder_convention(file_path, dest_root):
    """Get the naming convention for a file's folder."""
    try:
        rel = file_path.relative_to(dest_root)
        rel_str = str(rel).replace("\\", "/")
    except ValueError:
        return FOLDER_CONVENTIONS.get("Documents/Misc", FOLDER_CONVENTIONS["Documents/Misc"])

    for folder_key in FOLDER_CONVENTIONS:
        if rel_str.startswith(folder_key):
            return FOLDER_CONVENTIONS[folder_key]

    # Default fallback
    return FOLDER_CONVENTIONS["Documents/Misc"]


def read_transcript(file_path):
    """Read companion .transcript.md and return (text, confidence)."""
    md_path = file_path.with_suffix(".transcript.md")
    if not md_path.exists():
        return None, None

    content = md_path.read_text(encoding="utf-8", errors="replace")

    # Extract confidence from frontmatter
    confidence = "unknown"
    conf_match = re.search(r"transcription_confidence:\s*(\w+)", content)
    if conf_match:
        confidence = conf_match.group(1)

    # Extract body text (after the closing ---)
    parts = content.split("---", 2)
    if len(parts) >= 3:
        body = parts[2].strip()
    else:
        body = content

    return body, confidence


def build_text_prompt(transcript_text, folder_key, convention, is_undated=False):
    """Build a Gemini prompt for transcript-based naming."""
    examples_str = "\n".join(f"  - {e}" for e in convention["examples"])

    date_instruction = ""
    if is_undated:
        date_instruction = """
- IMPORTANT: This file is currently undated. If you can determine a date or approximate date
  from the content (letter dates, journal entries, references to specific events/years),
  include a "date" field in your response with format "YYYY-MM-DD" (use 00 for unknown month/day).
  If you cannot determine any date, omit the "date" field."""

    return f"""You are naming files in a family archive. Given the transcript text of a document
and its folder location, propose a short descriptive filename slug.

Folder: {folder_key}
Naming convention: {convention['pattern']}
Description: {convention['description']}
Examples of good names in this folder:
{examples_str}

Transcript (first 2000 characters):
{transcript_text[:2000]}

Rules:
- Output ONLY valid JSON
- The slug must use lowercase-kebab-case
- Keep under 8 words
- Include people's first names when the document is about or from a specific person
- Be specific: "joshua-eagle-scout-certificate" not "certificate"
- Do not invent information not present in the transcript
- Do not include dates in the slug (the date prefix is added separately)
- Do not include the file extension
{date_instruction}

Respond with JSON only: {{"slug": "proposed-slug", "reasoning": "one sentence explanation"}}"""


def build_vision_prompt(folder_key, convention, is_undated=False):
    """Build a Gemini prompt for vision-based naming."""
    examples_str = "\n".join(f"  - {e}" for e in convention["examples"])

    date_instruction = ""
    if is_undated:
        date_instruction = """
- IMPORTANT: This file is currently undated. If you can see a date on the document,
  include a "date" field in your response with format "YYYY-MM-DD" (use 00 for unknown month/day).
  If no date is visible, omit the "date" field."""

    return f"""You are naming files in a family archive. Look at this scanned document
and determine what it is, then propose a short descriptive filename slug.

Folder: {folder_key}
Naming convention: {convention['pattern']}
Description: {convention['description']}
Examples of good names in this folder:
{examples_str}

Rules:
- Output ONLY valid JSON
- The slug must use lowercase-kebab-case
- Keep under 8 words
- Include people's first names when the document is about or from a specific person
- Be specific: "joshua-eagle-scout-certificate" not "certificate"
- Do not invent information you cannot see in the document
- Do not include dates in the slug (the date prefix is added separately)
- Do not include the file extension
{date_instruction}

Respond with JSON only: {{"slug": "proposed-slug", "reasoning": "one sentence explanation"}}"""


def propose_via_transcript(client, model_name, transcript_text, folder_key, convention, is_undated=False):
    """Get a slug proposal from Gemini using transcript text."""
    prompt = build_text_prompt(transcript_text, folder_key, convention, is_undated)
    response = client.models.generate_content(model=model_name, contents=[prompt])
    return parse_gemini_response(response.text)


def propose_via_vision(client, model_name, pdf_path, folder_key, convention, is_undated=False):
    """Get a slug proposal from Gemini using the first page image."""
    from google.genai import types

    doc = fitz.open(str(pdf_path))
    page = doc[0]
    mat = fitz.Matrix(200 / 72, 200 / 72)  # 200 DPI is enough for identification
    pix = page.get_pixmap(matrix=mat)
    png_bytes = pix.tobytes("png")
    doc.close()

    prompt = build_vision_prompt(folder_key, convention, is_undated)
    image_part = types.Part.from_bytes(data=png_bytes, mime_type="image/png")

    response = client.models.generate_content(
        model=model_name,
        contents=[prompt, image_part],
    )
    return parse_gemini_response(response.text)


def parse_gemini_response(text):
    """Parse the JSON response from Gemini."""
    # Strip markdown code fences if present
    cleaned = text.strip()
    cleaned = re.sub(r"^```json\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
        slug = data.get("slug", "").strip().lower()
        # Sanitize: only allow lowercase letters, numbers, hyphens
        slug = re.sub(r"[^a-z0-9-]", "-", slug)
        slug = re.sub(r"-+", "-", slug).strip("-")
        reasoning = data.get("reasoning", "")
        detected_date = data.get("date")  # optional, for undated files
        return slug, reasoning, detected_date
    except (json.JSONDecodeError, AttributeError):
        return None, f"Failed to parse response: {text[:200]}", None


def resolve_collision(proposed_path):
    """If proposed_path already exists, append -2, -3, etc."""
    if not proposed_path.exists():
        return proposed_path

    stem = proposed_path.stem
    suffix = proposed_path.suffix
    parent = proposed_path.parent

    # Check if stem already ends with a date prefix + slug
    # We want to append to the slug, not the date
    counter = 2
    while True:
        new_name = f"{stem}-{counter}{suffix}"
        new_path = parent / new_name
        if not new_path.exists():
            return new_path
        counter += 1


def collect_generic_files(dest_root, target_folder=None):
    """Find all files with generic names in configured folders."""
    folders = [target_folder] if target_folder else RENAME_FOLDERS
    generic_files = []

    for folder in folders:
        folder_path = dest_root / folder
        if not folder_path.exists():
            continue

        for f in sorted(folder_path.rglob("*")):
            if f.is_dir():
                continue
            if f.suffix == ".md" or f.suffix == ".json":
                continue  # skip transcripts and metadata files
            if is_generic_name(f.name):
                generic_files.append(f)

    return generic_files


def get_folder_key(file_path, dest_root):
    """Get the folder convention key for a file."""
    try:
        rel = str(file_path.relative_to(dest_root)).replace("\\", "/")
    except ValueError:
        return "Documents/Misc"

    for folder_key in FOLDER_CONVENTIONS:
        if rel.startswith(folder_key):
            return folder_key
    return "Documents/Misc"


def write_proposals_md(proposals, dest_root):
    """Write a human-readable markdown table of proposals."""
    md_path = dest_root / "_rename-proposals.md"

    # Group by folder
    by_folder = {}
    for p in proposals:
        rel = p["current_path"]
        folder = rel.split("/")[0]
        by_folder.setdefault(folder, []).append(p)

    transcript_count = sum(1 for p in proposals if p["source"] == "transcript")
    vision_count = sum(1 for p in proposals if p["source"] == "vision")

    lines = [
        f"# Rename Proposals\n",
        f"Generated: {TODAY} | Files: {len(proposals)} | "
        f"Source: transcript ({transcript_count}), vision ({vision_count})\n",
        f"Edit `_rename-proposals.json` to change names or set `\"approved\": false` to skip.\n",
        f"Then run: `python Toolkit/scripts/apply_renames.py`\n",
    ]

    for folder, items in sorted(by_folder.items()):
        lines.append(f"\n## {folder} ({len(items)} files)\n")
        lines.append("| # | Current Name | Proposed Name | Source | Reasoning |")
        lines.append("|---|-------------|---------------|--------|-----------|")
        for i, item in enumerate(items, 1):
            cur = Path(item["current_name"]).name
            prop = item["proposed_name"]
            lines.append(
                f"| {i} | `{cur}` | `{prop}` | {item['source']} | {item['reasoning']} |"
            )

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path


def main():
    parser = argparse.ArgumentParser(description="Propose descriptive renames for generic filenames")
    parser.add_argument("--config", default=None, help="Path to config.json")
    parser.add_argument("--folder", default=None, help="Only scan this subfolder")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Gemini model (default: {DEFAULT_MODEL})")
    parser.add_argument("--dry-run", action="store_true", help="List files without making API calls")
    args = parser.parse_args()

    # Load environment and config
    if not args.dry_run:
        if not load_env():
            sys.exit(1)
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            print("ERROR: GEMINI_API_KEY not set in .env file.")
            print("See SETUP-API-KEYS.md for instructions.")
            sys.exit(1)

    config = load_config(args.config)
    dest_root = config["dest_root"]

    generic_files = collect_generic_files(dest_root, args.folder)

    if not generic_files:
        print("No files with generic names found.")
        return

    print(f"Found {len(generic_files)} files with generic names")

    if args.dry_run:
        print("\n--- DRY RUN (no API calls) ---")
        by_folder = {}
        for f in generic_files:
            folder_key = get_folder_key(f, dest_root)
            by_folder.setdefault(folder_key, []).append(f)

        for folder, files in sorted(by_folder.items()):
            print(f"\n  {folder}: {len(files)} files")
            for f in files[:5]:
                rel = f.relative_to(dest_root)
                transcript, conf = read_transcript(f)
                source = "transcript" if transcript and conf in ("high", "medium") else "vision"
                print(f"    {rel} [{source}]")
            if len(files) > 5:
                print(f"    ... and {len(files) - 5} more")

        transcript_count = sum(
            1 for f in generic_files
            if read_transcript(f)[1] in ("high", "medium")
        )
        vision_count = len(generic_files) - transcript_count
        est_cost = vision_count * 0.0003 + transcript_count * 0.00005
        print(f"\nSources: {transcript_count} transcript, {vision_count} vision")
        print(f"Estimated cost: ${est_cost:.2f}")
        return

    # Initialize Gemini client
    from google import genai
    client = genai.Client(api_key=api_key)

    # Load existing proposals for incremental resume
    json_path = dest_root / "_rename-proposals.json"
    proposals = []
    already_proposed = set()
    if json_path.exists():
        try:
            with open(json_path, "r", encoding="utf-8") as jf:
                proposals = json.load(jf)
            already_proposed = {p["current_path"] for p in proposals}
            if already_proposed:
                print(f"Loaded {len(proposals)} existing proposals — skipping already-proposed files")
        except (json.JSONDecodeError, IOError):
            proposals = []

    # Filter out already-proposed files
    generic_files = [
        f for f in generic_files
        if str(f.relative_to(dest_root)).replace("\\", "/") not in already_proposed
    ]

    if not generic_files:
        print("All generic files already have proposals.")
        md_path = write_proposals_md(proposals, dest_root)
        print(f"Review table saved to {md_path}")
        return

    print(f"{len(generic_files)} files remaining to propose")

    request_times = []
    max_retries = 3

    for i, f in enumerate(generic_files, 1):
        rel = f.relative_to(dest_root)
        folder_key = get_folder_key(f, dest_root)
        convention = FOLDER_CONVENTIONS.get(folder_key, FOLDER_CONVENTIONS["Documents/Misc"])
        date_prefix = get_date_prefix(f.name)

        print(f"[{i}/{len(generic_files)}] {rel}")

        # Rate limiting
        now = time.time()
        request_times = [t for t in request_times if now - t < 60]
        if len(request_times) >= REQUESTS_PER_MINUTE:
            wait = 60 - (now - request_times[0]) + 0.5
            print(f"  Rate limit: waiting {wait:.0f}s...")
            time.sleep(wait)

        try:
            transcript_text, confidence = read_transcript(f)
            source = "transcript"
            slug = None
            reasoning = ""
            detected_date = None
            is_undated = date_prefix == "undated"

            for attempt in range(max_retries + 1):
                try:
                    if transcript_text and confidence in ("high", "medium"):
                        slug, reasoning, detected_date = propose_via_transcript(
                            client, args.model, transcript_text, folder_key, convention, is_undated
                        )
                    else:
                        source = "vision"
                        if f.suffix.lower() == ".pdf":
                            slug, reasoning, detected_date = propose_via_vision(
                                client, args.model, f, folder_key, convention, is_undated
                            )
                        elif f.suffix.lower() in (".jpg", ".jpeg", ".png", ".tiff", ".bmp"):
                            from google.genai import types
                            img_bytes = f.read_bytes()
                            mime = {
                                ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                                ".png": "image/png", ".tiff": "image/tiff",
                                ".bmp": "image/bmp",
                            }.get(f.suffix.lower(), "image/jpeg")
                            prompt = build_vision_prompt(folder_key, convention, is_undated)
                            image_part = types.Part.from_bytes(data=img_bytes, mime_type=mime)
                            response = client.models.generate_content(
                                model=args.model, contents=[prompt, image_part]
                            )
                            slug, reasoning, detected_date = parse_gemini_response(response.text)
                        else:
                            slug, reasoning, detected_date = None, f"Unsupported file type: {f.suffix}", None
                    break  # success
                except Exception as retry_err:
                    err_str = str(retry_err)
                    is_retryable = any(str(code) in err_str for code in {429, 500, 502, 503, 504})
                    if is_retryable and attempt < max_retries:
                        wait = 2 ** attempt * 5
                        print(f"  Retry {attempt + 1}/{max_retries} after {wait}s...")
                        time.sleep(wait)
                        continue
                    raise

            request_times.append(time.time())

            if not slug:
                print(f"  SKIP: {reasoning}")
                continue

            # Determine date prefix and target folder
            ext = f.suffix
            new_date_prefix = date_prefix

            # If file was undated and AI detected a date, use it
            if is_undated and detected_date and re.match(r"\d{4}-\d{2}-\d{2}", detected_date):
                new_date_prefix = detected_date

            if new_date_prefix and new_date_prefix != "undated":
                proposed_name = f"{new_date_prefix}_{slug}{ext}"
            elif new_date_prefix == "undated":
                proposed_name = f"undated_{slug}{ext}"
            else:
                proposed_name = f"{slug}{ext}"

            # Determine target folder — move from Undated to year folder if date detected
            target_parent = f.parent
            if is_undated and new_date_prefix != "undated" and "Undated" in str(f.parent):
                year = new_date_prefix[:4]
                # Replace "Undated" with the year in the path
                target_parent = Path(str(f.parent).replace("Undated", year))

            proposed_path = target_parent / proposed_name

            # Check for collisions
            if proposed_path.exists() and proposed_path != f:
                proposed_path = resolve_collision(proposed_path)
                proposed_name = proposed_path.name

            proposal = {
                "current_path": str(rel).replace("\\", "/"),
                "current_name": f.name,
                "proposed_slug": slug,
                "proposed_name": proposed_name,
                "proposed_path": str(proposed_path.relative_to(dest_root)).replace("\\", "/"),
                "source": source,
                "confidence": confidence or "vision",
                "reasoning": reasoning,
                "approved": True,
            }

            # Add date detection info if applicable
            if is_undated and detected_date:
                proposal["detected_date"] = detected_date
            if str(target_parent) != str(f.parent):
                proposal["folder_move"] = True

            proposals.append(proposal)

            # Save incrementally after each proposal
            with open(json_path, "w", encoding="utf-8") as jf:
                json.dump(proposals, jf, indent=2, ensure_ascii=False)

            move_note = " [MOVE]" if str(target_parent) != str(f.parent) else ""
            print(f"  -> {proposed_name}{move_note} ({source}: {reasoning})")

        except Exception as e:
            print(f"  ERROR: {e}")

    # Write final proposals
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(proposals, f, indent=2, ensure_ascii=False)
    print(f"\nProposals saved to {json_path}")

    md_path = write_proposals_md(proposals, dest_root)
    print(f"Review table saved to {md_path}")

    print(f"\n{'=' * 60}")
    print(f"Generated {len(proposals)} rename proposals")
    print(f"Next steps:")
    print(f"  1. Review _rename-proposals.md (or edit _rename-proposals.json)")
    print(f"  2. Set \"approved\": false for any you want to skip")
    print(f"  3. Run: python Toolkit/scripts/apply_renames.py")


if __name__ == "__main__":
    main()
