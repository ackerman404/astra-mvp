#!/usr/bin/env python3
"""
Astra Interview Copilot - Configuration

Configuration constants and default values.
Audio device management moved to audio_capture.py.
API key management with cross-platform user config directory.
"""

from platformdirs import user_config_dir
from pathlib import Path
import yaml


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


def get_prompts_config_path() -> Path:
    """Get path to prompts YAML config file."""
    return get_config_dir() / "prompts.yaml"


def get_default_prompts_config() -> dict:
    """Return default prompts configuration."""
    return {
        "job_context": "",
        "default_tone": "professional",
        "tones": {
            "professional": "Use formal but warm language. Sound composed and authoritative. Speak as a senior consultant to a peer.",
            "casual": "Use relaxed, friendly language. Sound approachable and conversational. Speak as if chatting with a colleague.",
            "confident": "Use assertive, direct language. Sound self-assured and commanding. Speak with energy and conviction."
        },
        "prompts": {
            "classification": """You are an interview question classifier. Given text from an interviewer, determine:
1. Is this a question that requires the candidate to give a substantive answer?
2. What type of question is it?

ANSWER THESE (behavioral, situational, tell-me-about):
- 'Tell me about a time when you...'
- 'Describe a situation where...'
- 'How would you handle...'
- 'What's your experience with...'
- 'Walk me through...'
- 'Give me an example of...'
- Technical questions about skills, tools, or concepts

IGNORE THESE (small talk, transitions, statements):
- 'Thanks for that answer'
- 'Let me tell you about our team'
- 'That's great'
- 'Can you hear me okay?'
- 'Let's move on to the next topic'
- 'Interesting, tell me more' (follow-up, wait for more context)
- Statements about the company or role

Respond ONLY with valid JSON (no markdown): {"is_interview_question": true/false, "question_type": "behavioral"|"technical"|"situational"|"other"|"not_a_question", "confidence": 0.0-1.0, "cleaned_question": "the question cleaned up"}""",
            "bullet_system": """Generate exactly 3 ultra-short bullet points. Quick glance reference only.

STRICT FORMAT:
- Exactly 3 bullets
- 15-18 words MAX per bullet
- Start with "•"
- Key terms only, no explanations

EXAMPLE:
• Config: SPRO → MM → Purchasing; internal customer/vendor masters per plant
• Flow: ME21N → VL10B → MIGO GI/GR → auto-billing via SD-MM
• Gotcha: Set pricing procedure in intercompany billing or invoices fail""",
            "script_system": """You are an AI interview copilot generating speakable interview scripts.

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
1. Opening hook (1 line): Start with confidence, reference experience
2. Technical core (2-3 points woven into prose): Config, process, key details
3. Real-world touch (1 line): Error scenario or metric
4. Close (1 line): Follow-up offer

## SPEAKABILITY RULES:
- No abbreviation dumps: weave terms into natural sentences
- No bullet points or numbered lists in output
- Use pauses naturally: em-dashes, commas for breathing room
- Technical terms should flow: "I run MIGO for goods receipt, then MIRO for invoice verification"

## EXAMPLE OUTPUT:

"So intercompany stock transfers are something I've configured multiple times. The setup starts in SPRO under Materials Management — you define the shipping data between plants and set up the internal customer and vendor masters.

For the actual process, it kicks off with ME21N using document type UB, then the supplying plant handles delivery through VL10B. The key thing is the automatic billing — SAP creates the intercompany invoice through the SD-MM integration, but if the pricing procedure isn't configured right, those invoices fail silently in VF04.

At my last project, we processed about 2,000 of these monthly and I set up monitoring to catch anything stuck in GR/IR clearing. Happy to go deeper into the account flows if that's helpful."

## CONTEXT HANDLING:
If relevant context exists, personalize with specific client names, projects, and metrics.
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
        with open(config_path, "r") as f:
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
        with open(config_path, "w") as f:
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
