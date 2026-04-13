#!/usr/bin/env python3
"""
Astra Interview Copilot - PyQt6 GUI
Captures system audio and provides AI-powered interview answers.
"""

import json
import os
import subprocess
import sys
import threading
import argparse
from queue import Queue
from concurrent.futures import ThreadPoolExecutor
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QLineEdit,
    QComboBox,
    QProgressBar,
    QCheckBox,
    QSlider,
    QFrame,
    QMessageBox,
    QSplitter,
    QSizePolicy,
    QScrollArea,
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QTimer, QUrl
from PyQt6.QtGui import QFont, QTextCursor, QDesktopServices

from transcriber import transcribe_audio
from audio_capture import get_audio_capture
from rag import (
    ask, ask_bullet, ask_script, classify_utterance,
    get_available_tones, get_default_job_context, get_default_tone, reload_prompts_config,
)
import requests

from config import (
    SILENCE_THRESHOLD,
    SILENCE_DURATION,
    MIN_SPEECH_DURATION,
    CLASSIFICATION_CONFIDENCE,
    MIN_WORDS_FOR_CLASSIFICATION,
    AUDIO_SAMPLE_RATE,
    get_license_key,
    get_proxy_url,
    save_license_key,
    clear_license_key,
    get_hardware_id,
    get_config_dir,
)


class ListeningState:
    """Enum-like class for listening states."""
    IDLE = "idle"
    LISTENING = "listening"        # Silence, waiting for speech
    HEARING = "hearing"            # Speech detected
    PROCESSING = "processing"      # Transcribing/classifying
    GENERATING = "generating"      # RAG answer in progress


class SignalBridge(QObject):
    """Bridge for thread-safe UI updates."""
    transcription_ready = pyqtSignal(str)
    answer_token = pyqtSignal(str)
    answer_done = pyqtSignal()
    answer_clear = pyqtSignal()  # Clear answer box from background thread
    status_update = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    audio_level = pyqtSignal(float)
    # New signals for auto-answer mode
    state_changed = pyqtSignal(str)           # ListeningState value
    last_heard_update = pyqtSignal(str, str)  # text, status ("ignored"/"answering"/"")
    queue_update = pyqtSignal(int)            # Number of queued questions
    # Dual-pane answer signals
    bullet_token = pyqtSignal(str)            # Streaming token for bullet points
    script_token = pyqtSignal(str)            # Streaming token for script
    question_update = pyqtSignal(str)         # Update question display
    # License deactivation result (success: bool, message: str)
    deactivation_result = pyqtSignal(bool, str)


class IngestionSignals(QObject):
    """Signals for document ingestion progress."""
    progress = pyqtSignal(dict)  # Progress info dict
    complete = pyqtSignal(dict)  # Result summary dict


class FitTextEdit(QTextEdit):
    """QTextEdit that shrinks font to fit content without scrolling."""

    def __init__(self, initial_font_size=16, min_font_size=10):
        super().__init__()
        self.setReadOnly(True)
        self.initial_font_size = initial_font_size
        self.min_font_size = min_font_size

        # Show scrollbars only when content still exceeds after shrinking
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        font = QFont("Sans", initial_font_size)
        self.setFont(font)

    def reset_font(self):
        """Reset to initial font size before new content."""
        font = self.font()
        font.setPointSize(self.initial_font_size)
        self.setFont(font)

    def finalize_content(self):
        """Call after streaming completes to shrink font if needed."""
        text = self.toPlainText()
        if not text:
            return

        doc = self.document()
        doc.adjustSize()
        viewport_height = self.viewport().height()

        # Only shrink if content exceeds viewport
        if doc.size().height() <= viewport_height:
            return

        font = self.font()
        size = self.initial_font_size

        while size > self.min_font_size:
            font.setPointSize(size)
            self.setFont(font)
            doc.adjustSize()

            if doc.size().height() <= viewport_height:
                break

            size -= 1


