#!/usr/bin/env python3
"""
Document ingestion script for Astra MVP.
Reads documents from a folder, chunks them, embeds with OpenAI, and stores in ChromaDB.

Uses pdfplumber for PDF extraction, processes page-by-page with batched upserts.
Runs in a subprocess from the GUI so crashes can't kill the main app.
"""
from __future__ import annotations

import argparse
import gc
import logging
import os
import sys
from pathlib import Path
from collections.abc import Callable

import chromadb
from pypdf import PdfReader
from openai import OpenAI

from config import get_license_key, get_proxy_url

logger = logging.getLogger("astra.ingest")

# In frozen windowed exe, configure file-based logging so crash diagnostics
# are preserved even if the process dies. The log file is written next to
# the exe (e.g. dist/Astra/ingest.log).
def _setup_frozen_logging():
    if not getattr(sys, 'frozen', False):
        return
    try:
        log_path = os.path.join(os.path.dirname(sys.executable), "ingest.log")
        handler = logging.FileHandler(log_path, mode='w', encoding='utf-8')
        handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s %(name)s: %(message)s'
        ))
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
    except Exception:
        pass  # Can't set up logging — continue without it

_setup_frozen_logging()

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
COLLECTION_NAME = "astra_docs"
EMBEDDING_MODEL = "text-embedding-3-small"

# Max chunks to embed in one OpenAI API call (keeps request size bounded)
UPSERT_BATCH_SIZE = 50

# Max chunks to upsert to ChromaDB in a single collection.upsert() call.
# chroma-hnswlib (C extension) crashes in PyInstaller frozen exes when the
# HNSW graph update processes too many vectors at once (GitHub #3947).
# Small sub-batches keep each C-level graph update manageable.
UPSERT_SUB_BATCH = 10

# Cross-platform path for ChromaDB.
# In a frozen exe, __file__ points to the PyInstaller temp extraction dir (_MEIxxxxxx),
# not the persistent install dir. Use sys.executable's directory instead so the DB
# persists across restarts (next to Astra.exe).
def _get_chroma_db_path() -> str:
    if getattr(sys, 'frozen', False):
        return os.path.join(os.path.dirname(sys.executable), "chroma_db")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "chroma_db")

CHROMA_DB_PATH = _get_chroma_db_path()


def read_txt_file(file_path: Path) -> str:
    """Read content from a .txt or .md file."""
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


def clean_pdf_text(text: str) -> str:
    """Clean and normalize extracted PDF text while preserving structure."""
    import re

    lines = text.split('\n')
    cleaned_lines = []

    for line in lines:
        line = line.rstrip()

        if not line:
            if cleaned_lines and cleaned_lines[-1] != '':
                cleaned_lines.append('')
            continue

        bullet_pattern = r'^(\s*)([-•▪●○\*]|\d+[.\)])\s*'
        match = re.match(bullet_pattern, line)
        if match:
            indent = match.group(1)
            rest = line[match.end():]
            line = f"{indent}• {rest}"

        cleaned_lines.append(line)

    text = '\n'.join(cleaned_lines)
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


