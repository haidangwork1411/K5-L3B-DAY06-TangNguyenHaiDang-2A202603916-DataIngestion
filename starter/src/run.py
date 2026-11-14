"""Pipeline entry point: Orchestrate Ingestion, Embedding, PgVectorStore and Evaluation."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

# Ensure starter/ directory is in sys.path
starter_dir = Path(__file__).resolve().parent.parent
if str(starter_dir) not in sys.path:
    sys.path.insert(0, str(starter_dir))

from dotenv import dotenv_values

from src.chunking import by_paragraph, fixed_size
from src.embeddings import MyEmbedder
from src.evaluation import evaluate_query, summarize
from src.ingestion import load_pdf
from src.models import Chunk, DocumentPage
from src.store import PgVectorStore


class PersistentCachedEmbedder:
    """Wrapper around MyEmbedder that caches embeddings on disk to minimize API calls and cost."""

    def __init__(self, embedder: MyEmbedder, cache_path: Path) -> None:
        self.embedder = embedder
        self.cache_path = cache_path
        self.cache: dict[str, list[float]] = {}
        self.api_call_count = 0
        self._load_cache()

    def _load_cache(self) -> None:
        if self.cache_path.exists():
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    self.cache = json.load(f)
            except Exception as e:
                print(f"[Warning] Could not load embedding cache: {e}")
                self.cache = {}

    def _save_cache(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self.cache, f)
        except Exception as e:
            print(f"[Warning] Could not save embedding cache: {e}")

    def _hash_key(self, prefix: str, text: str) -> str:
        content = f"{self.embedder.model_name}:{self.embedder.dimensions}:{prefix}:{text}"
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        results: list[list[float] | None] = [None] * len(texts)
        missing_indices: list[int] = []
        missing_texts: list[str] = []

        for idx, text in enumerate(texts):
            key = self._hash_key("doc", text)
            if key in self.cache:
                results[idx] = self.cache[key]
            else:
                missing_indices.append(idx)
                missing_texts.append(text)

        if missing_texts:
            print(f"[Embedder] Cache miss for {len(missing_texts)}/{len(texts)} document texts. Requesting Gemini API...")
            batch_size = 25
            total_batches = (len(missing_texts) + batch_size - 1) // batch_size
            for b_idx in range(total_batches):
                start_i = b_idx * batch_size
                end_i = min(start_i + batch_size, len(missing_texts))
                batch = missing_texts[start_i:end_i]
                sub_indices = missing_indices[start_i:end_i]

                self.api_call_count += 1
                batch_vecs = self.embedder.embed_documents(batch)

                for orig_idx, vec, text in zip(sub_indices, batch_vecs, batch):
                    results[orig_idx] = vec
                    key = self._hash_key("doc", text)
                    self.cache[key] = vec

                # Save immediately after each batch so progress is never lost
                self._save_cache()
                print(f"[Embedder] Batch {b_idx + 1}/{total_batches} ({len(batch)} chunks) saved to cache.")

                # Pace requests to respect free-tier RPM limit
                if b_idx < total_batches - 1:
                    time.sleep(5.0)

        return [r for r in results if r is not None]

    def embed_query(self, question: str) -> list[float]:
        key = self._hash_key("query", question)
        if key in self.cache:
            return self.cache[key]

        print(f"[Embedder] Cache miss for query '{question[:40]}...'. Requesting Gemini API...")
        self.api_call_count += 1
        vec = self.embedder.embed_query(question)
        self.cache[key] = vec
        self._save_cache()
        return vec


def locate_file(rel_paths: list[str]) -> Path:
    """Find the first existing path among relative candidates."""
    for rp in rel_paths:
        p = Path(rp)
        if p.exists():
            return p.resolve()
        p2 = starter_dir / rp
        if p2.exists():
            return p2.resolve()
        p3 = starter_dir.parent / rp
        if p3.exists():
            return p3.resolve()
    raise FileNotFoundError(f"None of candidate paths exist: {rel_paths}")


def update_experiment_log(
    csv_path: Path,
    summary_data: dict[str, Any],
    chunk_counts: dict[str, int],
    ingest_times: dict[str, float],
) -> None:
    """Update artifacts/experiment_log.csv with genuine results."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        [
            "strategy",
            "chunking",
            "chunk_size",
            "overlap",
            "metadata",
            "filter",
            "vectorizer",
            "hypothesis",
            "dev_hit1",
            "dev_hit3",
            "test_hit1",
            "test_hit3",
            "notes",
        ]
    ]

    strategies_meta = {
        "A": {
            "chunking": "fixed_size",
            "chunk_size": 800,
            "overlap": 100,
            "metadata": "document_id,source,page,section",
            "filter": "none",
            "hypothesis": "Fixed-size windows keep uniform chunk size but may slice semantic sentences.",
        },
        "B": {
            "chunking": "by_paragraph",
            "chunk_size": 1000,
            "overlap": 0,
            "metadata": "document_id,source,page,section",
            "filter": "none",
            "hypothesis": "Structure-aware paragraph chunking preserves coherent semantic units.",
        },
        "C": {
            "chunking": "by_paragraph",
            "chunk_size": 1000,
            "overlap": 0,
            "metadata": "document_id,source,page,section",
            "filter": "section",
            "hypothesis": "Reusing B chunks with metadata filtering narrows search scope for targeted questions.",
        },
    }

    for strat_name, meta in strategies_meta.items():
        s_data = summary_data.get(strat_name, {}).get("splits", {})
        dev_s = s_data.get("dev", {})
        test_s = s_data.get("test", {})

        dev_h1 = f"{dev_s.get('hit_1_count', 0)}/{dev_s.get('count', 0)} ({dev_s.get('hit_1_pct', 0.0)}%)"
        dev_h3 = f"{dev_s.get('hit_3_count', 0)}/{dev_s.get('count', 0)} ({dev_s.get('hit_3_pct', 0.0)}%)"
        test_h1 = f"{test_s.get('hit_1_count', 0)}/{test_s.get('count', 0)} ({test_s.get('hit_1_pct', 0.0)}%)"
        test_h3 = f"{test_s.get('hit_3_count', 0)}/{test_s.get('count', 0)} ({test_s.get('hit_3_pct', 0.0)}%)"

        c_cnt = chunk_counts.get(strat_name, 0)
        i_time = ingest_times.get(strat_name, 0.0)
        notes = f"chunks={c_cnt}; ingest_time={i_time:.2f}s; model=gemini-embedding-001 (768d)"

        rows.append(
            [
                strat_name,
                meta["chunking"],
                meta["chunk_size"],
                meta["overlap"],
                meta["metadata"],
                meta["filter"],
                "gemini-embedding-001 (768d)",
                meta["hypothesis"],
                dev_h1,
                dev_h3,
                test_h1,
                test_h3,
                notes,
            ]
        )

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(rows)


