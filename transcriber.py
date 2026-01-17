#!/usr/bin/env python3
"""
System Audio Capture and Transcription for Astra MVP.

Captures system audio via PipeWire/PulseAudio monitor devices
and transcribes using faster-whisper.
"""

import subprocess
import threading
from collections import deque

import numpy as np
from faster_whisper import WhisperModel

from config import (
    AUDIO_DEVICE,
    AUDIO_SAMPLE_RATE,
    AUDIO_CHANNELS,
    WHISPER_MODEL,
    WHISPER_DEVICE,
    WHISPER_COMPUTE_TYPE,
    list_monitor_devices,
)

# Buffer size: 60 seconds of audio at 16kHz, 16-bit mono
MAX_BUFFER_SECONDS = 60
BYTES_PER_SAMPLE = 2  # 16-bit = 2 bytes
BUFFER_SIZE = AUDIO_SAMPLE_RATE * MAX_BUFFER_SECONDS * BYTES_PER_SAMPLE

# Chunk size for reading from parec (0.1 seconds)
READ_CHUNK_SIZE = int(AUDIO_SAMPLE_RATE * 0.1 * BYTES_PER_SAMPLE)

# Global Whisper model (lazy loaded)
_whisper_model = None


def get_whisper_model() -> WhisperModel:
    """Get or initialize the Whisper model."""
    global _whisper_model
    if _whisper_model is None:
        print(f"Loading Whisper model '{WHISPER_MODEL}'...")
        _whisper_model = WhisperModel(
            WHISPER_MODEL,
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE_TYPE
        )
        print("Model loaded.")
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


class SystemAudioCapture:
    """Captures system audio via PipeWire/PulseAudio monitor devices."""

    def __init__(self, device: str = None):
        """
        Initialize system audio capture.

        Args:
            device: PulseAudio source name. If None, uses config or auto-detects.
        """
        self._process = None
        self._buffer = deque(maxlen=BUFFER_SIZE)
        self._lock = threading.Lock()
        self._capturing = False
        self._read_thread = None

        # Determine device
        if device:
            self.device = device
        else:
            self.device = AUDIO_DEVICE

        # Validate device exists
        self._validate_device()

    def _validate_device(self):
        """Validate the device exists, or find alternative."""
        monitors = list_monitor_devices()
        monitor_names = [m.name for m in monitors]

        if self.device not in monitor_names:
            if monitors:
                # Use first available monitor
                old_device = self.device
                self.device = monitors[0].name
                print(f"Warning: Device '{old_device}' not found")
                print(f"Using: {self.device}")
            else:
                print("Error: No monitor devices found")
                print("Make sure PipeWire/PulseAudio is running")

    def list_devices(self) -> list[dict]:
        """
        List all available monitor devices.

        Returns:
            List of dicts with 'name' and 'status' keys
        """
        monitors = list_monitor_devices()
        return [{"name": m.name, "status": m.state} for m in monitors]

    def _read_loop(self):
        """Background thread: read audio data from parec."""
        while self._capturing and self._process:
            try:
                data = self._process.stdout.read(READ_CHUNK_SIZE)
                if data:
                    with self._lock:
                        self._buffer.extend(data)
                elif self._process.poll() is not None:
                    # Process ended
                    break
            except Exception as e:
                print(f"Error reading audio: {e}")
                break

    def start_capture(self):
        """Start capturing system audio."""
        if self._capturing:
            return

        # Clear buffer
        with self._lock:
            self._buffer.clear()

        # Start parec subprocess
        cmd = [
            "parec",
            f"--device={self.device}",
            f"--rate={AUDIO_SAMPLE_RATE}",
            f"--channels={AUDIO_CHANNELS}",
            "--format=s16le",
            "--raw"
        ]

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
        except FileNotFoundError:
            print("Error: 'parec' command not found")
            print("Install with: sudo apt install pulseaudio-utils")
            raise RuntimeError("parec not found")

        # Check for immediate errors
        try:
            self._process.wait(timeout=0.1)
            stderr = self._process.stderr.read().decode()
            if "does not exist" in stderr or "No such" in stderr:
                print(f"Error: Device not found: {self.device}")
                print("\nAvailable devices:")
                for dev in self.list_devices():
                    print(f"  [{dev['status']:10}] {dev['name']}")
                raise RuntimeError(f"Device not found: {self.device}")
        except subprocess.TimeoutExpired:
            pass  # Process is running, good

        self._capturing = True
        self._read_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._read_thread.start()

    def stop_capture(self) -> np.ndarray:
        """
        Stop capturing and return audio buffer.

        Returns:
            numpy array of 16-bit audio samples
        """
        self._capturing = False

        # Stop process
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None

        # Wait for read thread
        if self._read_thread:
            self._read_thread.join(timeout=1)
            self._read_thread = None

        # Get buffer as numpy array
        with self._lock:
            audio_bytes = bytes(self._buffer)

        if not audio_bytes:
            return np.array([], dtype=np.int16)

        return np.frombuffer(audio_bytes, dtype=np.int16)

    def get_last_n_seconds(self, n: int = 30) -> np.ndarray:
        """
        Get last N seconds of audio without stopping capture.

        Args:
            n: Number of seconds to retrieve

        Returns:
            numpy array of 16-bit audio samples
        """
        bytes_needed = AUDIO_SAMPLE_RATE * n * BYTES_PER_SAMPLE

        with self._lock:
            buffer_list = list(self._buffer)

        # Get last N seconds
        if len(buffer_list) > bytes_needed:
            audio_bytes = bytes(buffer_list[-bytes_needed:])
        else:
            audio_bytes = bytes(buffer_list)

        if not audio_bytes:
            return np.array([], dtype=np.int16)

        return np.frombuffer(audio_bytes, dtype=np.int16)

    def get_audio_level(self) -> float:
        """
        Get current audio level (RMS) for UI meter.

        Returns:
            Float from 0.0 to 1.0
        """
        # Get last 0.1 seconds
        bytes_needed = int(AUDIO_SAMPLE_RATE * 0.1 * BYTES_PER_SAMPLE)

        with self._lock:
            buffer_list = list(self._buffer)

        if len(buffer_list) < bytes_needed:
            return 0.0

        audio_bytes = bytes(buffer_list[-bytes_needed:])
        samples = np.frombuffer(audio_bytes, dtype=np.int16)

        if len(samples) == 0:
            return 0.0

        # Calculate RMS and normalize to 0-1 range
        rms = np.sqrt(np.mean(samples.astype(np.float32) ** 2))
        normalized = min(1.0, rms / 32768.0 * 4)  # Scale for visibility

        return normalized

    def __del__(self):
        """Cleanup."""
        if self._capturing:
            self.stop_capture()


class ContinuousTranscriber:
    """Convenience wrapper for continuous capture and transcription."""

    def __init__(self, device: str = None):
        """
        Initialize continuous transcriber.

        Args:
            device: PulseAudio source name, or None for auto-detect
        """
        self._capture = SystemAudioCapture(device)

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

    # List devices
    capture = SystemAudioCapture()
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
        bar = "█" * int(level * 50)
        print(f"  Level: {bar:50} {level:.2f}")

    print("\nStopping capture and transcribing...")
    audio = capture.stop_capture()
    print(f"Captured {len(audio)} samples ({len(audio)/AUDIO_SAMPLE_RATE:.1f} seconds)")

    text = transcribe_audio(audio)

    print(f"\n=== Transcription ===\n{text if text else '(no speech detected)'}\n")
