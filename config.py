#!/usr/bin/env python3
"""
Astra Interview Copilot - Configuration

Audio device configuration for Linux PipeWire/PulseAudio.
"""

import subprocess
from dataclasses import dataclass

# Audio Configuration
AUDIO_DEVICE = "alsa_output.pci-0000_00_1f.3-platform-skl_hda_dsp_generic.HiFi__hw_sofhdadsp__sink.monitor"
AUDIO_SAMPLE_RATE = 16000  # Whisper expects 16kHz
AUDIO_CHANNELS = 1  # Mono

# Whisper Configuration
WHISPER_MODEL = "tiny.en"
WHISPER_DEVICE = "cpu"
WHISPER_COMPUTE_TYPE = "int8"

# RAG Configuration
EMBEDDING_MODEL = "text-embedding-3-small"
LLM_MODEL = "gpt-4o"
CLASSIFICATION_MODEL = "gpt-4o-mini"  # Fast model for question classification
COLLECTION_NAME = "astra_docs"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50

# Auto-Answer Mode Configuration
SILENCE_THRESHOLD = 0.01        # Audio level below this = silence
SILENCE_DURATION = 2.0          # Seconds of silence to trigger processing
MIN_SPEECH_DURATION = 1.0       # Ignore very short utterances (coughs, etc.)
CLASSIFICATION_CONFIDENCE = 0.7  # Minimum confidence to auto-answer
MIN_WORDS_FOR_CLASSIFICATION = 3  # Skip LLM if fewer words than this


@dataclass
class AudioSource:
    """Represents a PulseAudio/PipeWire audio source."""
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


def list_audio_sources() -> list[AudioSource]:
    """
    List all audio sources using pactl.

    Returns:
        List of AudioSource objects
    """
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


def print_audio_config():
    """Print current audio configuration and available devices."""
    print("Audio Configuration")
    print("=" * 50)
    print(f"Sample Rate: {AUDIO_SAMPLE_RATE} Hz")
    print(f"Channels: {AUDIO_CHANNELS} (mono)")
    print(f"Configured Device: {AUDIO_DEVICE}")
    print()

    print("Available Monitor Devices:")
    print("-" * 50)
    monitors = list_monitor_devices()

    if not monitors:
        print("  (none found)")
    else:
        for m in monitors:
            status = "active" if m.is_active else "suspended"
            print(f"  [{m.index}] {m.name}")
            print(f"      State: {status}, Driver: {m.driver}")

    print()
    default = get_default_monitor()
    if default:
        print(f"Recommended Device: {default}")
    print("=" * 50)


if __name__ == "__main__":
    print_audio_config()
