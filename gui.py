#!/usr/bin/env python3
"""
Astra Interview Copilot - PyQt6 GUI
Captures system audio and provides AI-powered interview answers.
"""

import sys
import threading
import argparse
from queue import Queue
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QComboBox,
    QProgressBar,
    QCheckBox,
    QSlider,
    QFrame,
    QMessageBox,
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QTimer
from PyQt6.QtGui import QFont, QTextCursor

from transcriber import transcribe_audio
from audio_capture import get_audio_capture
from rag import ask, classify_utterance
from config import (
    SILENCE_THRESHOLD,
    SILENCE_DURATION,
    MIN_SPEECH_DURATION,
    CLASSIFICATION_CONFIDENCE,
    MIN_WORDS_FOR_CLASSIFICATION,
    AUDIO_SAMPLE_RATE,
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
    status_update = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    audio_level = pyqtSignal(float)
    # New signals for auto-answer mode
    state_changed = pyqtSignal(str)           # ListeningState value
    last_heard_update = pyqtSignal(str, str)  # text, status ("ignored"/"answering"/"")
    queue_update = pyqtSignal(int)            # Number of queued questions


class IngestionSignals(QObject):
    """Signals for document ingestion progress."""
    progress = pyqtSignal(dict)  # Progress info dict
    complete = pyqtSignal(dict)  # Result summary dict


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
            "• Ingest Documents - Scan the documents/ folder\n"
            "  to build your knowledge base\n\n"
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


class AstraWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.capture = None
        self.signals = SignalBridge()
        self.is_listening = False
        self.level_timer = None

        # Auto-answer mode state
        self.auto_answer_enabled = False
        self.current_state = ListeningState.IDLE
        self.speech_start_time = None
        self.silence_start_time = None
        self.question_queue = Queue()
        self.is_processing = False
        self.confidence_threshold = CLASSIFICATION_CONFIDENCE

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
        self.setFixedSize(500, 750)

        # Central widget and layout
        central = QWidget()
        central.setStyleSheet("background-color: #ffffff;")
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)

        # Title
        title = QLabel("Astra Interview Copilot")
        title.setFont(QFont("Sans", 14, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color: #222222;")
        layout.addWidget(title)

        # Audio source selection
        source_layout = QHBoxLayout()
        source_label = QLabel("Audio Source:")
        source_label.setFont(QFont("Sans", 10))
        source_label.setStyleSheet("color: #333333;")
        source_layout.addWidget(source_label)

        self.device_combo = QComboBox()
        self.device_combo.setStyleSheet("""
            QComboBox {
                background-color: #f5f5f5;
                color: #333333;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 5px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: #ffffff;
                color: #333333;
                selection-background-color: #4a90d9;
            }
        """)
        self._populate_devices()
        self.device_combo.currentIndexChanged.connect(self._on_device_changed)
        source_layout.addWidget(self.device_combo, stretch=1)

        self.test_btn = QPushButton("Test")
        self.test_btn.setFont(QFont("Sans", 10))
        self.test_btn.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 5px 15px;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.test_btn.clicked.connect(self._on_test_audio)
        source_layout.addWidget(self.test_btn)

        layout.addLayout(source_layout)

        # Auto-Answer Mode section
        auto_frame = QFrame()
        auto_frame.setStyleSheet("""
            QFrame {
                background-color: #f0f4f8;
                border: 1px solid #ddd;
                border-radius: 6px;
                padding: 5px;
            }
        """)
        auto_layout = QHBoxLayout(auto_frame)
        auto_layout.setContentsMargins(10, 5, 10, 5)

        self.auto_checkbox = QCheckBox("🤖 Auto-Answer Mode")
        self.auto_checkbox.setFont(QFont("Sans", 10))
        self.auto_checkbox.setStyleSheet("color: #333333;")
        self.auto_checkbox.toggled.connect(self._on_auto_mode_toggled)
        auto_layout.addWidget(self.auto_checkbox)

        auto_layout.addStretch()

        conf_label = QLabel("Confidence:")
        conf_label.setFont(QFont("Sans", 9))
        conf_label.setStyleSheet("color: #555555;")
        auto_layout.addWidget(conf_label)

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
        auto_layout.addWidget(self.confidence_slider)

        self.confidence_label = QLabel(f"{CLASSIFICATION_CONFIDENCE:.2f}")
        self.confidence_label.setFont(QFont("Sans", 9))
        self.confidence_label.setStyleSheet("color: #555555;")
        self.confidence_label.setFixedWidth(30)
        auto_layout.addWidget(self.confidence_label)

        layout.addWidget(auto_frame)

        # State indicator with color
        self.state_frame = QFrame()
        self.state_frame.setStyleSheet("""
            QFrame {
                background-color: #e8f4fd;
                border: 1px solid #b8d4e8;
                border-radius: 6px;
            }
        """)
        state_layout = QHBoxLayout(self.state_frame)
        state_layout.setContentsMargins(10, 8, 10, 8)

        self.state_indicator = QLabel("🔵")
        self.state_indicator.setFont(QFont("Sans", 14))
        state_layout.addWidget(self.state_indicator)

        self.state_text = QLabel("Ready")
        self.state_text.setFont(QFont("Sans", 11))
        self.state_text.setStyleSheet("color: #333333;")
        state_layout.addWidget(self.state_text)

        state_layout.addStretch()

        self.queue_label = QLabel("")
        self.queue_label.setFont(QFont("Sans", 9))
        self.queue_label.setStyleSheet("color: #666666;")
        state_layout.addWidget(self.queue_label)

        layout.addWidget(self.state_frame)

        # Audio level meter
        level_layout = QHBoxLayout()
        level_label = QLabel("Level:")
        level_label.setFont(QFont("Sans", 10))
        level_label.setStyleSheet("color: #333333;")
        level_layout.addWidget(level_label)

        self.level_bar = QProgressBar()
        self.level_bar.setRange(0, 100)
        self.level_bar.setValue(0)
        self.level_bar.setTextVisible(False)
        self.level_bar.setMaximumHeight(20)
        self.level_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #ddd;
                border-radius: 4px;
                background-color: #f5f5f5;
            }
            QProgressBar::chunk {
                background-color: #28a745;
                border-radius: 3px;
            }
        """)
        level_layout.addWidget(self.level_bar, stretch=1)

        layout.addLayout(level_layout)

        # Control buttons
        btn_layout = QHBoxLayout()

        self.listen_btn = QPushButton("🎧 Start Listening")
        self.listen_btn.setFont(QFont("Sans", 12))
        self.listen_btn.setMinimumHeight(50)
        self.listen_btn.setStyleSheet("""
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
        self.listen_btn.clicked.connect(self._on_listen_toggle)
        btn_layout.addWidget(self.listen_btn)

        self.answer_btn = QPushButton("💡 Get Answer")
        self.answer_btn.setFont(QFont("Sans", 12))
        self.answer_btn.setMinimumHeight(50)
        self.answer_btn.setEnabled(False)
        self.answer_btn.setStyleSheet("""
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
        self.answer_btn.clicked.connect(self._on_get_answer)
        btn_layout.addWidget(self.answer_btn)

        layout.addLayout(btn_layout)

        # Last heard section (for auto-mode)
        last_heard_layout = QHBoxLayout()
        last_heard_label = QLabel("Last heard:")
        last_heard_label.setFont(QFont("Sans", 9))
        last_heard_label.setStyleSheet("color: #666666;")
        last_heard_layout.addWidget(last_heard_label)

        self.last_heard_status = QLabel("")
        self.last_heard_status.setFont(QFont("Sans", 9))
        self.last_heard_status.setStyleSheet("color: #888888; font-style: italic;")
        last_heard_layout.addWidget(self.last_heard_status)
        last_heard_layout.addStretch()

        layout.addLayout(last_heard_layout)

        self.last_heard_box = QTextEdit()
        self.last_heard_box.setReadOnly(True)
        self.last_heard_box.setFont(QFont("Sans", 9))
        self.last_heard_box.setMaximumHeight(50)
        self.last_heard_box.setPlaceholderText("(waiting for speech...)")
        self.last_heard_box.setStyleSheet("""
            QTextEdit {
                background-color: #fafafa;
                color: #555555;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                padding: 4px;
            }
        """)
        layout.addWidget(self.last_heard_box)

        # Transcription section (manual mode)
        trans_label = QLabel("Question:")
        trans_label.setFont(QFont("Sans", 10))
        trans_label.setStyleSheet("color: #333333;")
        layout.addWidget(trans_label)

        self.transcription_box = QTextEdit()
        self.transcription_box.setReadOnly(True)
        self.transcription_box.setFont(QFont("Sans", 11))
        self.transcription_box.setMaximumHeight(80)
        self.transcription_box.setPlaceholderText("(transcription appears here)")
        self.transcription_box.setStyleSheet("""
            QTextEdit {
                background-color: #f5f5f5;
                color: #333333;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 5px;
            }
        """)
        layout.addWidget(self.transcription_box)

        # Answer section
        answer_label = QLabel("Answer:")
        answer_label.setFont(QFont("Sans", 10))
        answer_label.setStyleSheet("color: #333333;")
        layout.addWidget(answer_label)

        self.answer_box = QTextEdit()
        self.answer_box.setReadOnly(True)
        self.answer_box.setFont(QFont("Sans", 16))
        self.answer_box.setPlaceholderText("• bullet point 1\n• bullet point 2\n• bullet point 3")
        self.answer_box.setStyleSheet("""
            QTextEdit {
                background-color: #f9f9f9;
                color: #222222;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        layout.addWidget(self.answer_box, stretch=1)

        # Status bar
        self.status_label = QLabel("Status: Initializing...")
        self.status_label.setFont(QFont("Sans", 10))
        self.status_label.setStyleSheet("color: #555555; background-color: transparent;")
        layout.addWidget(self.status_label)

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

    def _connect_signals(self):
        """Connect thread-safe signals to UI updates."""
        self.signals.transcription_ready.connect(self._on_transcription_ready)
        self.signals.answer_token.connect(self._on_answer_token)
        self.signals.answer_done.connect(self._on_answer_done)
        self.signals.status_update.connect(self._on_status_update)
        self.signals.error_occurred.connect(self._on_error)
        self.signals.audio_level.connect(self._on_audio_level)
        # Auto-answer mode signals
        self.signals.state_changed.connect(self._on_state_changed)
        self.signals.last_heard_update.connect(self._on_last_heard_update)
        self.signals.queue_update.connect(self._on_queue_update)

    def _set_buttons_enabled(self, enabled: bool):
        """Enable/disable control buttons."""
        self.listen_btn.setEnabled(enabled)
        self.test_btn.setEnabled(enabled)
        self.device_combo.setEnabled(enabled)

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

            self.listen_btn.setText("⏹ Stop Listening")
            self.listen_btn.setStyleSheet("""
                QPushButton {
                    background-color: #d9534f;
                    color: white;
                    border: none;
                    border-radius: 8px;
                }
                QPushButton:hover {
                    background-color: #c9302c;
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

        self.listen_btn.setText("🎧 Start Listening")
        self.listen_btn.setStyleSheet("""
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
        self.answer_btn.setEnabled(False)
        self.test_btn.setEnabled(True)
        self.device_combo.setEnabled(True)

        self.status_label.setText("Status: Ready")

    def _update_level(self):
        """Update audio level meter and handle auto-answer mode."""
        if not self.capture or not self.is_listening:
            return

        level = self.capture.get_audio_level()
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
        """Background thread: auto-transcribe, classify, and optionally answer."""
        try:
            # Get recent audio (last few seconds based on speech duration)
            audio = self.capture.get_last_n_seconds(10)

            if len(audio) == 0:
                self.signals.state_changed.emit(ListeningState.LISTENING)
                self.is_processing = False
                return

            # Transcribe
            text = transcribe_audio(audio)

            if not text or not text.strip():
                self.signals.state_changed.emit(ListeningState.LISTENING)
                self.is_processing = False
                return

            # Update last heard
            self.signals.last_heard_update.emit(text, "")

            # Classify if it's an interview question
            classification = classify_utterance(text, MIN_WORDS_FOR_CLASSIFICATION)

            if not classification["is_interview_question"]:
                self.signals.last_heard_update.emit(text, "ignored")
                self.signals.state_changed.emit(ListeningState.LISTENING)
                self.is_processing = False
                return

            if classification["confidence"] < self.confidence_threshold:
                self.signals.last_heard_update.emit(text, "low_confidence")
                self.signals.state_changed.emit(ListeningState.LISTENING)
                self.is_processing = False
                return

            # It's an interview question with sufficient confidence - generate answer
            self.signals.last_heard_update.emit(text, "answering")
            self.signals.state_changed.emit(ListeningState.GENERATING)

            # Use cleaned question from classifier
            question = classification.get("cleaned_question", text)
            self.signals.transcription_ready.emit(question)

            # Clear answer box and generate
            self.answer_box.clear()
            for token in ask(question):
                self.signals.answer_token.emit(token)

            self.signals.state_changed.emit(ListeningState.LISTENING)

        except Exception as e:
            self.signals.error_occurred.emit(str(e))
            self.signals.state_changed.emit(ListeningState.LISTENING)
        finally:
            self.is_processing = False

            # Check if there are queued questions
            if not self.question_queue.empty():
                self.signals.queue_update.emit(self.question_queue.qsize())
                # Process next in queue (could implement this later)

    def _on_get_answer(self):
        """Transcribe recent audio and generate answer."""
        if not self.capture or not self.is_listening:
            return

        self.transcription_box.clear()
        self.answer_box.clear()
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

            # Get RAG answer
            self.signals.status_update.emit("Status: Generating answer...")
            for token in ask(text):
                self.signals.answer_token.emit(token)

            self.signals.answer_done.emit()

        except Exception as e:
            self.signals.error_occurred.emit(str(e))

    def _on_test_audio(self):
        """Test audio capture for 3 seconds."""
        if not self.capture:
            return

        self._set_buttons_enabled(False)
        self.transcription_box.clear()
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

    def _on_transcription_ready(self, text: str):
        """Update transcription box."""
        self.transcription_box.setText(text)

    def _on_answer_token(self, token: str):
        """Append token to answer box."""
        self.answer_box.moveCursor(QTextCursor.MoveOperation.End)
        self.answer_box.insertPlainText(token)

    def _on_answer_done(self):
        """Processing complete."""
        if self.is_listening:
            self.status_label.setText("Status: Listening to system audio...")
            self.answer_btn.setEnabled(True)
            self.listen_btn.setEnabled(True)
        else:
            self.status_label.setText("Status: Ready")
            self._set_buttons_enabled(True)
        self.level_bar.setValue(0)

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
        if enabled:
            self.state_frame.setStyleSheet("""
                QFrame {
                    background-color: #e8f4fd;
                    border: 1px solid #4a90d9;
                    border-radius: 6px;
                }
            """)
        else:
            self.state_frame.setStyleSheet("""
                QFrame {
                    background-color: #f5f5f5;
                    border: 1px solid #ddd;
                    border-radius: 6px;
                }
            """)

    def _on_confidence_changed(self, value: int):
        """Handle confidence slider change."""
        self.confidence_threshold = value / 100.0
        self.confidence_label.setText(f"{self.confidence_threshold:.2f}")

    def _on_state_changed(self, state: str):
        """Update UI based on listening state."""
        self.current_state = state

        state_config = {
            ListeningState.IDLE: ("⚪", "Ready", "#f5f5f5", "#ddd"),
            ListeningState.LISTENING: ("🔵", "Listening...", "#e8f4fd", "#b8d4e8"),
            ListeningState.HEARING: ("🟢", "Hearing speech...", "#e8fde8", "#8ed98e"),
            ListeningState.PROCESSING: ("🟡", "Processing...", "#fdf8e8", "#d9c98e"),
            ListeningState.GENERATING: ("🟣", "Generating answer...", "#f4e8fd", "#c98ed9"),
        }

        indicator, text, bg_color, border_color = state_config.get(
            state, ("⚪", "Unknown", "#f5f5f5", "#ddd")
        )

        self.state_indicator.setText(indicator)
        self.state_text.setText(text)
        self.state_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 6px;
            }}
        """)

    def _on_last_heard_update(self, text: str, status: str):
        """Update the 'last heard' section."""
        self.last_heard_box.setText(text)
        if status == "ignored":
            self.last_heard_status.setText("[Ignored - not a question]")
            self.last_heard_status.setStyleSheet("color: #999999; font-style: italic;")
        elif status == "answering":
            self.last_heard_status.setText("[Answering...]")
            self.last_heard_status.setStyleSheet("color: #4a90d9; font-style: italic;")
        elif status == "low_confidence":
            self.last_heard_status.setText("[Low confidence - skipped]")
            self.last_heard_status.setStyleSheet("color: #d9a54a; font-style: italic;")
        else:
            self.last_heard_status.setText("")

    def _on_queue_update(self, count: int):
        """Update queue indicator."""
        if count > 0:
            self.queue_label.setText(f"📋 {count} queued")
        else:
            self.queue_label.setText("")

    def closeEvent(self, event):
        """Clean up on close."""
        if self.is_listening:
            self._stop_listening()
        event.accept()


class AstraApp:
    """Application controller managing screen transitions."""

    def __init__(self):
        self.startup_screen = StartupScreen()
        self.session_window = None  # Lazy create

        # Connect startup screen signals
        self.startup_screen.ingest_requested.connect(self._on_ingest)
        self.startup_screen.start_session_requested.connect(self._on_start_session)

        # Thread for background ingestion
        self._ingest_thread = None

    def show(self):
        """Show the startup screen."""
        self.startup_screen.show()

    def _on_ingest(self):
        """Handle document ingestion request."""
        import os

        documents_path = "./documents/"

        # Check if documents folder exists
        if not os.path.exists(documents_path):
            self.startup_screen.set_status(
                f"Error: {documents_path} folder not found",
                is_error=True
            )
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

        # Run ingestion in background thread
        self._ingest_thread = threading.Thread(
            target=self._run_ingestion,
            args=(documents_path,),
            daemon=True
        )
        self._ingest_thread.start()

    def _run_ingestion(self, folder_path: str):
        """Background thread: run document ingestion with progress reporting."""
        from ingest import ingest_folder_with_progress

        def progress_callback(info: dict):
            """Emit progress signal from background thread."""
            self._ingestion_signals.progress.emit(info)

        try:
            result = ingest_folder_with_progress(folder_path, progress_callback)
            self._ingestion_signals.complete.emit(result)
        except Exception as e:
            self._ingestion_signals.complete.emit({
                "success": False,
                "total_files": 0,
                "total_chunks": 0,
                "errors": [str(e)]
            })

    def _on_ingestion_progress(self, info: dict):
        """Handle progress updates from ingestion thread."""
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
        # Create session window if not exists
        if self.session_window is None:
            self.session_window = AstraWindow()

        # Hide startup, show session
        self.startup_screen.hide()
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
