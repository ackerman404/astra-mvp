#!/usr/bin/env python3
"""
System Audio Transcription for Astra MVP.

Uses platform-agnostic AudioCapture abstraction and transcribes
using faster-whisper.
"""

import os
import sys

# CTranslate2 + PyInstaller fix: ctranslate2's __init__.py uses
# importlib.resources.files() to find its DLLs and pre-load them with
# ctypes.CDLL(). In a frozen exe this path resolves incorrectly, so the
# DLLs (especially libiomp5md.dll / Intel OpenMP) are never pre-loaded.
# When CTranslate2 later tries to use OpenMP during model init, Windows
# can't find libiomp5md.dll via standard LoadLibrary() and segfaults.
# Fix: explicitly pre-load the DLLs ourselves before importing ctranslate2.
if getattr(sys, 'frozen', False) and sys.platform == 'win32':
    import ctypes
    import glob
    os.environ.setdefault('OMP_NUM_THREADS', '1')
    os.environ.setdefault('KMP_DUPLICATE_LIB_OK', 'TRUE')
    _ct2_dir = os.path.join(sys._MEIPASS, 'ctranslate2')
    if os.path.isdir(_ct2_dir):
        os.add_dll_directory(_ct2_dir)
        for _dll in glob.glob(os.path.join(_ct2_dir, '*.dll')):
            try:
                ctypes.CDLL(_dll)
            except OSError:
                pass

import numpy as np
from faster_whisper import WhisperModel

from audio_capture import get_audio_capture, AudioCapture
from config import (
    AUDIO_SAMPLE_RATE,
    WHISPER_MODEL,
    WHISPER_DEVICE,
    WHISPER_COMPUTE_TYPE,
)


# Global Whisper model (lazy loaded)
_whisper_model = None


def get_whisper_model() -> WhisperModel:
    """Get or initialize the Whisper model."""
    global _whisper_model
    if _whisper_model is None:
        print(f"Loading Whisper model '{WHISPER_MODEL}'...", flush=True)

        frozen = getattr(sys, 'frozen', False)

        if frozen:
            # Frozen exe: load model bundled alongside the executable.
            # This bypasses huggingface_hub entirely — no network needed.
            model_path = os.path.join(sys._MEIPASS, 'whisper_model')
            _whisper_model = WhisperModel(
                model_path,
                device=WHISPER_DEVICE,
                compute_type=WHISPER_COMPUTE_TYPE,
                cpu_threads=1,
                num_workers=1,
            )
        else:
            # Dev: download to user cache (or use existing cache)
            from platformdirs import user_cache_dir
            _whisper_model = WhisperModel(
                WHISPER_MODEL,
                device=WHISPER_DEVICE,
                compute_type=WHISPER_COMPUTE_TYPE,
                download_root=user_cache_dir("astra"),
            )
        print("Model loaded.", flush=True)
    return _whisper_model


def transcribe_audio(audio_array: np.ndarray) -> str:
    """
    Transcribe audio from numpy array.

    Args:
        audio_array: numpy array of 16-bit audio at 16kHz

    Returns:
        Transcribed text string
    """
    if audio_array is None or len(audio_array) == 0:
        print("Warning: Empty audio buffer - check if audio is playing")
        return ""

    # Convert int16 to float32 normalized [-1.0, 1.0] for faster-whisper
    audio_float32 = audio_array.astype(np.float32) / 32768.0

    # Transcribe with optimized settings
    model = get_whisper_model()
    segments, _ = model.transcribe(
        audio_float32,
        beam_size=1,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500)
    )

    text_parts = [segment.text for segment in segments]
    return " ".join(text_parts).strip()


class ContinuousTranscriber:
    """Convenience wrapper for continuous capture and transcription."""

    def __init__(self, device: str = None):
        """
        Initialize continuous transcriber.

        Args:
            device: Audio source name, or None for auto-detect
        """
        self._capture = get_audio_capture(device)

    @property
    def device(self) -> str:
        """Get current device name."""
        return self._capture.device

    def list_devices(self) -> list[dict]:
        """List available monitor devices."""
        return self._capture.list_devices()

    def start(self):
        """Begin continuous audio capture."""
        self._capture.start_capture()

    def transcribe_recent(self, seconds: int = 30) -> str:
        """
        Transcribe last N seconds of audio.

        Args:
            seconds: Number of seconds to transcribe

        Returns:
            Transcribed text
        """
        audio = self._capture.get_last_n_seconds(seconds)
        return transcribe_audio(audio)

    def get_audio_level(self) -> float:
        """Get current audio level for UI."""
        return self._capture.get_audio_level()

    def stop(self) -> str:
        """
        Stop capture and transcribe remaining audio.

        Returns:
            Transcribed text
        """
        audio = self._capture.stop_capture()
        return transcribe_audio(audio)


if __name__ == "__main__":
    import time

    print("=== System Audio Capture Test ===\n")

    # Create capture via factory
    capture = get_audio_capture()
    print("Available monitor devices:")
    for dev in capture.list_devices():
        print(f"  [{dev['status']:10}] {dev['name']}")

    print(f"\nUsing device: {capture.device}")
    print("\n1. Play some audio (YouTube, Spotify, etc.)")
    print("2. Press Enter to start capturing...")
    input()

    capture.start_capture()
    print("Capturing for 5 seconds...\n")

    for i in range(5):
        time.sleep(1)
        level = capture.get_audio_level()
        bar = "\u2588" * int(level * 50)
        print(f"  Level: {bar:50} {level:.2f}")

    print("\nStopping capture and transcribing...")
    audio = capture.stop_capture()
    print(f"Captured {len(audio)} samples ({len(audio)/AUDIO_SAMPLE_RATE:.1f} seconds)")

    text = transcribe_audio(audio)

    print(f"\n=== Transcription ===\n{text if text else '(no speech detected)'}\n")
