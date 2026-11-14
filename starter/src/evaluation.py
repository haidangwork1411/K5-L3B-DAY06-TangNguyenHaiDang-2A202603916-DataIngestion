"""Evaluate retrieved evidence and preserve per-query traces."""
from __future__ import annotations

import re
import unicodedata
from typing import Any


def _normalize_text_for_eval(text: str) -> str:
    """Normalize whitespace and Unicode for evidence matching."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    # Collapse all whitespace and newlines into single spaces
    return re.sub(r"\s+", " ", text).strip().lower()


def evaluate_query(question: dict[str, Any], hits: list[dict[str, Any]]) -> dict[str, Any]:
    """Check source/page and enough gold evidence; keep hit@1 and hit@3 trace.

    Accept any documented alternative gold evidence. Do not infer human grounding
    or chunk coherence labels from exact string match.
    """
    gold_page = question.get("gold_page")
    gold_pages = question.get("gold_pages", [gold_page] if gold_page is not None else [])
    gold_source = question.get("gold_source_id") or question.get("source_id")
    raw_evidence = question.get("evidence_quote", "")
    norm_evidence = _normalize_text_for_eval(raw_evidence)

    eval_hits: list[dict[str, Any]] = []
    hit_at_1 = False
    hit_at_3 = False
    matching_rank: int | None = None

    for rank_idx, hit in enumerate(hits):
        rank = rank_idx + 1
        page = hit.get("page")
        source = hit.get("document_id") or hit.get("source")
        text = hit.get("text", "")
        norm_text = _normalize_text_for_eval(text)

        # Page match check
        page_matches = (page in gold_pages) if gold_pages else True

        # Source match check (if gold_source provided)
        source_matches = True
        if gold_source and source:
            source_matches = (gold_source == source) or (gold_source in source) or (source in gold_source)

        # Evidence containment check
        evidence_matches = (norm_evidence in norm_text) if norm_evidence else True

        # Strict Hit definition per GUIDE.md:
        # chunk belongs to gold source and gold page AND contains gold evidence
        is_hit = bool(page_matches and source_matches and evidence_matches)

        eval_hits.append(
            {
                "rank": rank,
                "chunk_id": hit.get("chunk_id"),
                "document_id": hit.get("document_id"),
                "source": hit.get("source"),
                "page": page,
                "score": hit.get("score"),
                "metadata": hit.get("metadata", {}),
                "is_gold_page": page_matches,
                "contains_evidence": evidence_matches,
                "is_hit": is_hit,
                "text": text,
            }
        )

        if is_hit and matching_rank is None:
            matching_rank = rank

        if rank == 1 and is_hit:
            hit_at_1 = True

        if rank <= 3 and is_hit:
            hit_at_3 = True

    return {
        "question_id": question.get("id"),
        "split": question.get("split", "dev"),
        "type": question.get("type", "standard"),
        "question": question.get("question", ""),
        "expected_answer": question.get("expected_answer", ""),
        "gold_source_id": gold_source,
        "gold_page": gold_page,
        "evidence_quote": raw_evidence,
        "filter": question.get("filter"),
        "hit_at_1": hit_at_1,
        "hit_at_3": hit_at_3,
        "matching_rank": matching_rank,
        "hits": eval_hits,
    }


def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate Hit@1 and Evidence Hit@3 by strategy and dev/test split."""
    if not traces:
        return {"total": 0, "splits": {}}

    splits: dict[str, list[dict[str, Any]]] = {"all": traces, "dev": [], "test": []}
    for t in traces:
        s = t.get("split", "dev").lower()
        if s in splits:
            splits[s].append(t)
        else:
            splits[s] = [t]

    summary: dict[str, Any] = {
        "total_questions": len(traces),
        "splits": {},
    }

    for split_name, split_traces in splits.items():
        n = len(split_traces)
        if n == 0:
            summary["splits"][split_name] = {
                "count": 0,
                "hit_1_count": 0,
                "hit_1_ratio": "0/0",
                "hit_1_pct": 0.0,
                "hit_3_count": 0,
                "hit_3_ratio": "0/0",
                "hit_3_pct": 0.0,
                "failed_questions": [],
            }
            continue

        h1 = sum(1 for t in split_traces if t.get("hit_at_1", False))
        h3 = sum(1 for t in split_traces if t.get("hit_at_3", False))
        failed = [t["question_id"] for t in split_traces if not t.get("hit_at_3", False)]

        summary["splits"][split_name] = {
            "count": n,
            "hit_1_count": h1,
            "hit_1_ratio": f"{h1}/{n}",
            "hit_1_pct": round((h1 / n) * 100, 2),
            "hit_3_count": h3,
            "hit_3_ratio": f"{h3}/{n}",
            "hit_3_pct": round((h3 / n) * 100, 2),
            "failed_questions": failed,
        }

    return summary

