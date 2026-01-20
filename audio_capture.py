#!/usr/bin/env python3
"""
Audio Capture Abstraction Layer for Astra MVP.

Platform-agnostic audio capture interface with Linux (PulseAudio) implementation.
Windows implementation to be added in Plan 04-02.
"""

import subprocess
import sys
import threading
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass

import numpy as np


# Buffer configuration
MAX_BUFFER_SECONDS = 60
BYTES_PER_SAMPLE = 2  # 16-bit = 2 bytes


@dataclass
class AudioSource:
    """Represents an audio source device."""
    index: str
    name: str
    driver: str
    sample_spec: str
    state: str

    @property
    def is_monitor(self) -> bool:
        return ".monitor" in self.name

    @property
    def is_active(self) -> bool:
        return self.state in ("IDLE", "RUNNING")


class AudioCapture(ABC):
    """
    Abstract base class for platform-specific audio capture.

    Implementations must provide system audio capture functionality
    for their respective platforms.
    """

    @abstractmethod
    def start_capture(self) -> None:
        """Begin capturing system audio."""
        pass

    @abstractmethod
    def stop_capture(self) -> np.ndarray:
        """
        Stop capturing and return audio buffer.

        Returns:
            numpy array of 16-bit audio samples
        """
        pass

    @abstractmethod
    def get_last_n_seconds(self, n: int) -> np.ndarray:
        """
        Get last N seconds of audio without stopping capture.

        Args:
            n: Number of seconds to retrieve

        Returns:
            numpy array of 16-bit audio samples
        """
        pass

    @abstractmethod
    def get_audio_level(self) -> float:
        """
        Get current audio level (RMS) for UI meter.

        Returns:
            Float from 0.0 to 1.0
        """
        pass

    @abstractmethod
    def list_devices(self) -> list[dict]:
        """
        List available audio capture devices.

        Returns:
            List of dicts with 'name' and 'status' keys
        """
        pass

    @property
    @abstractmethod
    def device(self) -> str:
        """Get current device name."""
        pass


