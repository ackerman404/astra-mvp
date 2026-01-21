#!/usr/bin/env python3
"""
RAG retrieval module for Astra MVP.
Searches ChromaDB for relevant document chunks.
"""

from collections.abc import Generator
import os

import chromadb
from openai import OpenAI
import json

from config import get_api_key, load_prompts_config

# Cross-platform path for ChromaDB
CHROMA_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chroma_db")

COLLECTION_NAME = "astra_docs"
EMBEDDING_MODEL = "text-embedding-3-small"
CLASSIFICATION_MODEL = "gpt-4o-mini"

# Config cache
_prompts_config = None


def search_context(query: str, top_k: int = 5) -> list[dict]:
    """
    Search for relevant document chunks based on a query.

    1. Embed the query using OpenAI text-embedding-3-small
    2. Search ChromaDB for top_k similar chunks
    3. Return list of {text, source_file, similarity_score}

    Returns empty list if no documents ingested (graceful fallback).
    """
    # Check if chroma_db exists at all
    if not os.path.exists(CHROMA_DB_PATH):
        return []

    # Initialize ChromaDB client
    try:
        chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    except Exception:
        return []

    # Get collection - return empty if doesn't exist
    try:
        collection = chroma_client.get_collection(name=COLLECTION_NAME)
    except (ValueError, Exception):
        return []

    # Check if collection has any documents
    if collection.count() == 0:
        return []

    # Now we know documents exist, get API key for embedding
    api_key = get_api_key()
    if not api_key:
        raise RuntimeError("OpenAI API key not configured. Run the GUI for setup instructions.")
    openai_client = OpenAI(api_key=api_key)

    # Embed the query
    response = openai_client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=query
    )
    query_embedding = response.data[0].embedding

    # Search ChromaDB
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["documents", "metadatas", "distances"]
    )

    # Format results
    formatted_results = []
    if results["documents"] and results["documents"][0]:
        for doc, metadata, distance in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0]
        ):
            # ChromaDB returns cosine distance, convert to similarity
            similarity_score = 1 - distance
            formatted_results.append({
                "text": doc,
                "source_file": metadata.get("source_file", "unknown"),
                "similarity_score": similarity_score
            })

    return formatted_results


DEFAULT_CLASSIFICATION_PROMPT = """You are an interview question classifier. Given text from an interviewer, determine:
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

Respond ONLY with valid JSON (no markdown): {"is_interview_question": true/false, "question_type": "behavioral"|"technical"|"situational"|"other"|"not_a_question", "confidence": 0.0-1.0, "cleaned_question": "the question cleaned up"}"""


def classify_utterance(text: str, min_words: int = 3) -> dict:
    """
    Classify if text is an interview question using GPT-4o-mini.

    Args:
        text: The transcribed text to classify
        min_words: Skip LLM classification if fewer words than this

    Returns:
        {
            "is_interview_question": bool,
            "question_type": "behavioral" | "technical" | "situational" | "other" | "not_a_question",
            "confidence": float (0-1),
            "cleaned_question": str
        }
    """
    # Fast path: skip LLM for very short utterances
    words = text.split()
    if len(words) < min_words:
        return {
            "is_interview_question": False,
            "question_type": "not_a_question",
            "confidence": 1.0,
            "cleaned_question": text
        }

    api_key = get_api_key()
    if not api_key:
        raise RuntimeError("OpenAI API key not configured. Run the GUI for setup instructions.")
    openai_client = OpenAI(api_key=api_key)

    try:
        response = openai_client.chat.completions.create(
            model=CLASSIFICATION_MODEL,
            messages=[
                {"role": "system", "content": get_prompt("classification")},
                {"role": "user", "content": f"Classify this: \"{text}\""}
            ],
            max_tokens=100,
            temperature=0
        )

        result_text = response.choices[0].message.content.strip()
        # Parse JSON response
        result = json.loads(result_text)

        # Ensure all required fields exist
        return {
            "is_interview_question": result.get("is_interview_question", False),
            "question_type": result.get("question_type", "not_a_question"),
            "confidence": float(result.get("confidence", 0.5)),
            "cleaned_question": result.get("cleaned_question", text)
        }

    except (json.JSONDecodeError, KeyError) as e:
        # If parsing fails, be conservative and don't auto-answer
        print(f"Classification parse error: {e}")
        return {
            "is_interview_question": False,
            "question_type": "not_a_question",
            "confidence": 0.0,
            "cleaned_question": text
        }
    except Exception as e:
        print(f"Classification error: {e}")
        return {
            "is_interview_question": False,
            "question_type": "not_a_question",
            "confidence": 0.0,
            "cleaned_question": text
        }


