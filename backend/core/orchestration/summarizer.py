"""
Context summarization utilities for orchestration.

Two tiers:
  1. smart_truncate()        — sync, free, always available
  2. compress_for_context()  — async, uses LLM with smart_truncate fallback
"""
import re


def smart_truncate(text: str, max_chars: int = 3000) -> str:
    """
    Keep the head and tail of text, inserting an omission marker in the middle.
    Tries to break at sentence/paragraph boundaries rather than mid-word.
    """
    if len(text) <= max_chars:
        return text

    head_budget = max_chars * 2 // 3
    tail_budget = max_chars - head_budget - 60  # leave room for marker

    # Try to end head at a paragraph or sentence boundary
    head = text[:head_budget]
    for boundary in ("\n\n", "\n", ". ", "! ", "? "):
        idx = head.rfind(boundary)
        if idx > head_budget // 2:
            head = head[: idx + len(boundary)].rstrip()
            break

    # Try to start tail at a paragraph or sentence boundary
    tail_raw = text[-tail_budget:]
    for boundary in ("\n\n", "\n", ". ", "! ", "? "):
        idx = tail_raw.find(boundary)
        if idx != -1 and idx < tail_budget // 2:
            tail_raw = tail_raw[idx + len(boundary):].lstrip()
            break

    omitted = len(text) - len(head) - len(tail_raw)
    return f"{head}\n\n[...{omitted} characters omitted...]\n\n{tail_raw}"


async def compress_for_context(
    text: str,
    max_chars: int = 3000,
    purpose: str = "general",
    settings: dict | None = None,
    session_id: str | None = None,
    run_id: str | None = None,
) -> str:
    """
    Compress text to fit within max_chars.
    Tries LLM summarization first (10s timeout), falls back to smart_truncate.
    """
    if len(text) <= max_chars:
        return text

    if not settings:
        return smart_truncate(text, max_chars)

    try:
        import asyncio
        from core.llm_providers import generate_response, detect_mode_from_model

        model = settings.get("summarization_model") or settings.get("model", "mistral")
        mode = detect_mode_from_model(model)

        purpose_hints = {
            "research": "key findings, data points, sources, and conclusions",
            "code": "functions, classes, logic flow, and important implementation details",
            "evaluation": "assessment criteria, scores, issues found, and recommendations",
            "plan": "steps, decisions, goals, and constraints",
            "general": "the most important information",
        }
        focus = purpose_hints.get(purpose, purpose_hints["general"])

        sys_prompt = "You are a concise summarizer. Output only the summary, no preamble."
        prompt = (
            f"Summarize the following text in under {max_chars} characters.\n"
            f"Focus on preserving: {focus}.\n"
            f"Do not add commentary — output the summary only.\n\n"
            f"TEXT:\n{text}"
        )

        result = await asyncio.wait_for(
            generate_response(
                prompt_msg=prompt,
                sys_prompt=sys_prompt,
                mode=mode,
                current_model=model,
                current_settings=settings,
                session_id=session_id,
                source="orchestration_summarizer",
                run_id=run_id,
            ),
            timeout=10.0,
        )

        summary = result if isinstance(result, str) else ""

        if summary and len(summary) <= max_chars * 1.2:  # allow small overrun
            return summary.strip()

    except Exception:
        pass  # Fall through to smart_truncate

    return smart_truncate(text, max_chars)
