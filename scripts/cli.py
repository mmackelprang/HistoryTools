#!/usr/bin/env python3
"""
family-archive — Unified CLI entry point for the Family Archive Toolkit.

Dispatches subcommands to existing script main() functions.

Usage:
    family-archive ingest /path/to/source
    family-archive organize --dry-run
    family-archive transcribe
    family-archive --help
    family-archive --version
"""

import sys
import argparse


def _get_version():
    """Get the package version, trying multiple methods."""
    # Method 1: importlib.metadata (works for installed packages)
    try:
        from importlib.metadata import version, PackageNotFoundError
        return version("family-archive-toolkit")
    except (PackageNotFoundError, ModuleNotFoundError):
        pass
    # Method 2: relative import from package __init__
    try:
        from . import __version__
        return __version__
    except (ImportError, SystemError):
        pass
    return "0.1.0"


__version__ = _get_version()


def cmd_ingest(args):
    """Scan, classify, and process a source folder into an organized archive."""
    sys.argv = ['ingest'] + args
    from .ingest import main
    main()


def cmd_organize(args):
    """Classify files by name/type, rename with dates, copy to organized folders."""
    sys.argv = ['organize'] + args
    from .organize import main
    main()


def cmd_transcribe(args):
    """Transcribe PDFs using Google Gemini AI vision."""
    sys.argv = ['transcribe_pdfs_gemini'] + args
    from .transcribe_pdfs_gemini import main
    main()


def cmd_transcribe_audio(args):
    """Transcribe audio with AssemblyAI (speaker diarization)."""
    sys.argv = ['transcribe_audio_assemblyai'] + args
    from .transcribe_audio_assemblyai import main
    main()


def cmd_format(args):
    """Format transcripts — mechanical cleanup (free) with optional AI summary (--with-summary)."""
    sys.argv = ['format_transcripts'] + args
    from .format_transcripts import main
    main()


def cmd_rename(args):
    """Propose or apply descriptive filenames for generic files using AI."""
    if '--apply' in args:
        args_copy = [a for a in args if a != '--apply']
        sys.argv = ['apply_renames'] + args_copy
        from .apply_renames import main
    else:
        sys.argv = ['propose_renames'] + args
        from .propose_renames import main
    main()


def cmd_speakers(args):
    """Assign real names to Speaker A/B/C labels in audio transcripts."""
    sys.argv = ['label_speakers'] + args
    from .label_speakers import main
    main()


def cmd_detect_dates(args):
    """Detect dates in undated files and propose renames."""
    sys.argv = ['detect_dates'] + args
    from .detect_dates import main
    main()


def cmd_photos(args):
    """Read EXIF data and generate photo catalog."""
    sys.argv = ['catalog_photos'] + args
    from .catalog_photos import main
    main()


