#!/usr/bin/env python3
"""
Speaker Label Utility
Assign real names to speaker labels (Speaker A, Speaker B, etc.)
in AssemblyAI-generated transcript files.

Usage:
    # Interactive mode — shows samples from each speaker, prompts for names:
    python label_speakers.py path/to/file.transcript.md

    # Batch mode — apply a mapping to all transcripts in a directory:
    python label_speakers.py --dir AudioRecordings --map "A=Alice,B=Bob"

    # Preview changes without writing:
    python label_speakers.py --dir AudioRecordings --map "A=Alice,B=Bob" --dry-run

    # Undo — revert names back to Speaker A, Speaker B, etc.:
    python label_speakers.py --dir AudioRecordings --unmap "Alice=A,Bob=B"
"""

import re
import sys
import argparse
from pathlib import Path


def find_transcripts(directory):
    """Find all .transcript.md files in a directory tree."""
    return sorted(Path(directory).rglob("*.transcript.md"))


def parse_speaker_map(map_str):
    """Parse 'A=Alice,B=Bob' into {'A': 'Alice', 'B': 'Bob'}."""
    mapping = {}
    for pair in map_str.split(","):
        pair = pair.strip()
        if "=" not in pair:
            print(f"WARNING: Skipping invalid mapping '{pair}' (expected format: A=Name)")
            continue
        key, val = pair.split("=", 1)
        mapping[key.strip()] = val.strip()
    return mapping


def get_speaker_samples(content):
    """Extract short sample quotes from each speaker."""
    speakers = {}
    for match in re.finditer(
        r"\*\*Speaker ([A-Z])\*\* \(([^)]+)\): (.+?)(?=\n\n\*\*Speaker|\Z)",
        content,
        re.DOTALL,
    ):
        speaker = match.group(1)
        timestamp = match.group(2)
        text = match.group(3).strip()
        if speaker not in speakers:
            speakers[speaker] = []
        if len(speakers[speaker]) < 3:  # keep up to 3 samples per speaker
            preview = text[:150] + "..." if len(text) > 150 else text
            speakers[speaker].append(f"  ({timestamp}): {preview}")
    return speakers


def apply_mapping(content, mapping):
    """Replace Speaker X with real names in transcript content.
    Uses regex to only match speaker labels in bold at the start of utterance blocks,
    not arbitrary text content."""
    modified = content
    for letter, name in mapping.items():
        # Replace bold speaker labels at start of utterance blocks
        modified = re.sub(
            rf"\*\*Speaker {re.escape(letter)}\*\*( \()",
            rf"**{name}**\1",
            modified,
        )
        # Update YAML frontmatter speaker assignments
        modified = re.sub(
            rf"^(  {re.escape(letter)}:) unknown$",
            rf"\1 {name}",
            modified,
            flags=re.MULTILINE,
        )
    return modified


def apply_unmapping(content, unmap):
    """Revert real names back to Speaker X labels.
    Uses regex to only match named labels in bold at the start of utterance blocks."""
    modified = content
    for name, letter in unmap.items():
        # Revert bold named labels back to Speaker X
        modified = re.sub(
            rf"\*\*{re.escape(name)}\*\*( \()",
            rf"**Speaker {letter}**\1",
            modified,
        )
        # Revert YAML frontmatter
        modified = re.sub(
            rf"^(  {re.escape(letter)}:) {re.escape(name)}$",
            rf"\1 unknown",
            modified,
            flags=re.MULTILINE,
        )
    return modified


def interactive_label(filepath):
    """Interactive mode: show speaker samples and prompt for names."""
    content = filepath.read_text(encoding="utf-8")
    speakers = get_speaker_samples(content)

    if not speakers:
        print(f"No speaker labels found in {filepath}")
        return

    print(f"\nFile: {filepath.name}")
    print(f"Found {len(speakers)} speaker(s)\n")

    mapping = {}
    for speaker, samples in sorted(speakers.items()):
        print(f"--- Speaker {speaker} ---")
        for sample in samples:
            print(sample)
        name = input(f"\nName for Speaker {speaker} (Enter to skip): ").strip()
        if name:
            mapping[speaker] = name
        print()

    if not mapping:
        print("No changes made.")
        return

    modified = apply_mapping(content, mapping)
    filepath.write_text(modified, encoding="utf-8")
    assignments = ", ".join(f"{k} -> {v}" for k, v in mapping.items())
    print(f"Updated: {assignments}")


def batch_label(directory, mapping, dry_run=False):
    """Batch mode: apply mapping to all transcripts in a directory."""
    transcripts = find_transcripts(directory)
    if not transcripts:
        print(f"No .transcript.md files found in {directory}")
        return

    changed = 0
    for t in transcripts:
        content = t.read_text(encoding="utf-8")
        # Only process files that have speaker labels
        if "**Speaker " not in content:
            continue

        modified = apply_mapping(content, mapping)
        if modified != content:
            if dry_run:
                print(f"  [would update] {t.name}")
            else:
                t.write_text(modified, encoding="utf-8")
                print(f"  [updated] {t.name}")
            changed += 1

    action = "Would update" if dry_run else "Updated"
    print(f"\n{action} {changed} file(s)")


def batch_unlabel(directory, unmap, dry_run=False):
    """Undo mode: revert names back to Speaker labels."""
    transcripts = find_transcripts(directory)
    changed = 0
    for t in transcripts:
        content = t.read_text(encoding="utf-8")
        modified = apply_unmapping(content, unmap)
        if modified != content:
            if dry_run:
                print(f"  [would revert] {t.name}")
            else:
                t.write_text(modified, encoding="utf-8")
                print(f"  [reverted] {t.name}")
            changed += 1

    action = "Would revert" if dry_run else "Reverted"
    print(f"\n{action} {changed} file(s)")


def main():
    parser = argparse.ArgumentParser(
        description="Assign real names to speaker labels in transcripts"
    )
    parser.add_argument("file", nargs="?", help="Single transcript file (interactive mode)")
    parser.add_argument("--dir", default=None, help="Directory of transcripts (batch mode)")
    parser.add_argument(
        "--map", default=None,
        help='Speaker mapping, e.g. "A=Alice,B=Bob"',
    )
    parser.add_argument(
        "--unmap", default=None,
        help='Undo mapping, e.g. "Alice=A,Bob=B"',
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    args = parser.parse_args()

    if args.file and not args.dir and not args.map:
        # Interactive single-file mode
        filepath = Path(args.file)
        if not filepath.exists():
            print(f"File not found: {filepath}")
            sys.exit(1)
        interactive_label(filepath)

    elif args.dir and args.unmap:
        # Batch undo mode
        unmap = parse_speaker_map(args.unmap)
        batch_unlabel(args.dir, unmap, args.dry_run)

    elif args.dir and args.map:
        # Batch label mode
        mapping = parse_speaker_map(args.map)
        batch_label(args.dir, mapping, args.dry_run)

    elif args.dir and not args.map:
        # List speakers found in directory
        transcripts = find_transcripts(args.dir)
        for t in transcripts:
            content = t.read_text(encoding="utf-8")
            speakers = get_speaker_samples(content)
            if speakers:
                print(f"\n{t.name}: {len(speakers)} speaker(s)")
                for s, samples in sorted(speakers.items()):
                    print(f"  Speaker {s}: {samples[0]}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