DEFAULT_STAR_SYSTEM_PROMPT = """You are an AI interview copilot for SAP Consultants, helping a candidate answer live interview questions in real-time.

## YOUR ROLE:
- Give impressive, technically rich answers filled with configurations, master data, transaction codes, and business process flows
- Speak with calm authority - assume the interviewer is senior, avoid basic definitions
- Make answers SPEAKABLE - the candidate will read this out loud verbatim

## ANSWER STRUCTURE (Use this flow):

**Opening Hook** (1 line - confident, direct):
"In my experience with [specific project/client], I handled this by..."
OR "The standard approach here is... and I've implemented this at [client/project]..."

**Technical Core** (3-5 bullet points, SPEAKABLE):
- Config path: SPRO → [path] → [specific setting] — this controls [what]
- Key master data: [objects] with [critical fields]
- Process flow: [Step1] → [Step2] → [Step3] — posting logic creates [documents]
- T-codes: [code] for [purpose], [code] for monitoring

**Why This Design** (1 line):
"SAP designed it this way because... [business reason]"

**What Breaks** (1 line):
"If misconfigured, you'll see [error/symptom] — I've debugged this by checking [table/config]"

**Trade-off Callout** (1 line, if relevant):
"The trade-off here is standard vs custom — I recommend [choice] because..."

**Result/Metric** (1 line, from resume if available):
"At [client], this reduced [X] by [Y]%" OR "This handled [volume] documents daily"

**Follow-up Ready** (1 line):
"If you want, I can go deeper into [related topic]..."

## FORMATTING RULES FOR SPEAKABILITY:

1. Write as SPOKEN sentences, not bullet points
   ❌ "• Configure MRP Type in MM01"
   ✅ "First, I configure the MRP Type in MM01 — typically PD for MRP-driven planning"

2. Connect technical terms naturally
   ❌ "MIGO, MIRO, GR/IR"
   ✅ "After goods receipt in MIGO, I run MIRO for invoice verification, then clear GR/IR in F.13"

3. Use transition phrases
   - "The key thing here is..."
   - "What's critical to understand is..."
   - "The way SAP handles this is..."
   - "In production, what we monitor is..."
   - "The gotcha here is..."

4. Numbers and specifics build authority
   - "I've configured this across 4 company codes"
   - "This handled 50,000 line items daily"
   - "Reduced month-end close from 5 days to 2"

5. Show cross-module awareness (1 line)
   - "This ties into FI through the automatic account determination in OBYC"
   - "On the SD side, this triggers billing due list via VF04"

## TONE:
- Confident, not arrogant
- Technical but conversational
- Energetic but composed
- Consultant speaking to a peer, not lecturing

## CONTEXT HANDLING:

**If resume context IS relevant:**
- Lead with specific project/client experience
- Use exact metrics and achievements
- "At [client], I implemented this and achieved [result]"

**If resume context is NOT relevant (fallback):**
- Lead with general SAP best practice
- "The standard approach in S/4 HANA is..."
- "Based on my consulting experience across implementations..."
- Still give full technical depth
- Mention you can elaborate with specific examples if needed

## EXAMPLE OUTPUT:

Question: "How do you handle intercompany stock transfers?"

---

"So intercompany STO is something I've set up multiple times — most recently at [client] across 4 company codes.

The setup starts in config — SPRO, Materials Management, Purchasing, then define shipping data between plants. The critical piece is the internal customer and vendor master — each plant needs a vendor representing the supplying plant, and vice versa for the customer.

For the process flow: it kicks off with ME21N creating the STO with doc type UB, then the supplying plant does the delivery via VL10B, goods issue posts in the sending company code, goods receipt in MIGO posts in the receiving company code — and here's the key — SAP automatically creates the billing document and intercompany invoice through the SD-MM integration.

The account determination flows through OBYC for the inventory postings and VKOA on the SD side for the billing. What breaks? Usually it's the pricing procedure — if the internal pricing isn't set up in the intercompany billing type, the invoice fails silently in VF04.

At [client], we processed about 2,000 STOs monthly across entities, and I set up a Z-report to flag any stuck in the GR/IR clearing account past 48 hours.

I can go deeper into the account flows or the EDI setup if you'd like."

---

That answer can be spoken verbatim. Notice:
- Natural flow, not bullet points
- Tech terms woven into sentences
- Specific t-codes with context
- Error scenario included
- Metric at the end
- Follow-up offer

## WHAT NOT TO DO:
❌ Generic HR-speak: "I'm a team player who communicates well"
❌ Bullet point dumps that can't be spoken
❌ Over-explaining basics: "SAP stands for Systems Applications and Products..."
❌ Uncertain language: "I think maybe...", "I'm not sure but..."
❌ Making up fake client names or metrics not in resume
"""