def cmd_duplicates(args):
    """Detect, quarantine, restore, and purge duplicate files."""
    import argparse as _argparse
    parser = _argparse.ArgumentParser(description="Duplicate management")
    parser.add_argument("--config", default=None)
    parser.add_argument("--scan", action="store_true", help="Detect duplicates, write proposals")
    parser.add_argument("--apply", action="store_true", help="Quarantine approved duplicates")
    parser.add_argument("--status", action="store_true", help="Show quarantine summary")
    parser.add_argument("--restore", type=str, default=None, help="Restore a quarantined file")
    parser.add_argument("--purge", action="store_true", help="Delete files past TTL")
    parser.add_argument("--all", action="store_true", help="With --purge: ignore TTL")
    parser.add_argument("--dry-run", action="store_true", help="Preview without changes")
    parser.add_argument("--folder", default=None, help="Limit scan to folder")
    parser.add_argument("--type", default=None, choices=["exact", "similar"], help="Detection type filter")
    parser.add_argument("--threshold", type=float, default=0.90, help="Text similarity threshold")
    parsed = parser.parse_args(args)

    if not any([parsed.scan, parsed.apply, parsed.status, parsed.restore, parsed.purge]):
        parser.print_help()
        return

    from .config import load_config
    from .db import get_db, close_db

    config = load_config(parsed.config)
    dest_root = config["dest_root"]
    conn = get_db(dest_root, config)

    try:
        if parsed.scan:
            from .duplicate_detect import scan_duplicates, generate_proposals
            print("Scanning for duplicates...")
            groups = scan_duplicates(
                conn, dest_root,
                threshold=parsed.threshold,
                folder=parsed.folder,
                scan_type=parsed.type,
            )
            if groups:
                generate_proposals(groups, dest_root)
                print(f"\nFound {len(groups)} duplicate groups. Review:")
                print(f"  {dest_root / '_duplicate-proposals.md'}")
                print(f"\nThen run: family-archive duplicates --apply")
            else:
                print("No duplicates found.")

        elif parsed.apply:
            from .duplicate_manage import apply_quarantine
            apply_quarantine(conn, dest_root, dry_run=parsed.dry_run)

        elif parsed.status:
            from .duplicate_manage import get_quarantine_status
            status = get_quarantine_status(conn)
            print(f"\nQuarantine status:")
            print(f"  Files:   {status['total_files']}")
            size_mb = status['total_size_bytes'] / (1024 * 1024)
            print(f"  Size:    {size_mb:.1f} MB")
            print(f"  Expired: {status['expired']} (ready to purge)")
            if status.get('by_reason'):
                print(f"  By type:")
                for reason, count in status['by_reason'].items():
                    print(f"    {reason}: {count}")

        elif parsed.restore:
            from .duplicate_manage import restore_file
            restore_file(conn, dest_root, parsed.restore)

        elif parsed.purge:
            from .duplicate_manage import purge_expired
            purge_expired(conn, dest_root, purge_all=parsed.all)

    finally:
        close_db(conn)


def cmd_report(args):
    """Produce archive summary with statistics."""
    sys.argv = ['generate_report'] + args
    from .generate_report import main
    main()


def cmd_verify(args):
    """Check that all required tools are installed and working."""
    sys.argv = ['verify_tools'] + args
    from .verify_tools import main
    main()


def cmd_init(args):
    """Interactive setup wizard for first-time users."""
    sys.argv = ['init'] + args
    from .init_wizard import main
    main()


def cmd_split(args):
    """Propose or apply document splits for compilation PDFs."""
    if '--apply' in args:
        args_copy = [a for a in args if a != '--apply']
        sys.argv = ['split_apply'] + args_copy
        from .split_apply import main
    else:
        sys.argv = ['split_propose'] + args
        from .split_propose import main
    main()


def cmd_costs(args):
    """Show AI API cost summary from _costs.json."""
    import json as _json
    from pathlib import Path as _Path

    # Find config to get dest_root
    try:
        sys.path.insert(0, str(_Path(__file__).resolve().parent))
        from .config import load_config
        config = load_config()
        dest_root = config["dest_root"]
    except Exception:
        # Fallback: look in current directory
        dest_root = _Path.cwd()

    costs_path = _Path(dest_root) / "_costs.json"
    if not costs_path.exists():
        print("No cost data found. AI cost tracking records usage in _costs.json")
        print("after running AI-powered commands (transcribe, format, rename, etc.).")
        return

    with open(costs_path, "r", encoding="utf-8") as f:
        sessions = _json.load(f)

    if not sessions:
        print("No cost data recorded yet.")
        return

    total_cost = sum(s.get("total_cost_usd", 0) for s in sessions)
    total_calls = sum(s.get("total_calls", 0) for s in sessions)
    total_input = sum(s.get("total_input_tokens", 0) for s in sessions)
    total_output = sum(s.get("total_output_tokens", 0) for s in sessions)

    # Aggregate by step across all sessions
    by_step = {}
    for s in sessions:
        for step, data in s.get("by_step", {}).items():
            if step not in by_step:
                by_step[step] = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
            by_step[step]["calls"] += data.get("calls", 0)
            by_step[step]["input_tokens"] += data.get("input_tokens", 0)
            by_step[step]["output_tokens"] += data.get("output_tokens", 0)
            by_step[step]["cost_usd"] += data.get("cost_usd", 0.0)

    print(f"\nAI Cost Summary ({len(sessions)} sessions, {total_calls} calls)")
    print(f"{'=' * 55}")

    if by_step:
        for step, data in sorted(by_step.items()):
            print(f"  {step:30s} {data['calls']:4d} calls  ${data['cost_usd']:.4f}")
        print(f"  {'─' * 51}")

    print(f"  {'TOTAL':30s} {total_calls:4d} calls  ${total_cost:.4f}")
    print(f"  Tokens: {total_input:,} in / {total_output:,} out")

    if '--detail' in args:
        print(f"\n{'─' * 55}")
        print("Session details:")
        for i, s in enumerate(sessions, 1):
            start = s.get("session_start", "?")[:19]
            print(f"  {i}. {start}  {s.get('total_calls', 0)} calls  ${s.get('total_cost_usd', 0):.4f}")


