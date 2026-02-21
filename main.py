#!/usr/bin/env python3
"""
Astra Interview Copilot - Main Entry Point

Usage:
    python main.py                      Launch the GUI (starts at startup screen)
    python main.py --ingest ./docs/     Ingest documents then exit
"""

import argparse
import json
import os
import sys
import traceback


def _get_crash_log_path():
    """Get crash log path next to the exe (frozen) or in cwd (dev)."""
    if getattr(sys, 'frozen', False):
        return os.path.join(os.path.dirname(sys.executable), "crash.log")
    return None


def run_ingestion(folder_path: str, json_progress: bool = False) -> None:
    """Run the document ingestion process.

    Args:
        folder_path: Path to folder containing documents.
        json_progress: If True, emit JSON lines to stdout for GUI subprocess mode.
    """
    from ingest import ingest_folder_with_progress, ingest_folder

    if not json_progress:
        ingest_folder(folder_path)
        return

    # JSON progress mode — each line is a JSON object the GUI can parse
    def progress_callback(info: dict):
        print(json.dumps(info), flush=True)

    try:
        result = ingest_folder_with_progress(folder_path, progress_callback)
        print(json.dumps({"stage": "result", **result}), flush=True)
    except Exception as e:
        print(json.dumps({
            "stage": "result",
            "success": False,
            "total_files": 0,
            "total_chunks": 0,
            "errors": [str(e)]
        }), flush=True)
        sys.exit(1)


def launch_gui() -> None:
    """Launch the PyQt6 GUI application with startup screen."""
    from transcriber import get_whisper_model
    get_whisper_model()
    from PyQt6.QtWidgets import QApplication
    from gui import AstraApp
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    astra_app = AstraApp()
    astra_app.show()
    sys.exit(app.exec())


def _fix_frozen_stdio():
    """Restore sys.stdout/sys.stderr when running as a frozen windowed exe subprocess.

    PyInstaller's windowed bootloader (runw.exe) sets sys.stdout and sys.stderr to None
    even when the process was launched with stdout=PIPE (e.g. by subprocess.Popen).
    The OS-level file descriptor (fd 1/2) IS connected to the pipe, but Python doesn't
    know about it. We reconstruct text-mode wrappers from the raw fds so that print()
    and json.dumps() output reaches the parent process.

    This must be called before any print() or sys.stdout.write() in --ingest mode.
    """
    if not getattr(sys, 'frozen', False):
        return  # Only needed in frozen windowed exe
    try:
        import io
        if sys.stdout is None:
            sys.stdout = io.TextIOWrapper(
                io.FileIO(1, closefd=False),
                encoding='utf-8',
                errors='replace',
                line_buffering=True,
            )
        if sys.stderr is None:
            sys.stderr = io.TextIOWrapper(
                io.FileIO(2, closefd=False),
                encoding='utf-8',
                errors='replace',
                line_buffering=True,
            )
    except OSError:
        # fd 1/2 not connected (e.g. truly no console and no pipe) — stay silent
        pass


def main():
    parser = argparse.ArgumentParser(
        description="Astra Interview Copilot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python main.py                      Launch the interview copilot GUI
    python main.py --ingest ./docs/     Ingest documents from a folder
        """
    )
    parser.add_argument(
        "--ingest",
        metavar="FOLDER",
        type=str,
        help="Ingest documents from the specified folder"
    )
    parser.add_argument(
        "--json-progress",
        action="store_true",
        help="Output JSON progress lines (used by GUI subprocess mode)"
    )

    args = parser.parse_args()

    # Restore sys.stdout/stderr for frozen windowed exe spawned as a subprocess.
    # Must happen after argparse (which reads sys.argv, not stdout) but before any print().
    _fix_frozen_stdio()

    # Handle ingestion mode
    if args.ingest:
        if not args.json_progress:
            print("Starting document ingestion...")
        run_ingestion(args.ingest, json_progress=args.json_progress)
        if not args.json_progress:
            print("\nIngestion complete. You can now run: python main.py")
        return

    # Launch GUI with startup screen
    print("Starting Astra Interview Copilot...")
    launch_gui()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log_path = _get_crash_log_path()
        if log_path:
            with open(log_path, "w") as f:
                traceback.print_exc(file=f)
        raise