DEFAULT_BULLET_SYSTEM_PROMPT = """You are an interview answer assistant generating quick-reference bullet points.

## YOUR TASK:
Generate exactly 2-3 concise bullet points that capture the essential answer to an interview question.

## FORMAT RULES:
- Exactly 2-3 bullet points, no more, no less
- Each bullet: 1-2 sentences maximum
- Start each bullet with "•"
- Focus on: key terms, t-codes, config paths, critical concepts
- This is for quick scanning, NOT for reading aloud

## CONTENT FOCUS:
- Technical essentials only
- Specific SAP terms, transactions, tables when relevant
- Key metrics or achievements from context
- The "what" and "how", skip the "why" details

## EXAMPLE:

Question: "How do you handle intercompany stock transfers?"

• Config: SPRO → MM → Purchasing → shipping data between plants; requires internal customer/vendor masters per plant
• Process: ME21N (STO doc type UB) → VL10B (delivery) → MIGO GI/GR → auto-billing via SD-MM integration
• Critical: Pricing procedure must be set in intercompany billing type or invoices fail silently in VF04

## CONTEXT HANDLING:
If relevant context exists, include specific client names, metrics, or achievements.
If no relevant context, use general SAP best practices.
"""


DEFAULT_SCRIPT_SYSTEM_PROMPT = """You are an AI interview copilot generating speakable interview scripts.

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
If no relevant context, use "In my experience..." or "The standard approach is..." framing.
"""


DEFAULT_TONE_INSTRUCTIONS = {
    "professional": "Use formal but warm language. Sound composed and authoritative. Speak as a senior consultant to a peer.",
    "casual": "Use relaxed, friendly language. Sound approachable and conversational. Speak as if chatting with a colleague.",
    "confident": "Use assertive, direct language. Sound self-assured and commanding. Speak with energy and conviction."
}


# Config helper functions
def _get_config() -> dict:
    """Get cached prompts config, loading if needed."""
    global _prompts_config
    if _prompts_config is None:
        _prompts_config = load_prompts_config()
    return _prompts_config


def reload_prompts_config() -> None:
    """Force reload prompts config from YAML file."""
    global _prompts_config
    _prompts_config = load_prompts_config()


def get_prompt(name: str) -> str:
    """Get prompt by name from config with fallback to default."""
    config = _get_config()
    prompts = config.get("prompts", {})

    # Map config names to default constants
    defaults = {
        "classification": DEFAULT_CLASSIFICATION_PROMPT,
        "bullet_system": DEFAULT_BULLET_SYSTEM_PROMPT,
        "script_system": DEFAULT_SCRIPT_SYSTEM_PROMPT,
        "star_system": DEFAULT_STAR_SYSTEM_PROMPT,
    }

    return prompts.get(name, defaults.get(name, ""))


def get_tone_instruction(tone: str) -> str:
    """Get tone instruction text from config."""
    config = _get_config()
    tones = config.get("tones", DEFAULT_TONE_INSTRUCTIONS)
    return tones.get(tone, tones.get("professional", DEFAULT_TONE_INSTRUCTIONS["professional"]))


def get_default_job_context() -> str:
    """Get default job context from config."""
    config = _get_config()
    return config.get("job_context", "")


def get_default_tone() -> str:
    """Get default tone from config."""
    config = _get_config()
    return config.get("default_tone", "professional")


def get_available_tones() -> list[str]:
    """Get list of available tone names from config."""
    config = _get_config()
    tones = config.get("tones", DEFAULT_TONE_INSTRUCTIONS)
    return list(tones.keys())


def generate_star_response(question: str, context_chunks: list[dict], job_context: str = "") -> Generator[str, None, None]:
    """
    Generate a SAP interview response using retrieved context.
    Falls back to general SAP knowledge if context is not relevant.
    """
    api_key = get_api_key()
    if not api_key:
        raise RuntimeError("OpenAI API key not configured. Run the GUI for setup instructions.")
    openai_client = OpenAI(api_key=api_key)

    # Check if we have relevant context
    has_relevant_context = (
        len(context_chunks) > 0 and
        any(chunk.get('similarity_score', 0) > 0.25 for chunk in context_chunks)
    )

    # Format context
    if has_relevant_context:
        context_text = "\n\n".join(
            f"[{chunk['source_file']}]:\n{chunk['text']}"
            for chunk in context_chunks
            if chunk.get('similarity_score', 0) > 0.2
        )
        context_section = f"""
CANDIDATE'S EXPERIENCE (use this to personalize):
{context_text}
"""
    else:
        context_section = """
CANDIDATE'S EXPERIENCE: No directly matching experience found.
Use general SAP best practices and consulting experience. Frame as "In my experience..." or "The standard approach is..."
"""

    # Add job context if available
    job_section = ""
    if job_context:
        job_section = f"""
JOB REQUIREMENTS (align answer to these):
{job_context}
"""

    user_message = f"""{context_section}
{job_section}

INTERVIEW QUESTION: {question}

Give a confident, technically rich answer the candidate can speak out loud verbatim. Follow the structure in your instructions."""

    stream = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": get_prompt("star_system") or DEFAULT_STAR_SYSTEM_PROMPT},
            {"role": "user", "content": user_message}
        ],
        stream=True,
        temperature=0.7  # Slight creativity for natural speech
    )

    for chunk in stream:
        if chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


