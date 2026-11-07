"""Zephyr RTOS document retrieval and RAG context construction."""

from __future__ import annotations

import re
from pathlib import Path


def _tokenize(text: str) -> set[str]:
    """Extract lowercase alphanumeric tokens from text."""
    return {w for w in re.findall(r"\w+", text.lower()) if len(w) > 2}


def retrieve_zephyr_context(
    query: str,
    max_results: int = 3,
    data_dir: str | Path | None = None,
) -> tuple[str, list[str]]:
    """Retrieve relevant Zephyr RTOS source files and documentation for a given query.

    Returns:
        (context_string, list_of_actual_source_paths)
    """
    root_paths = []
    if data_dir is not None:
        root_paths.append(Path(data_dir))
    else:
        # Check standard BoardBridge data locations
        raw_path = Path("data/raw")
        sample_path = Path("data/sample")
        if raw_path.is_dir():
            root_paths.append(raw_path)
        if sample_path.is_dir():
            root_paths.append(sample_path)

    query_tokens = _tokenize(query)
    candidates: list[tuple[float, str, str]] = []

    for search_root in root_paths:
        if not search_root.is_dir():
            continue
        for file_path in search_root.rglob("*"):
            if not file_path.is_file():
                continue
            # Relative path for display / citation
            try:
                rel_path = file_path.relative_to(search_root).as_posix()
            except ValueError:
                rel_path = file_path.as_posix()

            # Skip hidden files
            if file_path.name.startswith("."):
                continue

            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            file_tokens = _tokenize(rel_path + " " + content[:2000])
            overlap = query_tokens.intersection(file_tokens)
            score = len(overlap)

            # Boost matches in the filename or path
            for q in query_tokens:
                if q in rel_path.lower():
                    score += 5

            if score > 0:
                # Truncate content snippet for context window
                snippet = content[:1500].strip()
                candidates.append((score, rel_path, snippet))

    # Sort descending by score
    candidates.sort(key=lambda x: x[0], reverse=True)
    selected = candidates[:max_results]

    if not selected:
        # Fallback to general sample context if no explicit keyword matches
        default_file = Path("data/sample/bme280_README.rst")
        if default_file.is_file():
            snippet = default_file.read_text(encoding="utf-8", errors="ignore")[:1000]
            selected = [(1.0, "samples/sensor/bme280/README.rst", snippet)]

    context_parts: list[str] = []
    sources: list[str] = []
    for _, path_str, snippet in selected:
        sources.append(path_str)
        context_parts.append(f"--- Source: {path_str} ---\n{snippet}\n")

    context_text = "\n".join(context_parts)
    return context_text, sources


def build_rag_messages(
    query: str,
    context: str,
    sources: list[str],
) -> list[dict[str, str]]:
    """Build messages for the LLM with retrieved context and actual sources."""
    system_prompt = (
        "You are BoardBridge, an expert AI firmware engineering assistant for Zephyr RTOS. "
        "Use the provided Zephyr RTOS source context, devicetree bindings, driver samples, and "
        "configuration files to answer technical questions clearly and accurately. "
        "Cite the actual retrieved files and do not hallucinate fake file paths or non-existent drivers."
    )

    user_content = (
        f"Retrieved Zephyr RTOS Context:\n{context}\n\n"
        f"Verified Source References: {', '.join(sources) if sources else 'None'}\n\n"
        f"Question:\n{query}"
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

