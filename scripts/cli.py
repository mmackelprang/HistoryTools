#!/usr/bin/env python3
"""
family-archive — Unified CLI entry point for the Family Archive Toolkit.

Dispatches subcommands to existing script main() functions.

Usage:
    family-archive bootstrap /path/to/source
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


def cmd_bootstrap(args):
    """Scan, classify, and process a source folder into an organized archive."""
    sys.argv = ['bootstrap'] + args
    from .bootstrap import main
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
    """Add summaries, headers, and markdown formatting to transcripts."""
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
    """Find identical files by MD5 hash and move duplicates."""
    sys.argv = ['handle_duplicates'] + args
    from .handle_duplicates import main
    main()


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

    subparsers.add_parser('bootstrap', help='Scan, classify, and process a source folder')
    subparsers.add_parser('organize', help='Classify and copy files to organized folders')
    subparsers.add_parser('transcribe', help='Transcribe PDFs with Gemini AI vision')
    subparsers.add_parser('transcribe-audio', help='Transcribe audio with AssemblyAI')
    subparsers.add_parser('format', help='Format transcripts with summaries and markdown')
    subparsers.add_parser('rename', help='Propose (or --apply) descriptive filenames')
    subparsers.add_parser('speakers', help='Assign real names to speaker labels')
    subparsers.add_parser('detect-dates', help='Detect dates in undated files')
    subparsers.add_parser('photos', help='Catalog photos with EXIF data')
    subparsers.add_parser('duplicates', help='Find and handle duplicate files')
    subparsers.add_parser('report', help='Generate archive summary report')
    subparsers.add_parser('verify', help='Verify required tools are installed')
    subparsers.add_parser('split', help='Split multi-document files (coming soon)')
    subparsers.add_parser('search', help='Search archive contents (coming soon)')
    subparsers.add_parser('serve', help='Start web UI for browsing (coming soon)')

    # Parse only the subcommand name; everything else is passed through
    args, remaining = parser.parse_known_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    dispatch = {
        'bootstrap': cmd_bootstrap,
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
        'split': cmd_placeholder('split'),
        'search': cmd_placeholder('search'),
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