def read_file(file_path: Path) -> str:
    """Read content from a file based on its extension."""
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        text_parts = []
        reader = PdfReader(file_path)
        total_pages = len(reader.pages)
        for page_num, page in enumerate(reader.pages, 1):
            try:
                page_text = page.extract_text()
                if not page_text or not page_text.strip():
                    continue
                cleaned = clean_pdf_text(page_text)
                if cleaned:
                    if total_pages > 1:
                        text_parts.append(f"[Page {page_num}]\n{cleaned}")
                    else:
                        text_parts.append(cleaned)
            except Exception as e:
                logger.warning("Error extracting page %d of %s: %s", page_num, file_path.name, e)
                continue
        return "\n\n".join(text_parts)
    elif suffix in (".txt", ".md"):
        return read_txt_file(file_path)
    else:
        raise ValueError(f"Unsupported file type: {suffix}")


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks."""
    if not text:
        return []

    chunks = []
    start = 0
    text_length = len(text)

    while start < text_length:
        end = start + chunk_size
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk)
        start = end - overlap

    return chunks


def get_embeddings(client: OpenAI, texts: list[str], batch_size: int = 500) -> list[list[float]]:
    """Get embeddings for a list of texts using OpenAI API."""
    all_embeddings = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=batch
        )
        all_embeddings.extend([item.embedding for item in response.data])

    return all_embeddings


def get_doc_type(file_path: Path) -> str:
    """Get document type from file extension."""
    suffix = file_path.suffix.lower()
    return {
        ".txt": "text",
        ".md": "markdown",
        ".pdf": "pdf"
    }.get(suffix, "unknown")


def _flush_logs():
    """Flush all log handlers so crash diagnostics are written to disk."""
    for handler in logger.handlers:
        try:
            handler.flush()
        except Exception:
            pass
    # Also flush root logger handlers
    for handler in logging.getLogger().handlers:
        try:
            handler.flush()
        except Exception:
            pass


def _upsert_batch(
    collection,
    openai_client: OpenAI,
    chunks: list[str],
    ids: list[str],
    metadatas: list[dict],
) -> int:
    """Embed and upsert a batch of chunks. Returns number of chunks upserted.

    Embeds all chunks in one OpenAI API call for efficiency, then upserts to
    ChromaDB in small sub-batches (UPSERT_SUB_BATCH at a time). This prevents
    chroma-hnswlib from crashing during HNSW graph updates in PyInstaller
    frozen exes, where the C extension is sensitive to large batch sizes.
    """
    if not chunks:
        return 0

    total = len(chunks)
    logger.debug("Embedding %d chunks...", len(chunks))
    _flush_logs()
    embeddings = get_embeddings(openai_client, chunks)
    logger.debug("Embeddings received (%d vectors, dim=%d)", len(embeddings), len(embeddings[0]) if embeddings else 0)
    _flush_logs()

    # Upsert in small sub-batches to avoid C-level crash in chroma-hnswlib.
    # The HNSW index update is the crash point — smaller batches keep each
    # native-code graph update manageable in the frozen exe environment.
    upserted = 0
    for start in range(0, total, UPSERT_SUB_BATCH):
        end = min(start + UPSERT_SUB_BATCH, total)
        batch_size = end - start
        logger.debug("Upserting sub-batch %d-%d of %d to ChromaDB...", start + 1, end, total)
        _flush_logs()

        try:
            collection.upsert(
                ids=ids[start:end],
                embeddings=embeddings[start:end],
                documents=chunks[start:end],
                metadatas=metadatas[start:end],
            )
            upserted += batch_size
            logger.debug("Sub-batch %d-%d upserted OK", start + 1, end)
        except Exception as e:
            logger.error("Upsert failed on sub-batch %d-%d: %s: %s", start + 1, end, type(e).__name__, e)
            _flush_logs()
            raise

        # Release memory between sub-batches — helps in constrained frozen exe
        gc.collect()

    logger.debug("Upsert complete for %d chunks", upserted)
    _flush_logs()
    return upserted


def ingest_folder_with_progress(
    folder_path: str,
    progress_callback: Callable[[dict], None] | None = None
) -> dict:
    """
    Ingest all supported documents from a folder into ChromaDB with progress reporting.

    Processes PDFs page-by-page and upserts in batches to keep memory bounded.
    """
    folder = Path(folder_path)
    errors: list[str] = []

    def report(stage: str, **kwargs):
        if progress_callback:
            progress_callback({"stage": stage, **kwargs})

    # Validate folder
    if not folder.exists():
        msg = f"Folder '{folder_path}' does not exist."
        report("error", message=msg, total_files=0, current_file_index=0,
               current_file_name="", current_file_chunks=0, total_chunks=0)
        return {"success": False, "total_files": 0, "total_chunks": 0, "errors": [msg]}

    if not folder.is_dir():
        msg = f"'{folder_path}' is not a directory."
        report("error", message=msg, total_files=0, current_file_index=0,
               current_file_name="", current_file_chunks=0, total_chunks=0)
        return {"success": False, "total_files": 0, "total_chunks": 0, "errors": [msg]}

    # Find all supported files
    supported_extensions = {".txt", ".md", ".pdf"}
    files = [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in supported_extensions]
    total_files = len(files)

    if not files:
        msg = f"No supported files (.txt, .md, .pdf) found in '{folder_path}'."
        report("scanning", message=msg, total_files=0, current_file_index=0,
               current_file_name="", current_file_chunks=0, total_chunks=0)
        if not progress_callback:
            print(msg)
        return {"success": True, "total_files": 0, "total_chunks": 0, "errors": []}

    # Report scanning complete
    report("scanning", message=f"Found {total_files} file(s) to process",
           total_files=total_files, current_file_index=0,
           current_file_name="", current_file_chunks=0, total_chunks=0)
    if not progress_callback:
        print(f"Found {total_files} file(s) to process.")

    # Initialize OpenAI client
    logger.info("Initializing OpenAI client...")
    license_key = get_license_key()
    if not license_key:
        msg = "License key not configured. Activate your license in the app."
        report("error", message=msg, total_files=total_files, current_file_index=0,
               current_file_name="", current_file_chunks=0, total_chunks=0)
        return {"success": False, "total_files": total_files, "total_chunks": 0, "errors": [msg]}
    proxy_url = get_proxy_url()
    openai_client = OpenAI(api_key=license_key, base_url=proxy_url)
    logger.info("OpenAI client ready (proxy: %s)", proxy_url)

    # Initialize ChromaDB (disable telemetry — posthog 6.0+ broke the API chromadb 0.6.x uses)
    logger.info("Initializing ChromaDB at %s", CHROMA_DB_PATH)
    chroma_client = chromadb.PersistentClient(
        path=CHROMA_DB_PATH,
        settings=chromadb.Settings(anonymized_telemetry=False),
    )
    logger.info("ChromaDB PersistentClient created")
    try:
        collection = chroma_client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={
                "hnsw:space": "cosine",
                # Pre-allocate HNSW index to avoid resize operations.
                # hnswlib's index resize (realloc + memcpy) segfaults in
                # PyInstaller frozen exes. Default batch_size=100 triggers
                # a resize at ~100 vectors, crashing ingestion. Setting a
                # large initial capacity avoids any resize during ingestion.
                "hnsw:batch_size": 50000,
                # Single-threaded HNSW operations — OpenMP threading in
                # hnswlib can misbehave in frozen exe environments.
                "hnsw:num_threads": 1,
            }
        )
    except (KeyError, Exception) as e:
        # Corrupted DB from older chromadb version — wipe and retry
        if "KeyError" in type(e).__name__ or "_type" in str(e):
            logger.warning("ChromaDB incompatible/corrupted, resetting: %s", e)
            import shutil
            shutil.rmtree(CHROMA_DB_PATH, ignore_errors=True)
            chroma_client = chromadb.PersistentClient(
                path=CHROMA_DB_PATH,
                settings=chromadb.Settings(anonymized_telemetry=False),
            )
            collection = chroma_client.get_or_create_collection(
                name=COLLECTION_NAME,
                metadata={
                    "hnsw:space": "cosine",
                    "hnsw:batch_size": 50000,
                    "hnsw:num_threads": 1,
                }
            )
        else:
            raise

    logger.info("Collection '%s' ready", COLLECTION_NAME)

    total_chunks = 0

    for idx, file_path in enumerate(files):
        logger.info("Processing file %d/%d: %s", idx + 1, total_files, file_path.name)
        report("processing", message=f"Processing {file_path.name}",
               total_files=total_files, current_file_index=idx,
               current_file_name=file_path.name, current_file_chunks=0,
               total_chunks=total_chunks)
        if not progress_callback:
            print(f"\nProcessing: {file_path.name}")

        try:
            suffix = file_path.suffix.lower()
            doc_type = get_doc_type(file_path)

            if suffix == ".pdf":
                file_chunks = _ingest_pdf_streaming(
                    file_path, doc_type, collection, openai_client,
                    progress_callback is None
                )
            else:
                content = read_txt_file(file_path)
                if not content.strip():
                    if not progress_callback:
                        print("  Skipping: Empty file")
                    continue

                chunks = chunk_text(content)
                file_chunks = len(chunks)
                if not progress_callback:
                    print(f"  Created {file_chunks} chunk(s)")

                if not chunks:
                    continue

                for batch_start in range(0, len(chunks), UPSERT_BATCH_SIZE):
                    batch_end = min(batch_start + UPSERT_BATCH_SIZE, len(chunks))
                    batch_chunks = chunks[batch_start:batch_end]
                    batch_ids = [f"{file_path.stem}_{i}" for i in range(batch_start, batch_end)]
                    batch_metas = [
                        {"source_file": file_path.name, "chunk_index": i, "doc_type": doc_type}
                        for i in range(batch_start, batch_end)
                    ]
                    _upsert_batch(collection, openai_client, batch_chunks, batch_ids, batch_metas)

            total_chunks += file_chunks
            logger.info("File complete: %s — %d chunks (total: %d)", file_path.name, file_chunks, total_chunks)
            if not progress_callback:
                print(f"  Added {file_chunks} chunks to collection")

            gc.collect()

        except Exception as e:
            error_msg = f"Error processing {file_path.name}: {e}"
            errors.append(error_msg)
            logger.exception("Ingestion error for %s: %s", file_path.name, e)
            if not progress_callback:
                print(f"  {error_msg}")
            gc.collect()
            continue

    # Invalidate BM25 cache so hybrid search rebuilds index with new documents
    logger.info("Invalidating BM25 cache...")
    try:
        from rag import invalidate_bm25_cache
        invalidate_bm25_cache()
    except ImportError:
        pass

    logger.info("Ingestion complete: %d files, %d chunks, %d errors", total_files, total_chunks, len(errors))

    # Report completion
    report("complete", message=f"Ingestion complete! {total_chunks} chunks added.",
           total_files=total_files, current_file_index=total_files - 1,
           current_file_name="", current_file_chunks=0, total_chunks=total_chunks)
    if not progress_callback:
        print(f"\nIngestion complete!")
        print(f"Total chunks added: {total_chunks}")
        print(f"Collection: {COLLECTION_NAME}")

    return {
        "success": len(errors) == 0,
        "total_files": total_files,
        "total_chunks": total_chunks,
        "errors": errors
    }


def _ingest_pdf_streaming(
    file_path: Path,
    doc_type: str,
    collection,
    openai_client: OpenAI,
    verbose: bool,
) -> int:
    """
    Process a PDF page-by-page using pdfplumber, chunking and upserting in batches.

    Each page is opened, extracted, and released individually to limit memory usage.
    Chunks are flushed to ChromaDB every UPSERT_BATCH_SIZE chunks.
    """
    file_size_mb = file_path.stat().st_size / (1024 * 1024)

    if verbose:
        print(f"  PDF size: {file_size_mb:.1f}MB")

    pending_chunks: list[str] = []
    pending_ids: list[str] = []
    pending_metas: list[dict] = []
    chunk_counter = 0
    total_file_chunks = 0

    reader = PdfReader(file_path)
    total_pages = len(reader.pages)
    multi_page = total_pages > 1

    for page_num_idx, page in enumerate(reader.pages):
        page_num = page_num_idx + 1
        try:
            page_text = page.extract_text()

            if not page_text or not page_text.strip():
                continue

            cleaned = clean_pdf_text(page_text)
            if not cleaned:
                continue

            if multi_page:
                cleaned = f"[Page {page_num}]\n{cleaned}"

            page_chunks = chunk_text(cleaned)

            for chunk in page_chunks:
                pending_chunks.append(chunk)
                pending_ids.append(f"{file_path.stem}_{chunk_counter}")
                pending_metas.append({
                    "source_file": file_path.name,
                    "chunk_index": chunk_counter,
                    "doc_type": doc_type,
                })
                chunk_counter += 1

            # Flush when we hit the batch size
            if len(pending_chunks) >= UPSERT_BATCH_SIZE:
                _upsert_batch(collection, openai_client,
                              pending_chunks, pending_ids, pending_metas)
                total_file_chunks += len(pending_chunks)
                if verbose:
                    print(f"  ... {total_file_chunks} chunks so far (page {page_num}/{total_pages})")
                pending_chunks.clear()
                pending_ids.clear()
                pending_metas.clear()
                gc.collect()

        except Exception as e:
            logger.warning("Error on page %d of %s: %s", page_num, file_path.name, e)
            continue

    # Flush remaining
    if pending_chunks:
        _upsert_batch(collection, openai_client,
                      pending_chunks, pending_ids, pending_metas)
        total_file_chunks += len(pending_chunks)

    if verbose:
        print(f"  Total: {total_file_chunks} chunks from {total_pages} pages")

    return total_file_chunks


def ingest_folder(folder_path: str) -> None:
    """Ingest all supported documents from a folder into ChromaDB."""
    result = ingest_folder_with_progress(folder_path, progress_callback=None)
    if not result["success"] and result["errors"]:
        first_error = result["errors"][0]
        if "does not exist" in first_error or "is not a directory" in first_error:
            print(f"Error: {first_error}")
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Ingest documents into ChromaDB with OpenAI embeddings."
    )
    parser.add_argument(
        "folder",
        type=str,
        help="Path to folder containing .txt, .pdf, or .md files"
    )

    args = parser.parse_args()
    ingest_folder(args.folder)


if __name__ == "__main__":
    main()
