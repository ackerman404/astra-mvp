#!/usr/bin/env python3
"""
Astra Interview Copilot - Configuration

Configuration constants and default values.
Audio device management moved to audio_capture.py.
API key management with cross-platform user config directory.
"""

from platformdirs import user_config_dir
from pathlib import Path


def get_config_dir() -> Path:
    """Get cross-platform user config directory for Astra."""
    config_dir = Path(user_config_dir("astra"))
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_api_key() -> str | None:
    """
    Load OpenAI API key from user config directory.

    Config location:
    - Linux: ~/.config/astra/.env
    - Windows: %APPDATA%/astra/.env
    - macOS: ~/Library/Application Support/astra/.env

    Returns None if not found.
    """
    config_file = get_config_dir() / ".env"

    if not config_file.exists():
        return None

    # Parse simple KEY=value format
    with open(config_file, "r") as f:
        for line in f:
            line = line.strip()
            if line.startswith("OPENAI_API_KEY="):
                # Handle quoted values
                value = line.split("=", 1)[1]
                return value.strip('"').strip("'")

    return None


def get_config_path() -> Path:
    """Get path to config file for display to user."""
    return get_config_dir() / ".env"


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
CONTEXT_RELEVANCE_THRESHOLD = 0.3  # Below this, consider context not relevant
MIN_CONTEXT_RELEVANCE = 0.2  # Filter out chunks below this threshold

# Auto-Answer Mode Configuration
SILENCE_THRESHOLD = 0.01        # Audio level below this = silence
SILENCE_DURATION = 2.0          # Seconds of silence to trigger processing
MIN_SPEECH_DURATION = 1.0       # Ignore very short utterances (coughs, etc.)
CLASSIFICATION_CONFIDENCE = 0.7  # Minimum confidence to auto-answer
MIN_WORDS_FOR_CLASSIFICATION = 3  # Skip LLM if fewer words than this


def get_default_monitor() -> str | None:
    """
    Get the best available monitor device.

    Delegates to audio_capture module.

    Returns:
        Device name string or None
    """
    from audio_capture import get_default_monitor as _get_default_monitor
    return _get_default_monitor()


def print_audio_config():
    """Print current audio configuration and available devices."""
    from audio_capture import list_monitor_devices

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
