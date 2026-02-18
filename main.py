#!/usr/bin/env python3
"""
Astra Interview Copilot - Main Entry Point

Usage:
    python main.py                      Launch the GUI (starts at startup screen)
    python main.py --ingest ./docs/     Ingest documents then exit
"""

import argparse
import os
import sys
import traceback


def _get_crash_log_path():
    """Get crash log path next to the exe (frozen) or in cwd (dev)."""
    if getattr(sys, 'frozen', False):
        return os.path.join(os.path.dirname(sys.executable), "crash.log")
    return None


def run_ingestion(folder_path: str) -> None:
    """Run the document ingestion process."""
    from ingest import ingest_folder
    ingest_folder(folder_path)


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

    args = parser.parse_args()

    # Handle ingestion mode
    if args.ingest:
        print("Starting document ingestion...")
        run_ingestion(args.ingest)
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