class LinuxAudioCapture(AudioCapture):
    """
    Linux audio capture implementation using PulseAudio/PipeWire.

    Uses parec subprocess for capturing and pactl for device listing.
    """

    def __init__(self, device: str = None, sample_rate: int = 16000, channels: int = 1):
        """
        Initialize Linux audio capture.

        Args:
            device: PulseAudio source name. If None, auto-detects.
            sample_rate: Audio sample rate (default 16000 for Whisper)
            channels: Number of audio channels (default 1 for mono)
        """
        self._sample_rate = sample_rate
        self._channels = channels
        self._process = None
        self._buffer_size = sample_rate * MAX_BUFFER_SECONDS * BYTES_PER_SAMPLE
        self._buffer = deque(maxlen=self._buffer_size)
        self._lock = threading.Lock()
        self._capturing = False
        self._read_thread = None
        self._read_chunk_size = int(sample_rate * 0.1 * BYTES_PER_SAMPLE)

        # Determine device
        if device:
            self._device = device
        else:
            # Try to get from config, or auto-detect
            try:
                from config import AUDIO_DEVICE
                self._device = AUDIO_DEVICE
            except ImportError:
                default = get_default_monitor()
                self._device = default if default else ""

        # Validate device exists
        self._validate_device()

    def _validate_device(self):
        """Validate the device exists, or find alternative."""
        monitors = list_monitor_devices()
        monitor_names = [m.name for m in monitors]

        if self._device not in monitor_names:
            if monitors:
                # Use first available monitor
                old_device = self._device
                self._device = monitors[0].name
                print(f"Warning: Device '{old_device}' not found")
                print(f"Using: {self._device}")
            else:
                print("Error: No monitor devices found")
                print("Make sure PipeWire/PulseAudio is running")

    @property
    def device(self) -> str:
        """Get current device name."""
        return self._device

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
                data = self._process.stdout.read(self._read_chunk_size)
                if data:
                    with self._lock:
                        self._buffer.extend(data)
                elif self._process.poll() is not None:
                    # Process ended
                    break
            except Exception as e:
                print(f"Error reading audio: {e}")
                break

    def start_capture(self) -> None:
        """Start capturing system audio."""
        if self._capturing:
            return

        # Clear buffer
        with self._lock:
            self._buffer.clear()

        # Start parec subprocess
        cmd = [
            "parec",
            f"--device={self._device}",
            f"--rate={self._sample_rate}",
            f"--channels={self._channels}",
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
                print(f"Error: Device not found: {self._device}")
                print("\nAvailable devices:")
                for dev in self.list_devices():
                    print(f"  [{dev['status']:10}] {dev['name']}")
                raise RuntimeError(f"Device not found: {self._device}")
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

    def get_last_n_seconds(self, n: int) -> np.ndarray:
        """
        Get last N seconds of audio without stopping capture.

        Args:
            n: Number of seconds to retrieve

        Returns:
            numpy array of 16-bit audio samples
        """
        bytes_needed = self._sample_rate * n * BYTES_PER_SAMPLE

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
        bytes_needed = int(self._sample_rate * 0.1 * BYTES_PER_SAMPLE)

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


# Module-level functions for device listing (platform-specific)

def list_audio_sources() -> list[AudioSource]:
    """
    List all audio sources using pactl (Linux).

    Returns:
        List of AudioSource objects
    """
    if sys.platform != "linux":
        return []

    try:
        result = subprocess.run(
            ["pactl", "list", "sources", "short"],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode != 0:
            print(f"Warning: pactl returned error: {result.stderr}")
            return []

        sources = []
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue

            parts = line.split('\t')
            if len(parts) >= 5:
                sources.append(AudioSource(
                    index=parts[0],
                    name=parts[1],
                    driver=parts[2],
                    sample_spec=parts[3],
                    state=parts[4]
                ))

        return sources

    except FileNotFoundError:
        print("Error: 'pactl' command not found.")
        print("Please install PulseAudio utilities:")
        print("  sudo apt install pulseaudio-utils")
        return []
    except subprocess.TimeoutExpired:
        print("Error: pactl command timed out")
        return []
    except Exception as e:
        print(f"Error listing audio sources: {e}")
        return []


def list_monitor_devices() -> list[AudioSource]:
    """
    List all monitor devices (for capturing system/app audio).

    Monitor devices capture audio output (what you hear from speakers).
    Prefers devices with status "IDLE" or "RUNNING" over "SUSPENDED".

    Returns:
        List of monitor AudioSource objects, sorted by activity status
    """
    sources = list_audio_sources()
    monitors = [s for s in sources if s.is_monitor]

    # Sort: active devices first, then suspended
    monitors.sort(key=lambda s: (not s.is_active, s.name))

    return monitors


def get_default_monitor() -> str | None:
    """
    Get the best available monitor device.

    1. Returns the first non-suspended monitor
    2. Falls back to first monitor if all suspended
    3. Returns None if no monitors found

    Returns:
        Device name string or None
    """
    monitors = list_monitor_devices()

    if not monitors:
        print("=" * 50)
        print("No audio monitor devices found!")
        print()
        print("Monitor devices capture system audio output.")
        print("Possible fixes:")
        print("  1. Check if PipeWire/PulseAudio is running:")
        print("     systemctl --user status pipewire pulseaudio")
        print()
        print("  2. List all audio devices:")
        print("     pactl list sources short")
        print()
        print("  3. If using PipeWire, ensure pipewire-pulse is installed:")
        print("     sudo apt install pipewire-pulse")
        print("=" * 50)
        return None

    # Return first active monitor, or first monitor if all suspended
    for monitor in monitors:
        if monitor.is_active:
            return monitor.name

    # All suspended, return first one
    return monitors[0].name


def get_audio_capture(device: str = None) -> AudioCapture:
    """
    Factory function to get platform-appropriate AudioCapture instance.

    Args:
        device: Device name/identifier. If None, auto-detects.

    Returns:
        AudioCapture implementation for the current platform

    Raises:
        NotImplementedError: If platform is not supported
    """
    if sys.platform == "linux":
        # Import config for sample rate and channels
        try:
            from config import AUDIO_SAMPLE_RATE, AUDIO_CHANNELS
            return LinuxAudioCapture(
                device=device,
                sample_rate=AUDIO_SAMPLE_RATE,
                channels=AUDIO_CHANNELS
            )
        except ImportError:
            return LinuxAudioCapture(device=device)

    elif sys.platform == "win32":
        # Windows support will be added in Plan 04-02
        raise NotImplementedError(
            "Windows audio capture not yet implemented. "
            "See Plan 04-02 for WASAPI implementation."
        )

    elif sys.platform == "darwin":
        raise NotImplementedError(
            "macOS audio capture not yet implemented."
        )

    else:
        raise NotImplementedError(
            f"Platform '{sys.platform}' is not supported for audio capture."
        )


if __name__ == "__main__":
    import time

    print("=== Audio Capture Abstraction Test ===\n")

    # Test factory function
    print(f"Platform: {sys.platform}")

    try:
        capture = get_audio_capture()
        print(f"AudioCapture implementation: {type(capture).__name__}")
        print(f"\nUsing device: {capture.device}")

        print("\nAvailable monitor devices:")
        for dev in capture.list_devices():
            print(f"  [{dev['status']:10}] {dev['name']}")

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

        print("\nStopping capture...")
        audio = capture.stop_capture()
        print(f"Captured {len(audio)} samples ({len(audio)/16000:.1f} seconds)")

    except NotImplementedError as e:
        print(f"Platform not supported: {e}")
    except Exception as e:
        print(f"Error: {e}")