class StartupScreen(QWidget):
    """Startup screen with Ingest Documents and Start Session buttons."""

    # Signals emitted when buttons are clicked
    ingest_requested = pyqtSignal()
    start_session_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._init_ui()

    def _init_ui(self):
        """Set up the startup screen user interface."""
        self.setWindowTitle("Astra Interview Copilot")
        self.setMinimumSize(350, 300)
        self.resize(400, 350)
        self.setStyleSheet("background-color: #ffffff;")

        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(40, 40, 40, 40)

        # Title
        title = QLabel("Astra Interview Copilot")
        title.setFont(QFont("Sans", 18, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color: #222222;")
        layout.addWidget(title)

        # Instructions
        instructions = QLabel(
            "Welcome! Choose an option below:\n\n"
            "• Ingest Documents - Pick a folder with your\n"
            "  .pdf, .txt, or .md files to build your knowledge base\n\n"
            "• Start Session - Begin the interview copilot"
        )
        instructions.setFont(QFont("Sans", 10))
        instructions.setAlignment(Qt.AlignmentFlag.AlignLeft)
        instructions.setStyleSheet("color: #555555;")
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        layout.addStretch()

        # Ingest Documents button (blue - primary action)
        self.ingest_btn = QPushButton("Ingest Documents")
        self.ingest_btn.setFont(QFont("Sans", 12))
        self.ingest_btn.setMinimumHeight(50)
        self.ingest_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a90d9;
                color: white;
                border: none;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #3a7bc8;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.ingest_btn.clicked.connect(self._on_ingest_clicked)
        layout.addWidget(self.ingest_btn)

        # Start Session button (green - secondary action)
        self.start_btn = QPushButton("Start Session")
        self.start_btn.setFont(QFont("Sans", 12))
        self.start_btn.setMinimumHeight(50)
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                border: none;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.start_btn.clicked.connect(self._on_start_session_clicked)
        layout.addWidget(self.start_btn)

        # Progress bar for ingestion (hidden by default)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setMaximumHeight(20)
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #ddd;
                border-radius: 4px;
                background-color: #f5f5f5;
            }
            QProgressBar::chunk {
                background-color: #4a90d9;
                border-radius: 3px;
            }
        """)
        layout.addWidget(self.progress_bar)

        # Status label for ingestion feedback
        self.status_label = QLabel("")
        self.status_label.setFont(QFont("Sans", 9))
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: #666666;")
        layout.addWidget(self.status_label)

    def _on_ingest_clicked(self):
        """Handle Ingest Documents button click."""
        self.ingest_requested.emit()

    def _on_start_session_clicked(self):
        """Handle Start Session button click."""
        self.start_session_requested.emit()

    def set_status(self, message: str, is_error: bool = False):
        """Update the status label."""
        if is_error:
            self.status_label.setStyleSheet("color: #d9534f;")
        else:
            self.status_label.setStyleSheet("color: #666666;")
        self.status_label.setText(message)

    def set_buttons_enabled(self, enabled: bool):
        """Enable or disable buttons during operations."""
        self.ingest_btn.setEnabled(enabled)
        self.start_btn.setEnabled(enabled)

    def show_progress_bar(self, show: bool):
        """Toggle progress bar visibility."""
        self.progress_bar.setVisible(show)

    def set_progress(self, current: int, total: int):
        """Update progress bar value."""
        if total > 0:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(current)
        else:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)


class LicenseActivationScreen(QWidget):
    """Friendly license activation screen with clear guidance and paste support."""

    activated = pyqtSignal()
    skipped = pyqtSignal()
    _activation_result = pyqtSignal(str, str)  # (status_msg, color_type)

    def __init__(self):
        super().__init__()
        self._init_ui()
        self._activation_result.connect(self._handle_activation_result)

    def _init_ui(self):
        """Set up the activation screen UI."""
        self.setWindowTitle("Astra - License Activation")
        self.setMinimumSize(420, 520)
        self.resize(420, 520)
        self.setStyleSheet("background-color: #ffffff;")

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(40, 35, 40, 30)

        # Title
        title = QLabel("Astra Interview Copilot")
        title.setFont(QFont("Sans", 20, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color: #222222;")
        layout.addWidget(title)

        # Subtitle
        subtitle = QLabel("Activate Your License")
        subtitle.setFont(QFont("Sans", 13))
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color: #666666;")
        layout.addWidget(subtitle)

        layout.addSpacing(10)

        # Step-by-step instructions
        steps = QLabel(
            "1. Copy your license key from the purchase email\n"
            "2. Paste it below (Ctrl+V)\n"
            "3. Click Activate"
        )
        steps.setFont(QFont("Sans", 10))
        steps.setStyleSheet("""
            QLabel {
                color: #555555;
                background-color: #f8f9fa;
                border: 1px solid #e9ecef;
                border-radius: 6px;
                padding: 12px 16px;
            }
        """)
        steps.setWordWrap(True)
        layout.addWidget(steps)

        layout.addSpacing(5)

        # License key input — larger, with paste hint
        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("Paste license key here (Ctrl+V)")
        self.key_input.setFont(QFont("Consolas", 13))
        self.key_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.key_input.setMinimumHeight(50)
        self.key_input.setStyleSheet("""
            QLineEdit {
                border: 2px solid #ddd;
                border-radius: 8px;
                padding: 10px 14px;
                background-color: #ffffff;
                color: #222222;
            }
            QLineEdit:focus {
                border-color: #4a90d9;
                background-color: #f0f7ff;
            }
        """)
        # Allow Enter key to activate
        self.key_input.returnPressed.connect(self._on_activate)
        layout.addWidget(self.key_input)

        # Status label (hidden initially)
        self.status_label = QLabel("")
        self.status_label.setFont(QFont("Sans", 11))
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setWordWrap(True)
        self.status_label.setMinimumHeight(40)
        self.status_label.setVisible(False)
        layout.addWidget(self.status_label)

        # Activate button — big and friendly
        self.activate_btn = QPushButton("Activate License")
        self.activate_btn.setFont(QFont("Sans", 13, QFont.Weight.Bold))
        self.activate_btn.setMinimumHeight(52)
        self.activate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.activate_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                border: none;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
            QPushButton:pressed {
                background-color: #1e7e34;
            }
            QPushButton:disabled {
                background-color: #a0d4b0;
                color: #e0e0e0;
            }
        """)
        self.activate_btn.clicked.connect(self._on_activate)
        layout.addWidget(self.activate_btn)

        layout.addStretch()

        # Purchase link — more visible
        purchase_link = QLabel(
            '<a href="#" style="color: #4a90d9; text-decoration: none;">'
            'Don\'t have a key? Get one at astra-copilot.com</a>'
        )
        purchase_link.setFont(QFont("Sans", 10))
        purchase_link.setAlignment(Qt.AlignmentFlag.AlignCenter)
        purchase_link.linkActivated.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://astra-copilot.com"))
        )
        layout.addWidget(purchase_link)

        layout.addSpacing(5)

        # Continue without license — smaller, clearly secondary
        skip_link = QLabel(
            '<a href="#" style="color: #aaaaaa; text-decoration: none;">'
            'Skip for now (limited features)</a>'
        )
        skip_link.setFont(QFont("Sans", 9))
        skip_link.setAlignment(Qt.AlignmentFlag.AlignCenter)
        skip_link.linkActivated.connect(self._on_skip)
        layout.addWidget(skip_link)

    def _set_status(self, msg: str, color_type: str):
        """Set status label with color-coded feedback."""
        styles = {
            "success": "background-color: #d4edda; color: #155724; border: 1px solid #c3e6cb;",
            "error": "background-color: #f8d7da; color: #721c24; border: 1px solid #f5c6cb;",
            "warning": "background-color: #fff3cd; color: #856404; border: 1px solid #ffeeba;",
            "info": "background-color: #e2e3e5; color: #383d41; border: 1px solid #d6d8db;",
        }
        style = styles.get(color_type, styles["info"])
        self.status_label.setStyleSheet(f"QLabel {{ {style} border-radius: 6px; padding: 10px 14px; }}")
        self.status_label.setText(msg)
        self.status_label.setVisible(True)

    def _on_activate(self):
        """Handle activate button click — runs network call in background thread."""
        self.activate_btn.setEnabled(False)
        self.activate_btn.setText("Activating...")
        self._set_status("Contacting server...", "info")

        key = self.key_input.text().strip()
        if not key:
            self._set_status("Please paste your license key above", "error")
            self.activate_btn.setEnabled(True)
            self.activate_btn.setText("Activate License")
            self.key_input.setFocus()
            return

        thread = threading.Thread(target=self._activate_in_background, args=(key,), daemon=True)
        thread.start()

    def _activate_in_background(self, key: str):
        """Background thread: call license activation API without blocking GUI."""
        proxy_url = get_proxy_url()
        hw_id = get_hardware_id()
        try:
            base = proxy_url.rsplit("/v1", 1)[0]
            resp = requests.post(
                f"{base}/v1/license/activate",
                json={"license_key": key, "hardware_id": hw_id},
                timeout=10,
            )
            if resp.status_code == 200:
                save_license_key(key)
                self._activation_result.emit("License activated! Starting Astra...", "success")
            else:
                error = resp.json().get("detail", {}).get("error", {})
                msg = error.get("message", "Activation failed. Check your key and try again.")
                self._activation_result.emit(msg, "error")
        except requests.ConnectionError:
            save_license_key(key)
            self._activation_result.emit(
                "Saved! Server is offline — key will be validated next time.", "warning"
            )
        except Exception as e:
            self._activation_result.emit(f"Connection error: {e}", "error")

    def _handle_activation_result(self, msg: str, color_type: str):
        """Handle activation result on the main thread (signal handler)."""
        self._set_status(msg, color_type)
        self.activate_btn.setText("Activate License")
        if color_type in ("success", "warning"):
            delay = 800 if color_type == "success" else 1200
            QTimer.singleShot(delay, self.activated.emit)
        else:
            self.activate_btn.setEnabled(True)
            self.key_input.setFocus()
            self.key_input.selectAll()

    def _on_skip(self):
        """Handle continue without license."""
        self.skipped.emit()

    def reset(self):
        """Reset the screen for re-display (e.g. after deactivation)."""
        self.key_input.clear()
        self.status_label.setVisible(False)
        self.activate_btn.setEnabled(True)
        self.activate_btn.setText("Activate License")


