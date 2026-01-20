#!/usr/bin/env python3
"""
RAG retrieval module for Astra MVP.
Searches ChromaDB for relevant document chunks.
"""

from collections.abc import Generator

import chromadb
from openai import OpenAI
import json

from config import get_api_key

COLLECTION_NAME = "astra_docs"
EMBEDDING_MODEL = "text-embedding-3-small"
CLASSIFICATION_MODEL = "gpt-4o-mini"


def search_context(query: str, top_k: int = 5) -> list[dict]:
    """
    Search for relevant document chunks based on a query.

    1. Embed the query using OpenAI text-embedding-3-small
    2. Search ChromaDB for top_k similar chunks
    3. Return list of {text, source_file, similarity_score}
    """
    # Initialize clients
    api_key = get_api_key()
    if not api_key:
        raise RuntimeError("OpenAI API key not configured. Run the GUI for setup instructions.")
    openai_client = OpenAI(api_key=api_key)
    chroma_client = chromadb.PersistentClient(path="./chroma_db")

    # Get collection
    try:
        collection = chroma_client.get_collection(name=COLLECTION_NAME)
    except ValueError:
        return []

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


CLASSIFICATION_PROMPT = """You are an interview question classifier. Given text from an interviewer, determine:
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
                {"role": "system", "content": CLASSIFICATION_PROMPT},
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


STAR_SYSTEM_PROMPT = """You are an AI interview copilot for SAP Consultants, helping a candidate answer live interview questions in real-time.

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
            {"role": "system", "content": STAR_SYSTEM_PROMPT},
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


if __name__ == "__main__":
    for token in ask("Tell me about a time you led a difficult project"):
        print(token, end="", flush=True)
    print()