def ask(question: str, job_context: str = "") -> Generator[str, None, None]:
    """Search context and generate streaming response."""
    chunks = search_context(question)
    return generate_star_response(question, chunks, job_context)


def generate_bullet_response(question: str, context_chunks: list[dict], job_context: str = "") -> Generator[str, None, None]:
    """
    Generate a concise 2-3 bullet point response using retrieved context.
    Uses gpt-4o-mini for speed since bullets are simple.
    """
    api_key = get_api_key()
    if not api_key:
        raise RuntimeError("OpenAI API key not configured. Run the GUI for setup instructions.")
    openai_client = OpenAI(api_key=api_key)

    # Check if we have relevant context
    has_relevant_context = (
        len(context_chunks) > 0 and
        any(chunk.get('similarity_score', 0) > 0.25 for chunk in context_chunks)
    )

    # Format context
    if has_relevant_context:
        context_text = "\n\n".join(
            f"[{chunk['source_file']}]:\n{chunk['text']}"
            for chunk in context_chunks
            if chunk.get('similarity_score', 0) > 0.2
        )
        context_section = f"""
CANDIDATE'S EXPERIENCE (use for personalization):
{context_text}
"""
    else:
        context_section = """
CANDIDATE'S EXPERIENCE: No directly matching experience found.
Use general SAP best practices.
"""

    # Add job context if available
    job_section = ""
    if job_context:
        job_section = f"""
JOB REQUIREMENTS:
{job_context}
"""

    user_message = f"""{context_section}
{job_section}

INTERVIEW QUESTION: {question}

Generate exactly 2-3 bullet points. Be concise and technical."""

    stream = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": get_prompt("bullet_system") or DEFAULT_BULLET_SYSTEM_PROMPT},
            {"role": "user", "content": user_message}
        ],
        stream=True,
        temperature=0.3  # More focused output for bullets
    )

    for chunk in stream:
        if chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


def ask_bullet(question: str, job_context: str = "") -> Generator[str, None, None]:
    """Search context and generate bullet point response."""
    chunks = search_context(question)
    return generate_bullet_response(question, chunks, job_context)


def generate_script_response(question: str, context_chunks: list[dict], job_context: str = "", tone: str = "professional") -> Generator[str, None, None]:
    """
    Generate a humanized, speakable interview script using retrieved context.
    Uses gpt-4o for quality since natural speech requires sophistication.
    """
    api_key = get_api_key()
    if not api_key:
        raise RuntimeError("OpenAI API key not configured. Run the GUI for setup instructions.")
    openai_client = OpenAI(api_key=api_key)

    # Get tone instruction from config
    tone_instruction = get_tone_instruction(tone)

    # Format the prompt with tone
    script_prompt = get_prompt("script_system") or DEFAULT_SCRIPT_SYSTEM_PROMPT
    system_prompt = script_prompt.format(tone_instruction=tone_instruction)

    # Check if we have relevant context
    has_relevant_context = (
        len(context_chunks) > 0 and
        any(chunk.get('similarity_score', 0) > 0.25 for chunk in context_chunks)
    )

    # Format context
    if has_relevant_context:
        context_text = "\n\n".join(
            f"[{chunk['source_file']}]:\n{chunk['text']}"
            for chunk in context_chunks
            if chunk.get('similarity_score', 0) > 0.2
        )
        context_section = f"""
CANDIDATE'S EXPERIENCE (personalize with this):
{context_text}
"""
    else:
        context_section = """
CANDIDATE'S EXPERIENCE: No directly matching experience found.
Use "In my experience..." framing with general SAP best practices.
"""

    # Add job context if available
    job_section = ""
    if job_context:
        job_section = f"""
JOB REQUIREMENTS (align answer to these):
{job_context}
"""

    user_message = f"""{context_section}
{job_section}

INTERVIEW QUESTION: {question}

Generate a natural, speakable answer (150-250 words) the candidate can read aloud verbatim."""

    stream = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
        stream=True,
        temperature=0.7  # Creative for natural flow
    )

    for chunk in stream:
        if chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


def ask_script(question: str, job_context: str = "", tone: str = "professional") -> Generator[str, None, None]:
    """Search context and generate script response with tone."""
    chunks = search_context(question)
    return generate_script_response(question, chunks, job_context, tone)


if __name__ == "__main__":
    for token in ask("Tell me about a time you led a difficult project"):
        print(token, end="", flush=True)
    print()