class AstraWindow(QMainWindow):
    # Emitted after successful deactivation so AstraApp can switch screens
    license_deactivated = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.capture = None
        self.signals = SignalBridge()
        self.is_listening = False
        self.level_timer = None

        # Auto-answer mode state
        self.auto_answer_enabled = True
        self.current_state = ListeningState.IDLE
        self.speech_start_time = None
        self.silence_start_time = None
        self.question_queue = Queue()
        self.is_processing = False
        self.confidence_threshold = CLASSIFICATION_CONFIDENCE

        # Q&A history
        self.qa_history = []
        self._bullet_buffer = ""
        self._viewing_history = False

        self._init_ui()
        self._connect_signals()
        self._init_capture()

    def _init_capture(self):
        """Initialize audio capture with selected device."""
        try:
            device = self.device_combo.currentData()
            self.capture = get_audio_capture(device)
            self.status_label.setText("Status: Ready")
        except Exception as e:
            self.capture = None
            self.status_label.setText(f"Status: Error - {e}")
            self._set_buttons_enabled(False)

    def _init_ui(self):
        """Set up the user interface."""
        self.setWindowTitle("Astra Interview Copilot")
        self.setMinimumSize(600, 400)
        self.resize(900, 600)

        # Make window semi-transparent
        self.setWindowOpacity(0.92)

        # Central widget and layout
        central = QWidget()
        central.setStyleSheet("background-color: rgba(255, 255, 255, 230);")
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # ═══════════════════════════════════════════════════════
        # COMPACT TOOLBAR (44px)
        # ═══════════════════════════════════════════════════════
        toolbar = QFrame()
        toolbar.setFixedHeight(44)
        toolbar.setStyleSheet("""
            QFrame {
                background-color: rgba(248, 249, 250, 240);
                border-bottom: 1px solid #ddd;
            }
        """)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(10, 0, 10, 0)
        toolbar_layout.setSpacing(10)

        # State indicator (emoji + text)
        self.state_indicator = QLabel("⚪")
        self.state_indicator.setFont(QFont("Sans", 14))
        toolbar_layout.addWidget(self.state_indicator)

        self.state_text = QLabel("Ready")
        self.state_text.setFont(QFont("Sans", 10))
        self.state_text.setStyleSheet("color: #333333;")
        toolbar_layout.addWidget(self.state_text)

        # Thin separator
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.VLine)
        sep1.setStyleSheet("color: #ddd;")
        toolbar_layout.addWidget(sep1)

        # Audio level bar (inline)
        self.level_bar = QProgressBar()
        self.level_bar.setRange(0, 100)
        self.level_bar.setValue(0)
        self.level_bar.setTextVisible(False)
        self.level_bar.setFixedWidth(80)
        self.level_bar.setMaximumHeight(14)
        self.level_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #ddd;
                border-radius: 3px;
                background-color: rgba(245, 245, 245, 200);
            }
            QProgressBar::chunk {
                background-color: rgba(40, 167, 69, 220);
                border-radius: 2px;
            }
        """)
        toolbar_layout.addWidget(self.level_bar)

        # Queue label
        self.queue_label = QLabel("")
        self.queue_label.setFont(QFont("Sans", 9))
        self.queue_label.setStyleSheet("color: #666666;")
        toolbar_layout.addWidget(self.queue_label)

        toolbar_layout.addStretch()

        # Listen button (compact)
        self.listen_btn = QPushButton("🎧 Listen")
        self.listen_btn.setFont(QFont("Sans", 10))
        self.listen_btn.setFixedHeight(30)
        self.listen_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(74, 144, 217, 230);
                color: white;
                border: none;
                border-radius: 4px;
                padding: 0 14px;
            }
            QPushButton:hover {
                background-color: rgba(58, 123, 200, 240);
            }
            QPushButton:disabled {
                background-color: rgba(204, 204, 204, 200);
            }
        """)
        self.listen_btn.clicked.connect(self._on_listen_toggle)
        toolbar_layout.addWidget(self.listen_btn)

        # Answer button (compact)
        self.answer_btn = QPushButton("💡 Answer")
        self.answer_btn.setFont(QFont("Sans", 10))
        self.answer_btn.setFixedHeight(30)
        self.answer_btn.setEnabled(False)
        self.answer_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(40, 167, 69, 230);
                color: white;
                border: none;
                border-radius: 4px;
                padding: 0 14px;
            }
            QPushButton:hover {
                background-color: rgba(33, 136, 56, 240);
            }
            QPushButton:disabled {
                background-color: rgba(204, 204, 204, 200);
            }
        """)
        self.answer_btn.clicked.connect(self._on_get_answer)
        toolbar_layout.addWidget(self.answer_btn)

        # Settings toggle button
        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setFont(QFont("Sans", 14))
        self.settings_btn.setFixedSize(30, 30)
        self.settings_btn.setToolTip("Toggle settings panel")
        self.settings_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: 1px solid #ccc;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: rgba(224, 224, 224, 200);
            }
        """)
        self.settings_btn.clicked.connect(self._toggle_settings)
        toolbar_layout.addWidget(self.settings_btn)

        main_layout.addWidget(toolbar)

        # ═══════════════════════════════════════════════════════
        # COLLAPSIBLE SETTINGS PANEL (hidden by default)
        # ═══════════════════════════════════════════════════════
        self.settings_panel = QFrame()
        self.settings_panel.setVisible(False)
        self.settings_panel.setStyleSheet("""
            QFrame {
                background-color: rgba(248, 249, 250, 240);
                border-bottom: 1px solid #ddd;
            }
        """)
        settings_outer = QVBoxLayout(self.settings_panel)
        settings_outer.setContentsMargins(10, 8, 10, 8)
        settings_outer.setSpacing(8)

        # Row 1: Audio device + Test | Job context
        row1 = QHBoxLayout()
        row1.setSpacing(8)

        audio_label = QLabel("Audio:")
        audio_label.setFont(QFont("Sans", 9))
        audio_label.setStyleSheet("color: #555555;")
        row1.addWidget(audio_label)

        self.device_combo = QComboBox()
        self.device_combo.setFont(QFont("Sans", 9))
        self.device_combo.setStyleSheet("""
            QComboBox {
                background-color: rgba(255, 255, 255, 220);
                color: #333333;
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 3px 6px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: rgba(255, 255, 255, 240);
                color: #333333;
                selection-background-color: #4a90d9;
            }
        """)
        self._populate_devices()
        self.device_combo.currentIndexChanged.connect(self._on_device_changed)
        row1.addWidget(self.device_combo, stretch=1)

        self.test_btn = QPushButton("Test")
        self.test_btn.setFont(QFont("Sans", 9))
        self.test_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(108, 117, 125, 220);
                color: white;
                border: none;
                border-radius: 4px;
                padding: 3px 12px;
            }
            QPushButton:hover {
                background-color: rgba(90, 98, 104, 230);
            }
            QPushButton:disabled {
                background-color: rgba(204, 204, 204, 200);
            }
        """)
        self.test_btn.clicked.connect(self._on_test_audio)
        row1.addWidget(self.test_btn)

        # Vertical separator
        sep_r1 = QFrame()
        sep_r1.setFrameShape(QFrame.Shape.VLine)
        sep_r1.setStyleSheet("color: #ddd;")
        row1.addWidget(sep_r1)

        job_label = QLabel("Job:")
        job_label.setFont(QFont("Sans", 9))
        job_label.setStyleSheet("color: #555555;")
        row1.addWidget(job_label)

        self.job_context_input = QLineEdit()
        self.job_context_input.setPlaceholderText("e.g., Senior SAP MM Consultant")
        self.job_context_input.setText(get_default_job_context())
        self.job_context_input.setFont(QFont("Sans", 9))
        self.job_context_input.setStyleSheet("""
            QLineEdit {
                background-color: rgba(255, 255, 255, 220);
                color: #333333;
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 3px 6px;
            }
        """)
        self.job_context_input.setMinimumWidth(150)
        row1.addWidget(self.job_context_input, stretch=1)

        settings_outer.addLayout(row1)

        # Row 2: Auto-answer + confidence | Tone + Reload | Deactivate
        row2 = QHBoxLayout()
        row2.setSpacing(8)

        self.auto_checkbox = QCheckBox("Auto-answer")
        self.auto_checkbox.setFont(QFont("Sans", 9))
        self.auto_checkbox.setStyleSheet("color: #333333;")
        self.auto_checkbox.setChecked(True)
        self.auto_checkbox.toggled.connect(self._on_auto_mode_toggled)
        row2.addWidget(self.auto_checkbox)

        conf_label = QLabel("Confidence:")
        conf_label.setFont(QFont("Sans", 9))
        conf_label.setStyleSheet("color: #555555;")
        row2.addWidget(conf_label)

        self.confidence_slider = QSlider(Qt.Orientation.Horizontal)
        self.confidence_slider.setMinimum(30)
        self.confidence_slider.setMaximum(95)
        self.confidence_slider.setValue(int(CLASSIFICATION_CONFIDENCE * 100))
        self.confidence_slider.setFixedWidth(80)
        self.confidence_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 6px;
                background: #ddd;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                width: 14px;
                margin: -4px 0;
                background: #4a90d9;
                border-radius: 7px;
            }
        """)
        self.confidence_slider.valueChanged.connect(self._on_confidence_changed)
        row2.addWidget(self.confidence_slider)

        self.confidence_label = QLabel(f"{CLASSIFICATION_CONFIDENCE:.2f}")
        self.confidence_label.setFont(QFont("Sans", 9))
        self.confidence_label.setStyleSheet("color: #555555;")
        self.confidence_label.setFixedWidth(30)
        row2.addWidget(self.confidence_label)

        sep_r2 = QFrame()
        sep_r2.setFrameShape(QFrame.Shape.VLine)
        sep_r2.setStyleSheet("color: #ddd;")
        row2.addWidget(sep_r2)

        tone_label = QLabel("Tone:")
        tone_label.setFont(QFont("Sans", 9))
        tone_label.setStyleSheet("color: #555555;")
        row2.addWidget(tone_label)

        self.tone_combo = QComboBox()
        self.tone_combo.setFont(QFont("Sans", 9))
        self.tone_combo.setStyleSheet("""
            QComboBox {
                background-color: rgba(255, 255, 255, 220);
                color: #333333;
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 3px 6px;
            }
            QComboBox::drop-down {
                border: none;
            }
        """)
        self._populate_tones()
        row2.addWidget(self.tone_combo)

        self.reload_config_btn = QPushButton("⟳ Reload")
        self.reload_config_btn.setFont(QFont("Sans", 9))
        self.reload_config_btn.setToolTip("Reload prompts.yaml config")
        self.reload_config_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(108, 117, 125, 200);
                color: white;
                border: none;
                border-radius: 4px;
                padding: 3px 10px;
            }
            QPushButton:hover {
                background-color: rgba(90, 98, 104, 220);
            }
        """)
        self.reload_config_btn.clicked.connect(self._on_reload_config)
        row2.addWidget(self.reload_config_btn)

        row2.addStretch()

        # License status indicator
        license_key = get_license_key()
        if license_key and len(license_key) > 8:
            key_display = license_key[:4] + "..." + license_key[-4:]
        elif license_key:
            key_display = "****"
        else:
            key_display = "None"
        self.license_status_label = QLabel(f"Key: {key_display}")
        self.license_status_label.setFont(QFont("Sans", 8))
        self.license_status_label.setStyleSheet("color: #28a745;" if license_key else "color: #dc3545;")
        row2.addWidget(self.license_status_label)

        self.deactivate_btn = QPushButton("Deactivate License")
        self.deactivate_btn.setFont(QFont("Sans", 9))
        self.deactivate_btn.setToolTip("Deactivate license on this machine and free it for another device")
        self.deactivate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.deactivate_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(220, 53, 69, 180);
                color: white;
                border: none;
                border-radius: 4px;
                padding: 3px 10px;
            }
            QPushButton:hover {
                background-color: rgba(200, 35, 51, 210);
            }
            QPushButton:disabled {
                background-color: rgba(180, 180, 180, 150);
                color: #e0e0e0;
            }
        """)
        self.deactivate_btn.clicked.connect(self._deactivate_license)
        row2.addWidget(self.deactivate_btn)

        settings_outer.addLayout(row2)

        # Row 3: Config folder shortcut
        row3 = QHBoxLayout()
        row3.setSpacing(8)

        config_info = QLabel(f"Config: {get_config_dir()}")
        config_info.setFont(QFont("Sans", 8))
        config_info.setStyleSheet("color: #888888;")
        config_info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row3.addWidget(config_info, stretch=1)

        open_config_btn = QPushButton("📂 Open Config Folder")
        open_config_btn.setFont(QFont("Sans", 9))
        open_config_btn.setToolTip("Open folder containing prompts.yaml and .env")
        open_config_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(108, 117, 125, 200);
                color: white;
                border: none;
                border-radius: 4px;
                padding: 3px 10px;
            }
            QPushButton:hover {
                background-color: rgba(90, 98, 104, 220);
            }
        """)
        open_config_btn.clicked.connect(self._open_config_folder)
        row3.addWidget(open_config_btn)

        settings_outer.addLayout(row3)

        main_layout.addWidget(self.settings_panel)

        # ═══════════════════════════════════════════════════════
        # MAIN CONTENT AREA (horizontal splitter)
        # ═══════════════════════════════════════════════════════
        self.content_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.content_splitter.setStyleSheet("""
            QSplitter::handle:horizontal {
                width: 4px;
                background-color: #e0e0e0;
            }
        """)
        self.content_splitter.setChildrenCollapsible(False)

        # --- Left pane: Q&A History ---
        history_widget = QWidget()
        history_widget.setStyleSheet("background-color: rgba(248, 249, 250, 220);")
        history_outer = QVBoxLayout(history_widget)
        history_outer.setContentsMargins(8, 8, 4, 8)
        history_outer.setSpacing(6)

        history_header = QLabel("Q&A History")
        history_header.setFont(QFont("Sans", 10, QFont.Weight.Bold))
        history_header.setStyleSheet("color: #555555;")
        history_outer.addWidget(history_header)

        self.history_scroll = QScrollArea()
        self.history_scroll.setWidgetResizable(True)
        self.history_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.history_scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
        """)

        self.history_container = QWidget()
        self.history_container.setStyleSheet("background: transparent;")
        self.history_vlayout = QVBoxLayout(self.history_container)
        self.history_vlayout.setContentsMargins(0, 0, 0, 0)
        self.history_vlayout.setSpacing(6)
        self.history_vlayout.addStretch()  # Push cards to top

        self.history_scroll.setWidget(self.history_container)
        history_outer.addWidget(self.history_scroll, stretch=1)

        self.content_splitter.addWidget(history_widget)

        # --- Right pane: Current Answer ---
        answer_widget = QWidget()
        answer_outer = QVBoxLayout(answer_widget)
        answer_outer.setContentsMargins(4, 8, 8, 8)
        answer_outer.setSpacing(6)

        self.question_display = QLabel("Waiting for question...")
        self.question_display.setFont(QFont("Sans", 11))
        self.question_display.setWordWrap(True)
        self.question_display.setStyleSheet("""
            QLabel {
                color: #444444;
                background-color: rgba(240, 244, 248, 200);
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        answer_outer.addWidget(self.question_display)

        self.answer_box = FitTextEdit(initial_font_size=16, min_font_size=10)
        self.answer_box.setPlaceholderText("Answer will appear here...")
        self.answer_box.setStyleSheet("""
            QTextEdit {
                background-color: rgba(255, 255, 255, 240);
                color: #222222;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 10px;
            }
        """)
        self.answer_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        answer_outer.addWidget(self.answer_box, stretch=1)

        self.content_splitter.addWidget(answer_widget)

        # Set initial splitter sizes (~25% history, ~75% answer)
        self.content_splitter.setSizes([220, 680])

        main_layout.addWidget(self.content_splitter, stretch=1)

        # ═══════════════════════════════════════════════════════
        # STATUS BAR (24px)
        # ═══════════════════════════════════════════════════════
        status_bar_frame = QFrame()
        status_bar_frame.setFixedHeight(24)
        status_bar_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(248, 249, 250, 240);
                border-top: 1px solid #ddd;
            }
        """)
        status_bar_layout = QHBoxLayout(status_bar_frame)
        status_bar_layout.setContentsMargins(10, 0, 10, 0)
        status_bar_layout.setSpacing(10)

        self.status_label = QLabel("Status: Initializing...")
        self.status_label.setFont(QFont("Sans", 9))
        self.status_label.setStyleSheet("color: #555555;")
        status_bar_layout.addWidget(self.status_label)

        status_bar_layout.addStretch()

        self.last_heard_label = QLabel("")
        self.last_heard_label.setFont(QFont("Sans", 8))
        self.last_heard_label.setStyleSheet("color: #999999;")
        status_bar_layout.addWidget(self.last_heard_label)

        main_layout.addWidget(status_bar_frame)

    def _populate_devices(self):
        """Populate device dropdown with available monitor devices."""
        self.device_combo.clear()

        try:
            # Temporarily create capture to list devices
            temp_capture = get_audio_capture()
            devices = temp_capture.list_devices()

            default_idx = 0
            for i, dev in enumerate(devices):
                # Shorten the name for display
                name = dev["name"]
                display_name = name
                if len(name) > 50:
                    display_name = "..." + name[-47:]

                status = dev["status"]
                label = f"[{status}] {display_name}"

                self.device_combo.addItem(label, name)

                # Prefer active/idle monitors
                if status in ("IDLE", "RUNNING") and ".monitor" in name:
                    default_idx = i

            if devices:
                self.device_combo.setCurrentIndex(default_idx)

        except Exception as e:
            self.device_combo.addItem(f"Error: {e}", None)

    def _populate_tones(self):
        """Populate tone dropdown with available tones from config."""
        self.tone_combo.clear()
        tones = get_available_tones()
        default_tone = get_default_tone()

        for tone in tones:
            self.tone_combo.addItem(tone.capitalize(), tone)

        # Set default tone as selected
        idx = self.tone_combo.findData(default_tone)
        if idx >= 0:
            self.tone_combo.setCurrentIndex(idx)

    def _on_reload_config(self):
        """Reload prompts config from YAML file."""
        reload_prompts_config()
        # Refresh tone dropdown
        current_tone = self.tone_combo.currentData()
        self._populate_tones()
        # Try to restore previous selection
        idx = self.tone_combo.findData(current_tone)
        if idx >= 0:
            self.tone_combo.setCurrentIndex(idx)
        # Update job context if changed in config
        default_job = get_default_job_context()
        if default_job and not self.job_context_input.text():
            self.job_context_input.setText(default_job)
        self.status_label.setText("Status: Config reloaded")

    def _connect_signals(self):
        """Connect thread-safe signals to UI updates."""
        self.signals.transcription_ready.connect(self._on_transcription_ready)
        self.signals.answer_token.connect(self._on_answer_token)
        self.signals.answer_done.connect(self._on_answer_done)
        self.signals.answer_clear.connect(self._on_answer_clear)
        self.signals.status_update.connect(self._on_status_update)
        self.signals.error_occurred.connect(self._on_error)
        self.signals.audio_level.connect(self._on_audio_level)
        # Auto-answer mode signals
        self.signals.state_changed.connect(self._on_state_changed)
        self.signals.last_heard_update.connect(self._on_last_heard_update)
        self.signals.queue_update.connect(self._on_queue_update)
        # Dual-pane answer signals
        self.signals.bullet_token.connect(self._on_bullet_token)
        self.signals.script_token.connect(self._on_script_token)
        self.signals.question_update.connect(self._on_question_update)
        self.signals.deactivation_result.connect(self._on_deactivation_result)

    def _set_buttons_enabled(self, enabled: bool):
        """Enable/disable control buttons."""
        self.listen_btn.setEnabled(enabled)
        self.test_btn.setEnabled(enabled)
        self.device_combo.setEnabled(enabled)

    def _toggle_settings(self):
        """Toggle visibility of the settings panel."""
        self.settings_panel.setVisible(not self.settings_panel.isVisible())

    def _open_config_folder(self):
        """Open the config folder in the system file explorer."""
        import os
        config_dir = str(get_config_dir())
        # Ensure prompts.yaml exists (creates default if missing)
        from config import load_prompts_config
        load_prompts_config()
        # Open in file explorer
        os.startfile(config_dir)

    # ─── Q&A History ──────────────────────────────────────

    def _save_current_to_history(self):
        """Save the current Q&A to history before switching to a new question."""
        if self._viewing_history:
            self._viewing_history = False
            return

        current_q = self.question_display.text()
        current_a = self.answer_box.toPlainText()

        if not current_q or current_q == "Waiting for question..." or not current_a:
            return

        entry = {"question": current_q, "answer": current_a}
        self.qa_history.append(entry)
        self._add_history_card(entry)

        # Keep only last 20 entries
        if len(self.qa_history) > 20:
            self.qa_history.pop(0)
            # Remove oldest card (last widget before the stretch)
            oldest_idx = self.history_vlayout.count() - 2
            if oldest_idx >= 0:
                item = self.history_vlayout.takeAt(oldest_idx)
                if item and item.widget():
                    item.widget().deleteLater()

    def _add_history_card(self, entry: dict):
        """Add a visual card to the Q&A history panel."""
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 220);
                border: 1px solid #e0e0e0;
                border-radius: 6px;
            }
            QFrame:hover {
                background-color: rgba(232, 244, 253, 220);
                border-color: #b8d4e8;
            }
        """)
        card.setCursor(Qt.CursorShape.PointingHandCursor)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(8, 6, 8, 6)
        card_layout.setSpacing(3)

        # Question text (bold, truncated)
        q_text = entry["question"]
        if len(q_text) > 100:
            q_text = q_text[:100] + "..."
        q_label = QLabel(q_text)
        q_label.setFont(QFont("Sans", 9, QFont.Weight.Bold))
        q_label.setStyleSheet("color: #333333; border: none; background: transparent;")
        q_label.setWordWrap(True)
        q_label.setMaximumHeight(40)
        q_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        card_layout.addWidget(q_label)

        # Answer preview (gray, truncated)
        a_text = entry["answer"]
        if len(a_text) > 120:
            a_text = a_text[:120] + "..."
        a_label = QLabel(a_text)
        a_label.setFont(QFont("Sans", 8))
        a_label.setStyleSheet("color: #888888; border: none; background: transparent;")
        a_label.setWordWrap(True)
        a_label.setMaximumHeight(45)
        a_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        card_layout.addWidget(a_label)

        # Click handler — capture entry reference directly
        card.mousePressEvent = lambda event, e=entry: self._show_history_entry(e)

        # Insert at top (newest first, before the stretch at the bottom)
        self.history_vlayout.insertWidget(0, card)

    def _show_history_entry(self, entry: dict):
        """Show a historical Q&A in the right pane."""
        self.question_display.setText(entry["question"])
        self.answer_box.clear()
        self.answer_box.reset_font()
        self.answer_box.setPlainText(entry["answer"])
        self.answer_box.finalize_content()
        self._viewing_history = True

    # ─── Device / Listening ───────────────────────────────

    def _on_device_changed(self):
        """Handle device selection change."""
        if self.is_listening:
            self._stop_listening()
        self._init_capture()

    def _on_listen_toggle(self):
        """Toggle listening state."""
        if self.is_listening:
            self._stop_listening()
        else:
            self._start_listening()

    def _start_listening(self):
        """Start continuous audio capture."""
        if not self.capture:
            return

        try:
            self.capture.start_capture()
            self.is_listening = True

            # Reset auto-answer state
            self.speech_start_time = None
            self.silence_start_time = None
            self.is_processing = False

            self.listen_btn.setText("⏹ Stop")
            self.listen_btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(217, 83, 79, 230);
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 0 14px;
                }
                QPushButton:hover {
                    background-color: rgba(201, 48, 44, 240);
                }
            """)
            self.answer_btn.setEnabled(True)
            self.test_btn.setEnabled(False)
            self.device_combo.setEnabled(False)

            self.status_label.setText("Status: Listening to system audio...")

            # Set initial state for auto-answer mode
            if self.auto_answer_enabled:
                self.signals.state_changed.emit(ListeningState.LISTENING)

            # Start level meter updates
            self.level_timer = QTimer()
            self.level_timer.timeout.connect(self._update_level)
            self.level_timer.start(100)  # Update every 100ms

        except Exception as e:
            self.signals.error_occurred.emit(str(e))

    def _stop_listening(self):
        """Stop audio capture."""
        if self.level_timer:
            self.level_timer.stop()
            self.level_timer = None

        self.is_listening = False
        self.level_bar.setValue(0)

        # Reset auto-answer state
        self.speech_start_time = None
        self.silence_start_time = None
        self.is_processing = False
        self.signals.state_changed.emit(ListeningState.IDLE)

        if self.capture:
            self.capture.stop_capture()

        self.listen_btn.setText("🎧 Listen")
        self.listen_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(74, 144, 217, 230);
                color: white;
                border: none;
                border-radius: 4px;
                padding: 0 14px;
            }
            QPushButton:hover {
                background-color: rgba(58, 123, 200, 240);
            }
            QPushButton:disabled {
                background-color: rgba(204, 204, 204, 200);
            }
        """)
        self.answer_btn.setEnabled(False)
        self.test_btn.setEnabled(True)
        self.device_combo.setEnabled(True)

        self.status_label.setText("Status: Ready")

    def _update_level(self):
        """Update audio level meter and handle auto-answer mode."""
        if not self.capture or not self.is_listening:
            return

        try:
            level = self.capture.get_audio_level()
        except Exception as e:
            # Audio device may have disconnected (headphones unplugged, etc.)
            # Try to recover by reinitializing the capture device.
            self.signals.error_occurred.emit(f"Audio device error: {e}")
            try:
                self._stop_listening()
                self._init_capture()
                self.signals.status_update.emit("Status: Audio device reconnected — click Listen to resume")
            except Exception:
                self.signals.status_update.emit("Status: Audio device lost — select a new device")
            return
        self.level_bar.setValue(int(level * 100))

        # Auto-answer mode processing
        if not self.auto_answer_enabled or self.is_processing:
            return

        import time
        current_time = time.time()
        is_speech = level > SILENCE_THRESHOLD

        if is_speech:
            # Speech detected
            self.silence_start_time = None

            if self.speech_start_time is None:
                # Speech just started
                self.speech_start_time = current_time
                self.signals.state_changed.emit(ListeningState.HEARING)
        else:
            # Silence detected
            if self.speech_start_time is not None:
                # We were hearing speech, now silence
                if self.silence_start_time is None:
                    self.silence_start_time = current_time
                else:
                    silence_duration = current_time - self.silence_start_time
                    speech_duration = self.silence_start_time - self.speech_start_time

                    if silence_duration >= SILENCE_DURATION:
                        # Silence threshold reached, check if speech was long enough
                        if speech_duration >= MIN_SPEECH_DURATION:
                            # Trigger auto-processing
                            self._trigger_auto_process()
                        else:
                            # Too short, reset
                            self.signals.state_changed.emit(ListeningState.LISTENING)

                        # Reset timing
                        self.speech_start_time = None
                        self.silence_start_time = None
            else:
                # No speech yet, ensure we show listening state
                if self.current_state != ListeningState.LISTENING:
                    self.signals.state_changed.emit(ListeningState.LISTENING)

    def _trigger_auto_process(self):
        """Trigger automatic transcription and classification."""
        if self.is_processing:
            return

        self.is_processing = True
        self.signals.state_changed.emit(ListeningState.PROCESSING)

        thread = threading.Thread(target=self._auto_process_audio, daemon=True)
        thread.start()

    def _auto_process_audio(self):
        """Background thread: auto-transcribe, classify, and optionally answer.

        RELIABILITY: This method is the core interview loop. Every code path
        must reset is_processing and restore state to LISTENING so the app
        can keep answering questions even after transient failures.
        """
        try:
            # Guard against capture being None (device disconnected)
            if self.capture is None:
                return

            # Get recent audio (last few seconds based on speech duration)
            audio = self.capture.get_last_n_seconds(10)

            if len(audio) == 0:
                return

            # Transcribe
            text = transcribe_audio(audio)

            if not text or not text.strip():
                return

            # Update last heard
            self.signals.last_heard_update.emit(text, "")

            # Classify if it's an interview question
            classification = classify_utterance(text, MIN_WORDS_FOR_CLASSIFICATION)

            if not classification["is_interview_question"]:
                self.signals.last_heard_update.emit(text, "ignored")
                return

            if classification["confidence"] < self.confidence_threshold:
                self.signals.last_heard_update.emit(text, "low_confidence")
                return

            # It's an interview question with sufficient confidence - generate answer
            self.signals.last_heard_update.emit(text, "answering")
            self.signals.state_changed.emit(ListeningState.GENERATING)

            # Use cleaned question from classifier
            question = classification.get("cleaned_question", text)
            self.signals.transcription_ready.emit(question)

            # Save old Q&A, set new question, then clear and generate
            self.signals.question_update.emit(question)
            self.signals.answer_clear.emit()
            self._generate_parallel(question)
            self.signals.answer_done.emit()

        except Exception as e:
            self.signals.error_occurred.emit(f"Auto-answer error: {e}")
        finally:
            # ALWAYS reset processing state so the loop can continue
            self.is_processing = False
            self.signals.state_changed.emit(ListeningState.LISTENING)

            # Check if there are queued questions
            if not self.question_queue.empty():
                self.signals.queue_update.emit(self.question_queue.qsize())

    def _on_get_answer(self):
        """Transcribe recent audio and generate answer."""
        if not self.capture or not self.is_listening:
            return

        self.answer_btn.setEnabled(False)
        self.listen_btn.setEnabled(False)

        # Process in background thread
        thread = threading.Thread(target=self._process_audio, daemon=True)
        thread.start()

    def _process_audio(self):
        """Background thread: transcribe and get answer."""
        try:
            # Get last 30 seconds of audio
            self.signals.status_update.emit("Status: Transcribing last 30 seconds...")
            audio = self.capture.get_last_n_seconds(30)

            if len(audio) == 0:
                self.signals.error_occurred.emit("No audio captured")
                return

            text = transcribe_audio(audio)

            if not text or not text.strip():
                self.signals.error_occurred.emit("No speech detected - is audio playing?")
                return

            self.signals.transcription_ready.emit(text)

            # Save old Q&A, set new question, then clear and generate
            self.signals.question_update.emit(text)
            self.signals.answer_clear.emit()

            self.signals.status_update.emit("Status: Generating answers...")
            self._generate_parallel(text)

            self.signals.answer_done.emit()

        except Exception as e:
            self.signals.error_occurred.emit(str(e))
        finally:
            # ALWAYS re-enable buttons so the user can retry
            self.signals.answer_done.emit()

    def _generate_parallel(self, question: str):
        """Generate bullet and script responses in parallel threads."""
        # Get settings from UI
        job_context = self.job_context_input.text().strip()
        tone = self.tone_combo.currentData() or "professional"

        def stream_bullets():
            try:
                for token in ask_bullet(question, job_context):
                    self.signals.bullet_token.emit(token)
            except Exception as e:
                self.signals.error_occurred.emit(f"Bullet generation error: {e}")

        def stream_script():
            try:
                for token in ask_script(question, job_context, tone):
                    self.signals.script_token.emit(token)
            except Exception as e:
                self.signals.error_occurred.emit(f"Script generation error: {e}")

        with ThreadPoolExecutor(max_workers=2) as executor:
            bullet_future = executor.submit(stream_bullets)
            script_future = executor.submit(stream_script)
            # Wait with timeout so a hung API call can't block forever.
            # 60s is generous — typical answer streams complete in 5-15s.
            try:
                bullet_future.result(timeout=60)
            except TimeoutError:
                self.signals.error_occurred.emit("Bullet generation timed out")
            except Exception:
                pass  # Already handled inside stream_bullets
            try:
                script_future.result(timeout=60)
            except TimeoutError:
                self.signals.error_occurred.emit("Script generation timed out")
            except Exception:
                pass  # Already handled inside stream_script

    def _on_test_audio(self):
        """Test audio capture for 3 seconds."""
        if not self.capture:
            return

        self._set_buttons_enabled(False)
        self.answer_box.clear()

        thread = threading.Thread(target=self._run_test, daemon=True)
        thread.start()

    def _run_test(self):
        """Background thread: run audio test."""
        import time

        try:
            self.signals.status_update.emit("Status: Testing audio (3 seconds)...")
            self.capture.start_capture()

            # Show levels for 3 seconds
            for _ in range(30):
                time.sleep(0.1)
                level = self.capture.get_audio_level()
                self.signals.audio_level.emit(level)

            self.signals.status_update.emit("Status: Transcribing test...")
            audio = self.capture.stop_capture()

            if len(audio) == 0:
                self.signals.error_occurred.emit("No audio captured - check device")
                return

            text = transcribe_audio(audio)

            if text:
                self.signals.transcription_ready.emit(f"[TEST] {text}")
                self.signals.status_update.emit("Status: Test complete - audio working!")
            else:
                self.signals.transcription_ready.emit("[TEST] (no speech detected)")
                self.signals.status_update.emit("Status: Test complete - no speech heard")

        except Exception as e:
            self.signals.error_occurred.emit(f"Test failed: {e}")
        finally:
            self.signals.answer_done.emit()

    # ─── Signal Handlers ──────────────────────────────────

    def _on_transcription_ready(self, text: str):
        """Show transcription result in status bar."""
        display = text[:80] + "..." if len(text) > 80 else text
        self.status_label.setText(f"Heard: {display}")

    def _on_answer_token(self, token: str):
        """Append token to answer box."""
        self.answer_box.moveCursor(QTextCursor.MoveOperation.End)
        self.answer_box.insertPlainText(token)

    def _on_answer_done(self):
        """Processing complete — append buffered bullets and finalize."""
        # Append bullet points below the script
        if self._bullet_buffer.strip():
            separator = "\n\n━━━━━━━━━━━━━━━━━━━━\n📌 Key Points:\n"
            self.answer_box.moveCursor(QTextCursor.MoveOperation.End)
            self.answer_box.insertPlainText(separator + self._bullet_buffer)

        self.answer_box.finalize_content()

        if self.is_listening:
            self.status_label.setText("Status: Listening to system audio...")
            self.answer_btn.setEnabled(True)
            self.listen_btn.setEnabled(True)
        else:
            self.status_label.setText("Status: Ready")
            self._set_buttons_enabled(True)
        self.level_bar.setValue(0)

    def _on_answer_clear(self):
        """Clear answer box and reset bullet buffer (thread-safe via signal)."""
        self.answer_box.clear()
        self.answer_box.reset_font()
        self._bullet_buffer = ""

    def _on_bullet_token(self, token: str):
        """Buffer bullet tokens (appended to answer_box when done)."""
        self._bullet_buffer += token

    def _on_script_token(self, token: str):
        """Append script token to answer_box (visible immediately)."""
        scrollbar = self.answer_box.verticalScrollBar()
        scroll_pos = scrollbar.value()
        self.answer_box.moveCursor(QTextCursor.MoveOperation.End)
        self.answer_box.insertPlainText(token)
        scrollbar.setValue(scroll_pos)

    def _on_question_update(self, text: str):
        """Save current Q&A to history, then display new question."""
        self._save_current_to_history()
        self.question_display.setText(text)
        self._viewing_history = False

    def _on_status_update(self, status: str):
        """Update status label."""
        self.status_label.setText(status)

    def _on_audio_level(self, level: float):
        """Update audio level from signal."""
        self.level_bar.setValue(int(level * 100))

    def _on_error(self, message: str):
        """Handle errors."""
        self.status_label.setText(f"Status: Error - {message}")
        if self.is_listening:
            self.answer_btn.setEnabled(True)
            self.listen_btn.setEnabled(True)
        else:
            self._set_buttons_enabled(True)
        self.level_bar.setValue(0)

    def _on_auto_mode_toggled(self, enabled: bool):
        """Handle auto-answer mode toggle."""
        self.auto_answer_enabled = enabled
        self.confidence_slider.setEnabled(enabled)

    def _on_confidence_changed(self, value: int):
        """Handle confidence slider change."""
        self.confidence_threshold = value / 100.0
        self.confidence_label.setText(f"{self.confidence_threshold:.2f}")

    def _on_state_changed(self, state: str):
        """Update toolbar state indicator."""
        self.current_state = state

        state_config = {
            ListeningState.IDLE: ("⚪", "Ready"),
            ListeningState.LISTENING: ("🔵", "Listening..."),
            ListeningState.HEARING: ("🟢", "Hearing speech..."),
            ListeningState.PROCESSING: ("🟡", "Processing..."),
            ListeningState.GENERATING: ("🟣", "Generating..."),
        }

        indicator, text = state_config.get(state, ("⚪", "Unknown"))
        self.state_indicator.setText(indicator)
        self.state_text.setText(text)

    def _on_last_heard_update(self, text: str, status: str):
        """Show last-heard info in the status bar."""
        display = text[:60] + "..." if len(text) > 60 else text
        if status == "ignored":
            self.last_heard_label.setText(f"Ignored: {display}")
            self.last_heard_label.setStyleSheet("color: #999999;")
        elif status == "answering":
            self.last_heard_label.setText("Answering...")
            self.last_heard_label.setStyleSheet("color: #4a90d9;")
        elif status == "low_confidence":
            self.last_heard_label.setText(f"Low conf: {display}")
            self.last_heard_label.setStyleSheet("color: #d9a54a;")
        else:
            self.last_heard_label.setText(f"Heard: {display}")
            self.last_heard_label.setStyleSheet("color: #666666;")

    def _on_queue_update(self, count: int):
        """Update queue indicator."""
        if count > 0:
            self.queue_label.setText(f"📋 {count}")
        else:
            self.queue_label.setText("")

    def _deactivate_license(self):
        """Deactivate license — friendly confirmation, then background network call."""
        # Show current key (masked) so user knows what they're deactivating
        license_key = get_license_key()
        if not license_key:
            QMessageBox.information(
                self, "No License",
                "No license key is currently active.\n\n"
                "You can activate one from the startup screen."
            )
            return

        masked = license_key[:4] + "..." + license_key[-4:] if len(license_key) > 8 else "****"
        reply = QMessageBox.question(
            self, "Deactivate License",
            f"Current key: {masked}\n\n"
            "Deactivating frees this key so you can use it\n"
            "on another machine.\n\n"
            "You'll return to the activation screen.\n\n"
            "Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.deactivate_btn.setEnabled(False)
        self.deactivate_btn.setText("Deactivating...")
        self.status_label.setText("Status: Deactivating license...")

        thread = threading.Thread(
            target=self._deactivate_in_background, args=(license_key,), daemon=True
        )
        thread.start()

    def _deactivate_in_background(self, license_key: str):
        """Background thread: call license deactivation API."""
        proxy_url = get_proxy_url()
        hw_id = get_hardware_id()
        try:
            base = proxy_url.rsplit("/v1", 1)[0]
            resp = requests.post(
                f"{base}/v1/license/deactivate",
                json={"license_key": license_key, "hardware_id": hw_id},
                timeout=10,
            )
            if resp.status_code == 200:
                clear_license_key()
                self.signals.deactivation_result.emit(True, "License deactivated successfully.")
            else:
                error = resp.json().get("detail", {}).get("error", {})
                msg = error.get("message", "Deactivation failed. Please try again.")
                self.signals.deactivation_result.emit(False, msg)
        except requests.ConnectionError:
            # Server unreachable — still clear locally so user isn't stuck
            clear_license_key()
            self.signals.deactivation_result.emit(
                True,
                "License cleared locally. Server was unreachable,\n"
                "so the remote deactivation will happen automatically."
            )
        except Exception as e:
            self.signals.deactivation_result.emit(False, f"Connection error: {e}")

    def _on_deactivation_result(self, success: bool, message: str):
        """Handle deactivation result on the main thread."""
        self.deactivate_btn.setEnabled(True)
        self.deactivate_btn.setText("Deactivate")
        if success:
            # Stop listening cleanly before switching screens
            if self.is_listening:
                self._stop_listening()
            QMessageBox.information(self, "License Deactivated", message)
            self.license_deactivated.emit()
        else:
            QMessageBox.warning(self, "Deactivation Failed", message)
            self.status_label.setText("Status: Ready")

    def closeEvent(self, event):
        """Clean up on close."""
        if self.is_listening:
            self._stop_listening()
        event.accept()


class AstraApp:
    """Application controller managing screen transitions."""

    def __init__(self):
        self.startup_screen = StartupScreen()
        self.activation_screen = LicenseActivationScreen()
        self.session_window = None  # Lazy create

        # Connect startup screen signals
        self.startup_screen.ingest_requested.connect(self._on_ingest)
        self.startup_screen.start_session_requested.connect(self._on_start_session)

        # Connect activation screen signals
        self.activation_screen.activated.connect(self._on_license_activated)
        self.activation_screen.skipped.connect(self._on_license_skipped)

        # Subprocess for background ingestion (crash-isolated from GUI)
        self._ingest_process = None

    def _on_license_activated(self):
        """Handle successful license activation."""
        self.activation_screen.hide()
        self.startup_screen.show()

    def _on_license_skipped(self):
        """Handle continue without license."""
        self.activation_screen.hide()
        self.startup_screen.show()

    def _on_license_deactivated(self):
        """Handle license deactivation — return to activation screen."""
        if self.session_window is not None:
            self.session_window.hide()
        self.startup_screen.hide()
        self.activation_screen.reset()
        self.activation_screen.show()

    def show(self):
        """Show the appropriate screen based on license state."""
        if get_license_key():
            self.startup_screen.show()
        else:
            self.activation_screen.show()

    def _on_ingest(self):
        """Handle document ingestion request — opens a folder picker dialog.

        Ingestion runs as a SUBPROCESS (not a thread) for crash isolation.
        ChromaDB's hnswlib C extension can segfault in PyInstaller frozen exes
        (GitHub #3947). Running in a subprocess means a segfault only kills the
        child process — the GUI survives and can report the error to the user.

        The subprocess uses main.py --ingest FOLDER --json-progress, which emits
        JSON lines to stdout for progress reporting.
        """
        from PyQt6.QtWidgets import QFileDialog

        # Open folder picker starting from user's Documents directory
        default_dir = os.path.expanduser("~/Documents")
        documents_path = QFileDialog.getExistingDirectory(
            self.startup_screen, "Select folder with documents to ingest", default_dir
        )

        # User cancelled the dialog
        if not documents_path:
            return

        # Disable buttons during ingestion
        self.startup_screen.set_buttons_enabled(False)
        self.startup_screen.set_status("Scanning documents...")
        self.startup_screen.show_progress_bar(True)
        self.startup_screen.set_progress(0, 100)

        # Create ingestion signals for thread-safe UI updates
        self._ingestion_signals = IngestionSignals()
        self._ingestion_signals.progress.connect(self._on_ingestion_progress)
        self._ingestion_signals.complete.connect(self._on_ingestion_complete)

        # Build the subprocess command.
        # In frozen exe: sys.executable is Astra.exe, which routes --ingest to ingest.py
        # In dev mode: sys.executable is python.exe, run main.py --ingest
        if getattr(sys, 'frozen', False):
            cmd = [sys.executable, "--ingest", documents_path, "--json-progress"]
        else:
            main_py = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
            cmd = [sys.executable, main_py, "--ingest", documents_path, "--json-progress"]

        # Launch ingestion as a subprocess with stdout pipe for JSON progress.
        # CREATE_NO_WINDOW prevents a console flash on Windows.
        # The subprocess is fully isolated — if hnswlib segfaults, only the
        # child process dies; the GUI continues running and detects the crash.
        self._ingest_completed = False
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NO_WINDOW
        try:
            self._ingest_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=creationflags,
            )
        except Exception as e:
            self.startup_screen.set_buttons_enabled(True)
            self.startup_screen.show_progress_bar(False)
            self.startup_screen.set_status(f"Failed to start ingestion: {e}", is_error=True)
            return

        # Reader thread: reads JSON lines from subprocess stdout and emits signals.
        # This thread does NOT run ChromaDB code — it just reads a pipe — so it
        # cannot segfault. If the subprocess dies, the pipe closes and readline()
        # returns empty, ending the loop cleanly.
        self._ingest_reader = threading.Thread(
            target=self._read_ingest_output,
            daemon=True,
        )
        self._ingest_reader.start()

        # Watchdog: periodically check if subprocess died without emitting result.
        # Unlike the old thread-based watchdog, this WORKS because the subprocess
        # crash does not kill the GUI process.
        self._ingest_watchdog = QTimer()
        self._ingest_watchdog.timeout.connect(self._check_ingest_process)
        self._ingest_watchdog.start(1000)  # Check every second

    def _read_ingest_output(self):
        """Reader thread: parse JSON lines from ingestion subprocess stdout.

        Each line from the subprocess is a JSON object with progress info or the
        final result. This thread emits Qt signals to update the UI.

        If the subprocess crashes (segfault), the pipe breaks and readline()
        returns b'', ending the loop. The watchdog timer detects the dead process.
        """
        proc = self._ingest_process
        if proc is None or proc.stdout is None:
            return

        last_result = None
        try:
            for raw_line in proc.stdout:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                stage = data.get("stage", "")

                if stage == "result":
                    # Final result line — emit completion
                    last_result = data
                    self._ingestion_signals.complete.emit({
                        "success": data.get("success", False),
                        "total_files": data.get("total_files", 0),
                        "total_chunks": data.get("total_chunks", 0),
                        "errors": data.get("errors", []),
                    })
                else:
                    # Progress update
                    self._ingestion_signals.progress.emit(data)
        except Exception:
            pass  # Pipe broken or other IO error — watchdog handles cleanup

        # Wait for process to fully exit
        try:
            proc.wait(timeout=10)
        except Exception:
            pass

        # If we never got a result line, the subprocess crashed
        if last_result is None and not self._ingest_completed:
            exit_code = proc.returncode if proc.returncode is not None else -1
            # Read stderr for crash details
            stderr_text = ""
            try:
                if proc.stderr:
                    stderr_text = proc.stderr.read().decode("utf-8", errors="replace").strip()
            except Exception:
                pass

            error_msg = (
                f"Ingestion process crashed (exit code {exit_code}). "
                "This is typically caused by a native code error in ChromaDB's "
                "vector index. Check ingest_crash.log next to the application."
            )
            if stderr_text:
                error_msg += f"\n\nDetails: {stderr_text[:500]}"

            self._ingestion_signals.complete.emit({
                "success": False,
                "total_files": 0,
                "total_chunks": 0,
                "errors": [error_msg],
            })

    def _check_ingest_process(self):
        """Watchdog: detect if ingestion subprocess died.

        Unlike the old thread-based approach, this WORKS because the subprocess
        runs in a separate process. A segfault in hnswlib kills only the child —
        the GUI process (and this timer) keep running.
        """
        if self._ingest_completed:
            # Normal completion — stop watching
            self._ingest_watchdog.stop()
            return

        if self._ingest_process is not None:
            exit_code = self._ingest_process.poll()
            if exit_code is not None and not self._ingest_completed:
                # Process exited — the reader thread should handle emitting
                # the completion signal. Give it a moment, then check again.
                # If reader thread already emitted, _ingest_completed will be True
                # on next watchdog tick.
                pass

    def _on_ingestion_progress(self, info: dict):
        """Handle progress updates from ingestion subprocess."""
        stage = info.get("stage", "")
        total_files = info.get("total_files", 0)
        current_index = info.get("current_file_index", 0)
        current_name = info.get("current_file_name", "")

        if stage == "scanning":
            self.startup_screen.set_status(f"Found {total_files} files")
            self.startup_screen.set_progress(0, total_files)
        elif stage == "processing":
            display_index = current_index + 1
            self.startup_screen.set_status(
                f"Processing {current_name} ({display_index} of {total_files})"
            )
            self.startup_screen.set_progress(display_index, total_files)

    def _on_ingestion_complete(self, result: dict):
        """Handle ingestion completion."""
        self._ingest_completed = True
        if hasattr(self, '_ingest_watchdog') and self._ingest_watchdog.isActive():
            self._ingest_watchdog.stop()
        self.startup_screen.set_buttons_enabled(True)
        self.startup_screen.show_progress_bar(False)

        success = result.get("success", False)
        total_chunks = result.get("total_chunks", 0)
        errors = result.get("errors", [])

        if success and not errors:
            message = f"Ingestion complete! {total_chunks} chunks added."
            self.startup_screen.set_status(message)
            QMessageBox.information(
                self.startup_screen,
                "Ingestion Complete",
                message
            )
        else:
            error_msg = errors[0] if errors else "Unknown error"
            self.startup_screen.set_status(f"Error: {error_msg}", is_error=True)
            QMessageBox.warning(
                self.startup_screen,
                "Ingestion Error",
                error_msg
            )

    def _on_start_session(self):
        """Handle start session request."""
        # Check license key -- show activation screen if missing
        if not get_license_key():
            self.startup_screen.hide()
            # Re-connect activated signal to proceed to session after activation
            try:
                self.activation_screen.activated.disconnect()
            except TypeError:
                pass
            self.activation_screen.activated.connect(self._on_license_activated_start_session)
            self.activation_screen.show()
            return

        # Create session window if not exists
        self._ensure_session_window()

        # Hide startup, show session
        self.startup_screen.hide()
        self.session_window.show()

    def _ensure_session_window(self):
        """Create the session window if it doesn't exist yet, and wire signals."""
        if self.session_window is None:
            self.session_window = AstraWindow()
            self.session_window.license_deactivated.connect(self._on_license_deactivated)

    def _on_license_activated_start_session(self):
        """Handle activation from start session flow -- go directly to session."""
        self.activation_screen.hide()
        # Restore default activated signal connection
        try:
            self.activation_screen.activated.disconnect()
        except TypeError:
            pass
        self.activation_screen.activated.connect(self._on_license_activated)

        # Create session window if not exists
        self._ensure_session_window()

        self.session_window.show()


TEST_UTTERANCES = [
    ("Tell me about a time you led a difficult project", True),
    ("Thanks for joining us today", False),
    ("What's your experience with distributed systems", True),
    ("That's a great answer", False),
    ("Describe a situation where you had to deal with conflict", True),
    ("Can you hear me okay", False),
    ("How would you approach debugging a production issue", True),
    ("Let me tell you about our engineering culture", False),
    ("Walk me through your thought process when designing a new feature", True),
    ("Interesting", False),
    ("Give me an example of when you had to learn something quickly", True),
    ("Let's move on to the next topic", False),
]


def run_classifier_test():
    """Test the interview question classifier."""
    print("=" * 60)
    print("Interview Question Classifier Test")
    print("=" * 60)
    print()

    correct = 0
    total = len(TEST_UTTERANCES)

    for utterance, expected in TEST_UTTERANCES:
        result = classify_utterance(utterance)
        is_question = result["is_interview_question"]
        confidence = result["confidence"]
        q_type = result["question_type"]

        status = "✓" if is_question == expected else "✗"
        if is_question == expected:
            correct += 1

        print(f"{status} \"{utterance[:50]}{'...' if len(utterance) > 50 else ''}\"")
        print(f"   Expected: {'Question' if expected else 'Not question'}")
        print(f"   Got: {'Question' if is_question else 'Not question'} "
              f"(type={q_type}, confidence={confidence:.2f})")
        print()

    print("=" * 60)
    print(f"Results: {correct}/{total} correct ({100*correct/total:.0f}%)")
    print("=" * 60)

    return correct == total


def main():
    parser = argparse.ArgumentParser(description="Astra Interview Copilot")
    parser.add_argument(
        "--test-classifier",
        action="store_true",
        help="Run classifier test instead of GUI"
    )
    args = parser.parse_args()

    if args.test_classifier:
        success = run_classifier_test()
        sys.exit(0 if success else 1)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = AstraWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