def main() -> None:
    print("=" * 70)
    print("VINUNI AI LAB 06 — END-TO-END PIPELINE & BENCHMARK EVALUATION")
    print("=" * 70)

    # 1. Environment & configuration setup
    env_path = starter_dir / ".env"
    if not env_path.exists():
        env_path = starter_dir.parent / ".env"
    env_vals = dotenv_values(env_path)

    db_url = env_vals.get("DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL not set in .env")

    gemini_key = env_vals.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not gemini_key or not gemini_key.strip():
        raise ValueError("GEMINI_API_KEY is missing or empty in .env")

    # Locate corpus and benchmark
    pdf_path = locate_file(["starter/data/taking_stock_aug_2022_vi.pdf", "data/taking_stock_aug_2022_vi.pdf"])
    benchmark_path = locate_file(["benchmark/questions.json", "../benchmark/questions.json"])

    print(f"[Config] PDF Corpus: {pdf_path}")
    print(f"[Config] Benchmark:  {benchmark_path}")

    with open(benchmark_path, "r", encoding="utf-8") as f:
        all_questions = json.load(f)

    dev_questions = [q for q in all_questions if q.get("split") == "dev"]
    test_questions = [q for q in all_questions if q.get("split") == "test"]

    print(f"[Benchmark] Loaded {len(all_questions)} total questions: {len(dev_questions)} dev, {len(test_questions)} test.")
    assert len(all_questions) >= 20, "Benchmark must contain at least 20 questions"
    assert len(dev_questions) >= 15, "Dev split must contain at least 15 questions"
    assert len(test_questions) >= 5, "Test split must contain at least 5 questions"

    # 2. Ingestion & Chunking
    doc_id = "worldbank-vietnam-taking-stock-aug-2022"
    source = "worldbank-vietnam-taking-stock-aug-2022"
    print("\n[Step 1/5] Ingesting PDF content pages...")
    t_ingest_start = time.time()
    pages = load_pdf(pdf_path, doc_id, source, only_useful=True)
    t_ingest_done = time.time()
    print(f"[Ingestion] Loaded {len(pages)} useful content pages in {t_ingest_done - t_ingest_start:.2f}s.")
    assert len(pages) >= 30, f"Corpus must have at least 30 useful content pages, got {len(pages)}"

    # Generate chunks
    print("\n[Step 2/5] Generating chunk sets for Strategy A and B...")
    chunks_a: list[Chunk] = []
    for p in pages:
        chunks_a.extend(fixed_size(p, size=800, overlap=100))

    chunks_b: list[Chunk] = []
    for p in pages:
        chunks_b.extend(by_paragraph(p, max_size=1000))

    # Strategy C reuses Strategy B chunks exactly
    chunks_c = chunks_b

    print(f"[Chunks] Strategy A (fixed_size 800/100):     {len(chunks_a)} chunks")
    print(f"[Chunks] Strategy B (by_paragraph max 1000):  {len(chunks_b)} chunks")
    print(f"[Chunks] Strategy C (reusing Strategy B):      {len(chunks_c)} chunks")

    chunk_counts = {
        "A": len(chunks_a),
        "B": len(chunks_b),
        "C": len(chunks_c),
    }

    # 3. Setup Persistent Store & Embedder
    store = PgVectorStore(database_url=db_url, dimensions=768)
    store.create_schema()

    cache_file = starter_dir / "results" / "embedding_cache.json"
    raw_embedder = MyEmbedder(model_name="gemini-embedding-001", api_key=gemini_key, dimensions=768)
    embedder = PersistentCachedEmbedder(embedder=raw_embedder, cache_path=cache_file)

    # 4. Ingest and Embed Document Chunks
    print("\n[Step 3/5] Ingesting and embedding document vectors into PgVectorStore...")
    ingest_times: dict[str, float] = {}

    # Strategy A
    print(f"[Ingest A] Processing {len(chunks_a)} chunks for Strategy A...")
    t0 = time.time()
    texts_a = [c.text for c in chunks_a]
    vecs_a = embedder.embed_documents(texts_a)
    store.upsert(strategy="A", chunks=chunks_a, vectors=vecs_a)
    ingest_times["A"] = time.time() - t0
    print(f"[Ingest A] Upserted {len(chunks_a)} chunks in {ingest_times['A']:.2f}s.")

    # Strategy B
    print(f"[Ingest B] Processing {len(chunks_b)} chunks for Strategy B...")
    t0 = time.time()
    texts_b = [c.text for c in chunks_b]
    vecs_b = embedder.embed_documents(texts_b)
    store.upsert(strategy="B", chunks=chunks_b, vectors=vecs_b)
    ingest_times["B"] = time.time() - t0
    print(f"[Ingest B] Upserted {len(chunks_b)} chunks in {ingest_times['B']:.2f}s.")

    # Strategy C reuses Strategy B document chunks in database directly (0 extra embed, 0 extra time)
    ingest_times["C"] = 0.0
    print("[Ingest C] Reusing Strategy B stored chunks and embeddings directly (0 duplicate API calls).")

    # 5. Execute Benchmark Queries
    print("\n[Step 4/5] Executing benchmark retrieval across Strategies A, B, and C...")
    traces_by_strategy: dict[str, list[dict[str, Any]]] = {"A": [], "B": [], "C": []}

    # Pre-embed queries using cache to guarantee identical vectors across A/B/C
    print("[Query Cache] Pre-caching query embeddings for all 20 questions...")
    query_vectors: dict[str, list[float]] = {}
    for q in all_questions:
        qid = q["id"]
        q_text = q["question"]
        query_vectors[qid] = embedder.embed_query(q_text)

    # Run Dev questions
    print("\n--- Running Development Set (15 questions) ---")
    for strat in ["A", "B", "C"]:
        for q in dev_questions:
            qid = q["id"]
            q_vec = query_vectors[qid]
            filter_param = q.get("filter") if strat == "C" else None
            hits = store.search(strategy=strat, query_vector=q_vec, top_k=3, filters=filter_param)
            trace = evaluate_query(question=q, hits=hits)
            trace["strategy"] = strat
            trace["filter_applied"] = filter_param
            traces_by_strategy[strat].append(trace)

    # Run Test questions
    print("--- Running Test Set (5 questions) ---")
    for strat in ["A", "B", "C"]:
        for q in test_questions:
            qid = q["id"]
            q_vec = query_vectors[qid]
            filter_param = q.get("filter") if strat == "C" else None
            hits = store.search(strategy=strat, query_vector=q_vec, top_k=3, filters=filter_param)
            trace = evaluate_query(question=q, hits=hits)
            trace["strategy"] = strat
            trace["filter_applied"] = filter_param
            traces_by_strategy[strat].append(trace)

    # 6. Summarize Metrics
    print("\n[Step 5/5] Computing retrieval metrics and exporting artifacts...")
    summary_results: dict[str, Any] = {}
    for strat in ["A", "B", "C"]:
        strat_traces = traces_by_strategy[strat]
        summary_results[strat] = summarize(strat_traces)
        summary_results[strat]["chunk_count"] = chunk_counts[strat]
        summary_results[strat]["ingest_time_seconds"] = round(ingest_times[strat], 2)

    # Write traces and summary to both starter/results and root results/
    output_dirs = [starter_dir / "results", starter_dir.parent / "results"]
    for out_dir in output_dirs:
        out_dir.mkdir(parents=True, exist_ok=True)
        for strat in ["A", "B", "C"]:
            with open(out_dir / f"traces_strategy_{strat}.json", "w", encoding="utf-8") as f:
                json.dump(traces_by_strategy[strat], f, ensure_ascii=False, indent=2)

        with open(out_dir / "summary_metrics.json", "w", encoding="utf-8") as f:
            json.dump(
                {
                    "model": "gemini-embedding-001",
                    "dimensions": 768,
                    "total_api_calls_made": embedder.api_call_count,
                    "chunk_counts": chunk_counts,
                    "ingest_times": ingest_times,
                    "strategies": summary_results,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

    # Update artifacts/experiment_log.csv
    csv_paths = [starter_dir.parent / "artifacts" / "experiment_log.csv", starter_dir / "artifacts" / "experiment_log.csv"]
    for cp in csv_paths:
        update_experiment_log(cp, summary_results, chunk_counts, ingest_times)
        print(f"[Artifacts] Updated {cp}")

    # Print Final Summary Table
    print("\n" + "=" * 70)
    print("FINAL RETRIEVAL ACCURACY REPORT (Hit@1 & Evidence Hit@3)")
    print("=" * 70)
    print(f"{'Strategy':<10} | {'Split':<6} | {'Hit@1 (n/N)':<15} | {'Evidence Hit@3 (n/N)':<22} | {'Chunks':<8}")
    print("-" * 70)

    for strat in ["A", "B", "C"]:
        s_splits = summary_results[strat]["splits"]
        for split_key in ["dev", "test"]:
            sp = s_splits[split_key]
            h1_str = f"{sp['hit_1_ratio']} ({sp['hit_1_pct']}%)"
            h3_str = f"{sp['hit_3_ratio']} ({sp['hit_3_pct']}%)"
            c_cnt = chunk_counts[strat]
            print(f"{strat:<10} | {split_key:<6} | {h1_str:<15} | {h3_str:<22} | {c_cnt:<8}")
        print("-" * 70)

    print(f"\n[API Usage] Total actual Gemini API calls made: {embedder.api_call_count}")
    print("[Success] All traces, summary metrics, and artifacts successfully saved!")


if __name__ == "__main__":
    main()