def cmd_reindex(args):
    """Rebuild the search index from the filesystem."""
    sys.argv = ['reindex'] + args
    import argparse as _argparse
    parser = _argparse.ArgumentParser(description="Rebuild search index")
    parser.add_argument("--config", default=None)
    parser.add_argument("--check", action="store_true", help="Verify without modifying")
    parsed = parser.parse_args(args)

    from .config import load_config
    from .db import get_db, reindex_all, check_index, close_db
    config = load_config(parsed.config)
    conn = get_db(config["dest_root"], config)
    if parsed.check:
        check_index(conn, config["dest_root"])
    else:
        reindex_all(conn, config["dest_root"])
    close_db(conn)


def cmd_search(args):
    """Search across all transcripts."""
    import argparse as _argparse
    parser = _argparse.ArgumentParser(description="Search transcripts")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--config", default=None)
    parser.add_argument("--folder", default=None)
    parser.add_argument("--type", default=None)
    parser.add_argument("--year", default=None)
    parser.add_argument("--limit", type=int, default=10)
    parsed = parser.parse_args(args)

    from .config import load_config
    from .db import get_db, search, close_db
    config = load_config(parsed.config)
    conn = get_db(config["dest_root"], config)
    results = search(conn, parsed.query, folder=parsed.folder, file_type=parsed.type,
                     year=parsed.year, limit=parsed.limit)
    close_db(conn)

    if not results:
        print(f'No results for "{parsed.query}"')
        return

    print(f'\nFound {len(results)} results for "{parsed.query}":\n')
    for i, r in enumerate(results, 1):
        # Encode safely for Windows console
        path = r["path"]
        snippet = r["snippet"].encode("ascii", errors="replace").decode("ascii")
        print(f'  {i}. {path}')
        print(f'     "{snippet}"')
        print(f'     ({r["file_type"]}, {r["date_prefix"]}, {r["word_count"]} words)\n')


def cmd_stats(args):
    """Show archive statistics from the search index."""
    import argparse as _argparse
    parser = _argparse.ArgumentParser(description="Archive statistics")
    parser.add_argument("--config", default=None)
    parsed = parser.parse_args(args)

    from .config import load_config
    from .db import get_db, get_stats, close_db
    config = load_config(parsed.config)
    dest_root = config["dest_root"]
    conn = get_db(dest_root, config)
    stats = get_stats(conn)
    close_db(conn)

    # Determine DB path for display
    db_path = config.get("db_path") or str(dest_root / ".archive.db")

    print(f"\nArchive: {dest_root}")
    print(f"Database: {db_path}")

    print(f"\nFiles:        {stats['total_files']:,}")
    type_labels = {
        "document": "Documents", "audio": "Audio", "photo": "Photos",
        "video": "Video", "transcript": "Transcripts", "spreadsheet": "Spreadsheets",
        "email": "Email", "genealogy": "Genealogy", "unknown": "Other",
    }
    for ftype, count in sorted(stats["files_by_type"].items(), key=lambda x: -x[1]):
        label = type_labels.get(ftype, ftype.title())
        print(f"  {label:14s} {count:,}")

    print(f"\nTranscripts:  {stats['total_transcripts']:,}")
    for conf, count in sorted(stats["transcripts_by_confidence"].items(), key=lambda x: -x[1]):
        print(f"  {conf.title():14s} {count:,}")

    print(f"\nTotal words: {stats['total_words']:,}")
    if stats["last_indexed"]:
        print(f"Last indexed: {stats['last_indexed']}")


