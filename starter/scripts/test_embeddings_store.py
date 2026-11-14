"""Integration tests for Gemini Embeddings + PgVectorStore (Lab 06 Checkpoint)."""
import os
import sys
from pathlib import Path

# Ensure starter/ directory is in sys.path
starter_dir = Path(__file__).resolve().parent.parent
if str(starter_dir) not in sys.path:
    sys.path.insert(0, str(starter_dir))

import psycopg
from dotenv import dotenv_values

from src.embeddings import MyEmbedder
from src.store import PgVectorStore
from src.models import Chunk


def run_tests() -> None:
    env = dotenv_values(".env")
    db_url = env.get("DATABASE_URL")
    assert db_url, "DATABASE_URL not set in .env"

    print("=== 1. TEST REAL EMBEDDING OUTPUT & 768-DIMENSIONS ===")
    embedder = MyEmbedder()
    q_vec = embedder.embed_query("Lạm phát tại Việt Nam năm 2022")
    assert len(q_vec) == 768, f"Expected 768 dims, got {len(q_vec)}"
    print("Query embedding: OK (768 dims)")

    test_texts = [
        "Kinh tế vĩ mô Việt Nam ổn định với mức tăng trưởng GDP 7,72% trong quý II năm 2022.",
        "Giáo dục đại học đóng vai trò quan trọng trong việc nâng cao năng suất lao động.",
        "Phụ lục thống kê về các chỉ số kinh tế vĩ mô và xuất nhập khẩu năm 2022."
    ]
    doc_vecs = embedder.embed_documents(test_texts)
    assert len(doc_vecs) == 3, f"Expected 3 doc vectors, got {len(doc_vecs)}"
    assert all(len(v) == 768 for v in doc_vecs), "All doc vectors must be 768 dims"
    print("Document embeddings: OK (3 vectors, each 768 dims)")

    print("\n=== 2. TEST DATABASE SCHEMA CREATION ===")
    store = PgVectorStore(database_url=db_url, dimensions=768)
    store.create_schema()

    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT column_name, data_type, udt_name FROM information_schema.columns WHERE table_name = 'chunks';")
            cols = cur.fetchall()
            print("Table chunks columns:", [(c[0], c[2]) for c in cols])
            assert any(c[0] == "embedding" and c[2] == "vector" for c in cols), "vector column missing"
    print("Schema creation: OK")

    print("\n=== 3. TEST IDEMPOTENT UPSERT ===")
    chunks = [
        Chunk(chunk_id="test_c1", document_id="doc_test", source="test.pdf", page=1, text=test_texts[0], metadata={"section": "kinh_te_vi_mo"}),
        Chunk(chunk_id="test_c2", document_id="doc_test", source="test.pdf", page=2, text=test_texts[1], metadata={"section": "giao_duc_dai_hoc"}),
        Chunk(chunk_id="test_c3", document_id="doc_test", source="test.pdf", page=3, text=test_texts[2], metadata={"section": "phu_luc"}),
    ]

    store.upsert("strategy_test", chunks, doc_vecs)

    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM chunks WHERE strategy = 'strategy_test';")
            count_1 = cur.fetchone()[0]
            assert count_1 == 3, f"Expected 3, got {count_1}"

    # Re-upsert identical chunks
    store.upsert("strategy_test", chunks, doc_vecs)
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM chunks WHERE strategy = 'strategy_test';")
            count_2 = cur.fetchone()[0]
            assert count_2 == 3, f"Expected 3 (no duplicates), got {count_2}"
    print("Idempotent upsert: OK (Count remained 3)")

    print("\n=== 4. TEST PERSISTENCE AFTER RECONNECT ===")
    # New store instance reconnecting
    store2 = PgVectorStore(database_url=db_url, dimensions=768)
    results_all = store2.search("strategy_test", q_vec, top_k=3)
    assert len(results_all) == 3, f"Expected 3 results after reconnect, got {len(results_all)}"
    print("Persistence after reconnect: OK")

    print("\n=== 5. TEST TOP-3 RETRIEVAL & COSINE RANKING ===")
    for r in results_all:
        cid = r["chunk_id"]
        page = r["page"]
        score = r["score"]
        sec = r["metadata"].get("section")
        print(f"  Chunk {cid} | Page {page} | Score: {score:.4f} | Section: {sec}")
    # The first query was about macro economics ("Lạm phát tại Việt Nam năm 2022")
    assert results_all[0]["chunk_id"] == "test_c1", f"Expected test_c1 as top hit, got {results_all[0]['chunk_id']}"
    print("Top-3 retrieval & ranking: OK (test_c1 ranked #1)")

    print("\n=== 6. TEST METADATA FILTERING ===")
    results_filtered = store2.search("strategy_test", q_vec, top_k=3, filters={"section": "giao_duc_dai_hoc"})
    assert len(results_filtered) == 1, f"Expected 1 filtered result, got {len(results_filtered)}"
    assert results_filtered[0]["chunk_id"] == "test_c2", f"Expected test_c2, got {results_filtered[0]['chunk_id']}"
    assert results_filtered[0]["metadata"]["section"] == "giao_duc_dai_hoc"
    print("Metadata filtering: OK (Only giao_duc_dai_hoc returned)")

    print("\n=== 7. TEST STALE CHUNK CLEANUP ===")
    # Re-ingest with only test_c1 and test_c2 (removing test_c3)
    remaining_chunks = [chunks[0], chunks[1]]
    remaining_vecs = [doc_vecs[0], doc_vecs[1]]
    store2.upsert("strategy_test", remaining_chunks, remaining_vecs)

    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT chunk_id FROM chunks WHERE strategy = 'strategy_test' ORDER BY chunk_id;")
            ids = [row[0] for row in cur.fetchall()]
            print("Remaining chunk IDs in DB:", ids)
            assert ids == ["test_c1", "test_c2"], f"Expected ['test_c1', 'test_c2'], got {ids}"
    print("Stale chunk cleanup: OK (test_c3 was removed)")

    print("\n=== CLEANUP TEST DATA ===")
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM chunks WHERE strategy = 'strategy_test';")
        conn.commit()
    print("Cleanup: OK")
    print("\nALL 8 TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    run_tests()
