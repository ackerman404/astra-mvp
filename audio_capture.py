#!/usr/bin/env python3
"""
Audio Capture Abstraction Layer for Astra MVP.

Platform-agnostic audio capture interface with implementations for:
- Linux (PulseAudio/PipeWire via parec)
- Windows (WASAPI loopback via PyAudioWPatch)
"""

import subprocess
import sys
import threading
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass

import numpy as np

# Conditional import for Windows audio
if sys.platform == "win32":
    try:
        import pyaudiowpatch as pyaudio
    except ImportError:
        pyaudio = None


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


class WindowsAudioCapture(AudioCapture):
    """
    Windows audio capture implementation using PyAudioWPatch WASAPI loopback.

    PyAudioWPatch extends PyAudio with WASAPI loopback support for capturing
    system audio on Windows.
    """

    def __init__(self, device: str = None, sample_rate: int = 16000, channels: int = 1):
        """
        Initialize Windows audio capture.

        Args:
            device: WASAPI device name. If None, auto-detects default loopback.
            sample_rate: Target sample rate (default 16000 for Whisper)
            channels: Target channels (default 1 for mono)
        """
        if sys.platform != "win32":
            raise RuntimeError("WindowsAudioCapture only works on Windows")

        if pyaudio is None:
            raise ImportError(
                "PyAudioWPatch is required for Windows audio capture. "
                "Install with: pip install PyAudioWPatch"
            )

        self._target_sample_rate = sample_rate
        self._target_channels = channels
        self._stream = None
        self._buffer_size = sample_rate * MAX_BUFFER_SECONDS * BYTES_PER_SAMPLE
        self._buffer = deque(maxlen=self._buffer_size)
        self._lock = threading.Lock()
        self._capturing = False
        self._pa = None

        # Will be set when we find the loopback device
        self._device = None
        self._device_info = None
        self._actual_sample_rate = None
        self._actual_channels = None

        # Initialize PyAudio and find device
        self._init_audio(device)

    def _init_audio(self, device_name: str = None):
        """Initialize PyAudio and find loopback device."""
        self._pa = pyaudio.PyAudio()

        if device_name:
            # Find specific device
            self._device_info = self._find_device_by_name(device_name)
        else:
            # Auto-detect default loopback
            self._device_info = self._find_default_loopback()

        if self._device_info is None:
            raise RuntimeError(
                "No WASAPI loopback device found. "
                "Make sure you have audio output devices available."
            )

        self._device = self._device_info.get("name", "Unknown")
        self._actual_sample_rate = int(self._device_info.get("defaultSampleRate", 44100))
        self._actual_channels = int(self._device_info.get("maxInputChannels", 2))

    def _find_default_loopback(self) -> dict | None:
        """
        Find the default WASAPI loopback device.

        PyAudioWPatch provides loopback devices for capturing speaker output.
        """
        try:
            # Get the default WASAPI output device
            wasapi_info = self._pa.get_host_api_info_by_type(pyaudio.paWASAPI)
            default_output_idx = wasapi_info.get("defaultOutputDevice")

            if default_output_idx < 0:
                return None

            default_output = self._pa.get_device_info_by_index(default_output_idx)

            # Find the loopback device for this output
            # PyAudioWPatch adds loopback devices that mirror output devices
            for i in range(self._pa.get_device_count()):
                device_info = self._pa.get_device_info_by_index(i)

                # Loopback devices have isLoopbackDevice flag
                if device_info.get("isLoopbackDevice", False):
                    # Check if it's for our default output
                    # The name often contains the output device name
                    if default_output["name"] in device_info.get("name", ""):
                        return device_info

            # If no matching loopback found, try to get any loopback device
            for i in range(self._pa.get_device_count()):
                device_info = self._pa.get_device_info_by_index(i)
                if device_info.get("isLoopbackDevice", False):
                    return device_info

            return None

        except Exception as e:
            print(f"Error finding default loopback: {e}")
            return None

    def _find_device_by_name(self, name: str) -> dict | None:
        """Find a device by name."""
        for i in range(self._pa.get_device_count()):
            device_info = self._pa.get_device_info_by_index(i)
            if name in device_info.get("name", ""):
                return device_info
        return None

    @property
    def device(self) -> str:
        """Get current device name."""
        return self._device or ""

    def list_devices(self) -> list[dict]:
        """
        List all available WASAPI loopback devices.

        Returns:
            List of dicts with 'name' and 'status' keys
        """
        devices = []

        if self._pa is None:
            return devices

        for i in range(self._pa.get_device_count()):
            try:
                device_info = self._pa.get_device_info_by_index(i)

                # Only show loopback devices
                if device_info.get("isLoopbackDevice", False):
                    devices.append({
                        "name": device_info.get("name", f"Device {i}"),
                        "status": "AVAILABLE"
                    })
            except Exception:
                continue

        return devices

    def _audio_callback(self, in_data, frame_count, time_info, status):
        """Callback for audio stream - receives audio data."""
        if self._capturing and in_data:
            # Convert to target format if needed
            audio_data = self._convert_audio(in_data)
            with self._lock:
                self._buffer.extend(audio_data)

        return (None, pyaudio.paContinue)

    def _convert_audio(self, data: bytes) -> bytes:
        """
        Convert audio from device format to target format.

        Handles sample rate and channel conversion for Whisper compatibility.
        """
        # Parse as float32 (WASAPI typically uses float32)
        try:
            samples = np.frombuffer(data, dtype=np.float32)
        except ValueError:
            # Try int16 if float32 fails
            samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0

        # Reshape for channels
        if self._actual_channels > 1:
            samples = samples.reshape(-1, self._actual_channels)
            # Convert to mono by averaging channels
            samples = samples.mean(axis=1)

        # Resample if needed
        if self._actual_sample_rate != self._target_sample_rate:
            # Simple resampling using linear interpolation
            ratio = self._target_sample_rate / self._actual_sample_rate
            new_length = int(len(samples) * ratio)
            if new_length > 0:
                x_old = np.linspace(0, 1, len(samples))
                x_new = np.linspace(0, 1, new_length)
                samples = np.interp(x_new, x_old, samples)

        # Convert to int16 for Whisper
        samples = np.clip(samples * 32768, -32768, 32767).astype(np.int16)

        return samples.tobytes()

    def start_capture(self) -> None:
        """Start capturing system audio via WASAPI loopback."""
        if self._capturing:
            return

        if self._device_info is None:
            raise RuntimeError("No audio device configured")

        # Clear buffer
        with self._lock:
            self._buffer.clear()

        # Open stream with callback
        try:
            self._stream = self._pa.open(
                format=pyaudio.paFloat32,
                channels=self._actual_channels,
                rate=self._actual_sample_rate,
                input=True,
                input_device_index=self._device_info["index"],
                frames_per_buffer=1024,
                stream_callback=self._audio_callback
            )
            self._capturing = True
            self._stream.start_stream()
        except Exception as e:
            raise RuntimeError(f"Failed to start audio capture: {e}")

    def stop_capture(self) -> np.ndarray:
        """
        Stop capturing and return audio buffer.

        Returns:
            numpy array of 16-bit audio samples
        """
        self._capturing = False

        # Stop stream
        if self._stream:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

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
        bytes_needed = self._target_sample_rate * n * BYTES_PER_SAMPLE

        with self._lock:
            buf_len = len(self._buffer)
            if buf_len == 0:
                return np.array([], dtype=np.int16)
            # Snapshot only what we need — avoids copying entire 60s buffer
            take = min(buf_len, bytes_needed)
            # deque supports efficient iteration from right via reversed()
            snapshot = bytes(list(self._buffer)[-take:]) if take < buf_len else bytes(self._buffer)

        return np.frombuffer(snapshot, dtype=np.int16)

    def get_audio_level(self) -> float:
        """
        Get current audio level (RMS) for UI meter.

        Returns:
            Float from 0.0 to 1.0
        """
        # Get last 0.1 seconds
        bytes_needed = int(self._target_sample_rate * 0.1 * BYTES_PER_SAMPLE)

        with self._lock:
            buf_len = len(self._buffer)
            if buf_len < bytes_needed:
                return 0.0
            audio_bytes = bytes(list(self._buffer)[-bytes_needed:])

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
        if self._pa:
            try:
                self._pa.terminate()
            except Exception:
                pass


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
        # Windows implementation using PyAudioWPatch WASAPI loopback
        try:
            from config import AUDIO_SAMPLE_RATE, AUDIO_CHANNELS
            return WindowsAudioCapture(
                device=device,
                sample_rate=AUDIO_SAMPLE_RATE,
                channels=AUDIO_CHANNELS
            )
        except ImportError:
            return WindowsAudioCapture(device=device)

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
