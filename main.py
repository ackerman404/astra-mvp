#!/usr/bin/env python3
"""
Astra Interview Copilot - Main Entry Point

Usage:
    python main.py                      Launch the GUI (starts at startup screen)
    python main.py --ingest ./docs/     Ingest documents then exit
"""

import argparse
import logging
import os
import sys


def _setup_crash_log():
    """Redirect stderr to a log file when running as a frozen PyInstaller exe."""
    if getattr(sys, 'frozen', False):
        from platformdirs import user_data_dir
        log_dir = user_data_dir("astra", ensure_exists=True)
        log_path = os.path.join(log_dir, "crash.log")
        logging.basicConfig(
            filename=log_path,
            level=logging.DEBUG,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
        # Also redirect stderr so uncaught exceptions go to the file
        sys.stderr = open(log_path, "a")
        logging.info("Astra starting (frozen exe)")


def run_ingestion(folder_path: str) -> None:
    """Run the document ingestion process."""
    from ingest import ingest_folder
    ingest_folder(folder_path)


def launch_gui() -> None:
    """Launch the PyQt6 GUI application with startup screen."""
    # Pre-load Whisper model in main thread to avoid threading conflicts
    # with onnxruntime when transcription runs in background threads
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
    _setup_crash_log()

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
    try:
        launch_gui()
    except Exception:
        logging.exception("Fatal error during startup")
        raise


if __name__ == "__main__":
    main()
