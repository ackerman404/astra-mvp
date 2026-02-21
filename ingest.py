#!/usr/bin/env python3
"""
Document ingestion script for Astra MVP.
Reads documents from a folder, chunks them, embeds with OpenAI, and stores in ChromaDB.

Memory-safe: processes large PDFs page-by-page and upserts in batches.
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
import pdfplumber
from openai import OpenAI

from config import get_license_key, get_proxy_url

logger = logging.getLogger("astra.ingest")

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
COLLECTION_NAME = "astra_docs"
EMBEDDING_MODEL = "text-embedding-3-small"

# Max chunks to embed + upsert in one batch (keeps memory bounded)
UPSERT_BATCH_SIZE = 200

# Cross-platform path for ChromaDB
CHROMA_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chroma_db")


def read_txt_file(file_path: Path) -> str:
    """Read content from a .txt or .md file."""
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


def clean_pdf_text(text: str) -> str:
    """Clean and normalize extracted PDF text while preserving structure."""
    import re

    # Normalize whitespace but preserve newlines for structure
    lines = text.split('\n')
    cleaned_lines = []

    for line in lines:
        # Strip trailing whitespace but preserve leading (for indentation)
        line = line.rstrip()

        # Skip completely empty lines (but keep one for paragraph breaks)
        if not line:
            if cleaned_lines and cleaned_lines[-1] != '':
                cleaned_lines.append('')
            continue

        # Preserve bullet points and list markers
        # Common patterns: •, -, *, ▪, ●, ○, numbers with . or )
        bullet_pattern = r'^(\s*)([-•▪●○\*]|\d+[.\)])\s*'
        match = re.match(bullet_pattern, line)
        if match:
            # Ensure bullet points are properly formatted
            indent = match.group(1)
            rest = line[match.end():]
            line = f"{indent}• {rest}"

        cleaned_lines.append(line)

    # Join and clean up multiple blank lines
    text = '\n'.join(cleaned_lines)
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


def read_pdf_pages(file_path: Path) -> list[str]:
    """
    Read a PDF file page-by-page, returning a list of cleaned text per page.

    Uses simple text extraction (no layout mode) for large files to avoid
    excessive memory usage.
    """
    file_size_mb = file_path.stat().st_size / (1024 * 1024)
    use_layout = file_size_mb < 20  # Only use layout mode for files under 20MB

    page_texts = []

    with pdfplumber.open(file_path) as pdf:
        total_pages = len(pdf.pages)

        for page_num, page in enumerate(pdf.pages, 1):
            try:
                if use_layout:
                    page_text = page.extract_text(
                        layout=True,
                        x_density=7.25,
                        y_density=13
                    )
                else:
                    page_text = page.extract_text()

                if not page_text or not page_text.strip():
                    continue

                cleaned_text = clean_pdf_text(page_text)

                if cleaned_text:
                    if total_pages > 1:
                        page_texts.append(f"[Page {page_num}]\n{cleaned_text}")
                    else:
                        page_texts.append(cleaned_text)

            except Exception as e:
                logger.warning("Error extracting page %d of %s: %s", page_num, file_path.name, e)
                continue

    return page_texts


def read_file(file_path: Path) -> str:
    """Read content from a file based on its extension."""
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        pages = read_pdf_pages(file_path)
        return "\n\n".join(pages)
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
    """
    Get embeddings for a list of texts using OpenAI API.

    Batches requests to stay under OpenAI's token limits.
    """
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


def _upsert_batch(
    collection,
    openai_client: OpenAI,
    chunks: list[str],
    ids: list[str],
    metadatas: list[dict],
) -> int:
    """Embed and upsert a batch of chunks. Returns number of chunks upserted."""
    if not chunks:
        return 0
    embeddings = get_embeddings(openai_client, chunks)
    collection.upsert(
        ids=ids,
        embeddings=embeddings,
        documents=chunks,
        metadatas=metadatas,
    )
    return len(chunks)


def ingest_folder_with_progress(
    folder_path: str,
    progress_callback: Callable[[dict], None] | None = None
) -> dict:
    """
    Ingest all supported documents from a folder into ChromaDB with progress reporting.

    Memory-safe: processes PDFs page-by-page and upserts in batches of UPSERT_BATCH_SIZE.
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
    license_key = get_license_key()
    if not license_key:
        msg = "License key not configured. Activate your license in the app."
        report("error", message=msg, total_files=total_files, current_file_index=0,
               current_file_name="", current_file_chunks=0, total_chunks=0)
        return {"success": False, "total_files": total_files, "total_chunks": 0, "errors": [msg]}
    proxy_url = get_proxy_url()
    openai_client = OpenAI(api_key=license_key, base_url=proxy_url)

    # Initialize ChromaDB
    chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    collection = chroma_client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )

    total_chunks = 0

    for idx, file_path in enumerate(files):
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
                # --- Stream PDF page-by-page to keep memory low ---
                file_chunks = _ingest_pdf_streaming(
                    file_path, doc_type, collection, openai_client,
                    progress_callback is None
                )
            else:
                # Text/markdown files — read whole file (usually small)
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

                # Upsert in batches
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
            if not progress_callback:
                print(f"  Added {file_chunks} chunks to collection")

            # Free memory between files
            gc.collect()

        except Exception as e:
            error_msg = f"Error processing {file_path.name}: {e}"
            errors.append(error_msg)
            logger.exception("Ingestion error for %s", file_path.name)
            if not progress_callback:
                print(f"  {error_msg}")
            gc.collect()
            continue

    # Invalidate BM25 cache so hybrid search rebuilds index with new documents
    try:
        from rag import invalidate_bm25_cache
        invalidate_bm25_cache()
    except ImportError:
        pass

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
    Process a PDF page-by-page, chunking and upserting in batches.

    This avoids loading the entire extracted text + all embeddings into memory
    at once, which causes OOM crashes on large PDFs (100MB+).
    """
    file_size_mb = file_path.stat().st_size / (1024 * 1024)
    use_layout = file_size_mb < 20

    if verbose:
        mode = "layout" if use_layout else "fast"
        print(f"  PDF size: {file_size_mb:.1f}MB (using {mode} extraction)")

    # Accumulate chunks across pages, flushing in batches
    pending_chunks: list[str] = []
    pending_ids: list[str] = []
    pending_metas: list[dict] = []
    chunk_counter = 0
    total_file_chunks = 0

    with pdfplumber.open(file_path) as pdf:
        total_pages = len(pdf.pages)
        multi_page = total_pages > 1

        for page_num, page in enumerate(pdf.pages, 1):
            try:
                if use_layout:
                    page_text = page.extract_text(
                        layout=True, x_density=7.25, y_density=13
                    )
                else:
                    page_text = page.extract_text()

                if not page_text or not page_text.strip():
                    continue

                cleaned = clean_pdf_text(page_text)
                if not cleaned:
                    continue

                if multi_page:
                    cleaned = f"[Page {page_num}]\n{cleaned}"

                # Chunk this page's text
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
