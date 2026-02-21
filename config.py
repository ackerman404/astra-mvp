#!/usr/bin/env python3
"""
Astra Interview Copilot - Configuration

Configuration constants and default values.
Audio device management moved to audio_capture.py.
License key, proxy URL, and hardware ID management with cross-platform user config directory.
"""

import hashlib
import platform
import subprocess
from functools import lru_cache
from pathlib import Path

import yaml
from platformdirs import user_config_dir


def get_config_dir() -> Path:
    """Get cross-platform user config directory for Astra."""
    config_dir = Path(user_config_dir("astra"))
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


# ---------------------------------------------------------------------------
# .env file helpers (KEY=value format)
# ---------------------------------------------------------------------------


def _read_env_file() -> dict[str, str]:
    """Read all key-value pairs from the .env config file."""
    config_file = get_config_dir() / ".env"
    data: dict[str, str] = {}

    if not config_file.exists():
        return data

    with open(config_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                data[key.strip()] = value.strip().strip('"').strip("'")

    return data


def _write_env_file(data: dict[str, str]) -> bool:
    """Write key-value pairs to the .env config file."""
    config_file = get_config_dir() / ".env"
    try:
        with open(config_file, "w", encoding="utf-8") as f:
            for key, value in data.items():
                f.write(f"{key}={value}\n")
        return True
    except IOError:
        return False


# ---------------------------------------------------------------------------
# License key management
# ---------------------------------------------------------------------------


def get_license_key() -> str | None:
    """
    Load license key from user config directory.

    Config location:
    - Linux: ~/.config/astra/.env
    - Windows: %APPDATA%/astra/.env
    - macOS: ~/Library/Application Support/astra/.env

    Returns None if not found.
    """
    data = _read_env_file()
    return data.get("LICENSE_KEY") or None


def save_license_key(key: str) -> bool:
    """Write LICENSE_KEY to the .env file, preserving other entries."""
    data = _read_env_file()
    data["LICENSE_KEY"] = key
    return _write_env_file(data)


def clear_license_key() -> bool:
    """Remove the LICENSE_KEY line from the .env file."""
    data = _read_env_file()
    data.pop("LICENSE_KEY", None)
    return _write_env_file(data)


# ---------------------------------------------------------------------------
# Proxy URL management
# ---------------------------------------------------------------------------

_DEFAULT_PROXY_URL = "https://backend-production-1dff.up.railway.app/v1"


def get_proxy_url() -> str:
    """
    Read PROXY_URL from the .env file.

    Returns the configured URL or the production default if not set.
    For local dev, set PROXY_URL=http://localhost:8000/v1 in the .env file.
    """
    data = _read_env_file()
    return data.get("PROXY_URL") or _DEFAULT_PROXY_URL


def save_proxy_url(url: str) -> bool:
    """Write PROXY_URL to the .env file, preserving other entries."""
    data = _read_env_file()
    data["PROXY_URL"] = url
    return _write_env_file(data)


# ---------------------------------------------------------------------------
# Hardware ID
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_hardware_id() -> str:
    """
    Generate a stable machine identifier (32-char hex string).

    Strategy:
    - Linux: SHA-256 hash of /etc/machine-id
    - Windows: SHA-256 hash of wmic csproduct UUID
    - Fallback: SHA-256 hash of MAC address via uuid.getnode()

    Cached per process (computed once).
    """
    system = platform.system()

    try:
        if system == "Linux":
            machine_id_path = Path("/etc/machine-id")
            if machine_id_path.exists():
                raw = machine_id_path.read_text().strip()
                return hashlib.sha256(raw.encode()).hexdigest()[:32]

        elif system == "Windows":
            result = subprocess.run(
                ["wmic", "csproduct", "get", "uuid"],
                capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.strip().splitlines():
                line = line.strip()
                if line and line.upper() != "UUID":
                    return hashlib.sha256(line.encode()).hexdigest()[:32]
    except Exception:
        pass

    # Fallback: MAC address
    import uuid
    return hashlib.sha256(str(uuid.getnode()).encode()).hexdigest()[:32]


def get_config_path() -> Path:
    """Get path to .env config file for display to user (license key, proxy URL)."""
    return get_config_dir() / ".env"


def get_prompts_config_path() -> Path:
    """Get path to prompts YAML config file."""
    return get_config_dir() / "prompts.yaml"


def get_default_prompts_config() -> dict:
    """Return default prompts configuration for Robotics/ROS2/GNC interviews."""
    return {
        "job_context": """Role: Robotics / Autonomy Engineer (GNC focus)
Stack: ROS2, C++, Python, Gazebo, Nav2
Domains: State estimation, path planning, control systems, sensor fusion
Experience: Kalman filters, MPC, behavior trees, SLAM, tf2 transforms""",
        "default_tone": "professional",
        "tones": {
            "professional": "Use formal but warm language. Sound composed and authoritative. Speak as a senior robotics engineer to a peer.",
            "casual": "Use relaxed, friendly language. Sound approachable and conversational. Speak as if chatting with a colleague about robotics.",
            "confident": "Use assertive, direct language. Sound self-assured and commanding. Speak with energy and conviction about your robotics expertise."
        },
        "prompts": {
            "classification": """You are an interview question classifier for robotics/autonomy engineering roles. Given text from an interviewer, determine:
1. Is this a question that requires the candidate to give a substantive answer?
2. What type of question is it?

ANSWER THESE (behavioral, situational, technical):
- 'Tell me about a time when you...'
- 'Describe a situation where...'
- 'How would you handle...'
- 'What's your experience with...'
- 'Walk me through...'
- 'Give me an example of...'
- 'Explain how X works' (ROS2, SLAM, EKF, path planning, etc.)
- 'How would you design/implement...'
- 'What's the difference between X and Y'
- Technical questions about robotics, ROS2, GNC, perception, planning, control

IGNORE THESE (small talk, transitions, statements):
- 'Thanks for that answer'
- 'Let me tell you about our team'
- 'That's great'
- 'Can you hear me okay?'
- 'Let's move on to the next topic'
- 'Interesting, tell me more' (follow-up, wait for more context)
- Statements about the company or role

Respond ONLY with valid JSON (no markdown): {"is_interview_question": true/false, "question_type": "behavioral"|"technical"|"situational"|"system_design"|"other"|"not_a_question", "confidence": 0.0-1.0, "cleaned_question": "the question cleaned up"}""",
            "bullet_system": """Generate exactly 3 ultra-short bullet points for robotics interview answers. Quick glance reference only.

STRICT FORMAT:
- Exactly 3 bullets
- 15-18 words MAX per bullet
- Start with bullet character
- Use standard robotics terminology: EKF, MPC, tf2, Nav2, costmap, etc.

EXAMPLE (for "Explain sensor fusion with IMU and GPS"):
- IMU predicts at 100Hz (accel/gyro integration); GPS updates at 10Hz with position fix
- EKF prediction step propagates state; update step corrects with Kalman gain
- Key challenges: GPS latency (50-200ms), outlier rejection, covariance tuning""",
            "script_system": """You are an AI interview copilot generating speakable answers for robotics/autonomy engineering interviews.

## YOUR TASK:
Generate a natural, conversational answer that the candidate can read aloud verbatim during a live interview.

## TONE:
{tone_instruction}

## FORMAT RULES:
- Write as flowing speech, NOT bullet points
- Use complete sentences with natural transitions
- Include verbal connectors: "The key thing here is...", "What's important to note...", "In my experience..."
- Keep it concise: 150-250 words ideal
- End with a follow-up offer: "I can go deeper into X if you'd like"

## CONTENT STRUCTURE:
1. Opening hook (1 line): Start with confidence, reference robotics experience
2. Technical core (2-3 points woven into prose): Algorithms, ROS2 specifics, architecture
3. Real-world touch (1 line): Debugging story, metric, or practical insight
4. Close (1 line): Follow-up offer

## ROBOTICS-SPECIFIC GUIDELINES:
- Use standard terminology: EKF/UKF, MPC, tf2, Nav2, costmap, behavior tree, etc.
- Reference real tools: RViz, Gazebo, rosbag, colcon, ros2 launch
- Mention specific message types when relevant: Twist, PoseStamped, LaserScan, Odometry
- Include practical details: rates (Hz), frame names, common pitfalls

## EXAMPLE OUTPUT (for "How does tf2 work?"):

"So tf2 is something I use daily - it's the transform library that maintains relationships between coordinate frames. The core idea is a tree structure where every frame has one parent, and you can query transforms between any two frames.

In practice, I set up a tf2 buffer and listener in my nodes. When I need to transform sensor data - say lidar points from the sensor frame to the map frame - I call buffer.transform() with a timeout. The buffer stores recent transforms, typically the last 10 seconds, which handles the fact that different data arrives at different times.

The common gotcha is extrapolation errors - if you ask for a transform at a time that's not in the buffer, it fails. I always wrap transform calls in try-catch and handle LookupException gracefully. For static transforms like sensor mounts, I use static_transform_publisher so they're always available.

Happy to walk through a specific multi-sensor setup if that would be helpful."

## CONTEXT HANDLING:
If relevant context exists from the knowledge base, personalize with specific projects, metrics, and experience.
If no relevant context, use "In my experience..." or "The standard approach is..." framing."""
        }
    }


def load_prompts_config() -> dict:
    """
    Load prompts config from YAML file.
    Creates default config if file doesn't exist.
    Falls back to defaults on parse error.
    """
    config_path = get_prompts_config_path()
    defaults = get_default_prompts_config()

    if not config_path.exists():
        # Create default config file
        save_prompts_config(defaults)
        return defaults

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
            if config is None:
                return defaults
            # Merge with defaults for any missing keys
            merged = defaults.copy()
            merged.update(config)
            # Ensure nested dicts are merged
            if "tones" in config:
                merged["tones"] = {**defaults["tones"], **config["tones"]}
            if "prompts" in config:
                merged["prompts"] = {**defaults["prompts"], **config["prompts"]}
            return merged
    except (yaml.YAMLError, IOError) as e:
        print(f"Warning: Failed to load prompts config: {e}")
        print("Using default prompts.")
        return defaults


def save_prompts_config(config: dict) -> bool:
    """
    Save prompts config to YAML file.
    Returns True on success, False on failure.
    """
    config_path = get_prompts_config_path()
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        return True
    except IOError as e:
        print(f"Warning: Failed to save prompts config: {e}")
        return False


# Audio Configuration
# Change this to match your audio output's monitor device
# Run: pactl list sources short | grep monitor
# Pick the one for your speakers (usually without _3, _4, _5 suffix - those are HDMI)
AUDIO_DEVICE = "alsa_output.pci-0000_00_1f.3-platform-skl_hda_dsp_generic.HiFi__hw_sofhdadsp__sink.monitor"
AUDIO_SAMPLE_RATE = 16000  # Whisper expects 16kHz
AUDIO_CHANNELS = 1  # Mono

# Whisper Configuration
WHISPER_MODEL = "base.en"
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