def cmd_placeholder(name):
    """Return a handler for placeholder commands."""
    def handler(args):
        print("Coming soon in a future release.")
    handler.__doc__ = f"{name} (coming soon)"
    return handler


def main():
    """Main entry point for the family-archive CLI."""
    parser = argparse.ArgumentParser(
        prog='family-archive',
        description='CLI toolkit for digitizing, organizing, transcribing, and searching family archives.',
    )
    parser.add_argument(
        '--version', action='version',
        version=f'family-archive {__version__}',
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Each subcommand gets a parser entry. We don't define specific arguments here
    # because each script has its own argparse — we pass remaining args through.

    subparsers.add_parser('init', help='Interactive setup wizard for first-time users')
    subparsers.add_parser('ingest', help='Scan, classify, and process a source folder')
    subparsers.add_parser('organize', help='Classify and copy files to organized folders')
    subparsers.add_parser('transcribe', help='Transcribe PDFs with AI vision (Gemini or OpenAI; --vendor planned)')
    subparsers.add_parser('transcribe-audio', help='Transcribe audio with AssemblyAI')
    subparsers.add_parser('format', help='Format transcripts with AI (Claude or OpenAI; --vendor planned)')
    subparsers.add_parser('rename', help='Propose (or --apply) descriptive filenames')
    subparsers.add_parser('speakers', help='Assign real names to speaker labels')
    subparsers.add_parser('detect-dates', help='Detect dates in undated files')
    subparsers.add_parser('photos', help='Catalog photos with EXIF data')
    subparsers.add_parser('duplicates', help='Detect and manage duplicate files (--scan, --apply, --status, --purge)')
    subparsers.add_parser('report', help='Generate archive summary report')
    subparsers.add_parser('verify', help='Verify required tools are installed')
    subparsers.add_parser('split', help='Split compilation PDFs into individual documents (or --apply)')
    subparsers.add_parser('costs', help='Show AI API cost summary (--detail for session breakdown)')
    subparsers.add_parser('reindex', help='Rebuild search index from filesystem')
    subparsers.add_parser('search', help='Search across all transcripts')
    subparsers.add_parser('stats', help='Show archive statistics from search index')
    subparsers.add_parser('serve', help='Start web UI for browsing (coming soon)')

    # Parse only the subcommand name; everything else is passed through
    args, remaining = parser.parse_known_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    dispatch = {
        'init': cmd_init,
        'ingest': cmd_ingest,
        'organize': cmd_organize,
        'transcribe': cmd_transcribe,
        'transcribe-audio': cmd_transcribe_audio,
        'format': cmd_format,
        'rename': cmd_rename,
        'speakers': cmd_speakers,
        'detect-dates': cmd_detect_dates,
        'photos': cmd_photos,
        'duplicates': cmd_duplicates,
        'report': cmd_report,
        'verify': cmd_verify,
        'split': cmd_split,
        'costs': cmd_costs,
        'reindex': cmd_reindex,
        'search': cmd_search,
        'stats': cmd_stats,
        'serve': cmd_placeholder('serve'),
    }

    handler = dispatch.get(args.command)
    if handler:
        handler(remaining)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
