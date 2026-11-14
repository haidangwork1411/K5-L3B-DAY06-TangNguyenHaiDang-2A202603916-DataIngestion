"""Store and search vectors using PostgreSQL + pgvector."""
from __future__ import annotations

import json
from typing import Any

import psycopg

from .models import Chunk


class PgVectorStore:
    def __init__(self, database_url: str, dimensions: int) -> None:
        """Retain connection settings; validate model dimensions."""
        if dimensions <= 0:
            raise ValueError(f"dimensions must be positive, got {dimensions}")
        self.database_url = database_url
        self.dimensions = dimensions

    def _connect(self) -> psycopg.Connection:
        """Create a new PostgreSQL connection."""
        return psycopg.connect(self.database_url)

    def create_schema(self) -> None:
        """Create table with vector column and source/page/filter metadata."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                # Enable pgvector extension
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")

                # Create chunks table
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS chunks (
                        strategy VARCHAR(32) NOT NULL,
                        chunk_id VARCHAR(128) NOT NULL,
                        document_id VARCHAR(128) NOT NULL,
                        source TEXT NOT NULL,
                        page INTEGER NOT NULL,
                        text TEXT NOT NULL,
                        metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                        embedding vector({self.dimensions}) NOT NULL,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (strategy, chunk_id)
                    );
                    """
                )

                # Create indexes for filtering and vector search
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_chunks_strategy ON chunks (strategy);"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_chunks_strategy_doc ON chunks (strategy, document_id);"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_chunks_metadata ON chunks USING gin (metadata);"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_chunks_embedding_cosine ON chunks USING hnsw (embedding vector_cosine_ops);"
                )
            conn.commit()

    def upsert(self, strategy: str, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        """Validate lengths/dimensions, write stable IDs without duplicates, and remove stale chunks."""
        if len(chunks) != len(vectors):
            raise ValueError(
                f"Length mismatch: {len(chunks)} chunks vs {len(vectors)} vectors"
            )

        if not chunks:
            return

        for idx, vec in enumerate(vectors):
            if len(vec) != self.dimensions:
                raise ValueError(
                    f"Vector at index {idx} has dimension {len(vec)}, expected {self.dimensions}"
                )

        # Group valid chunk_ids by document_id for stale chunk cleanup
        doc_chunks_map: dict[str, list[str]] = {}
        for c in chunks:
            doc_chunks_map.setdefault(c.document_id, []).append(c.chunk_id)

        upsert_records = [
            (
                strategy,
                c.chunk_id,
                c.document_id,
                c.source,
                c.page,
                c.text,
                json.dumps(c.metadata, ensure_ascii=False),
                json.dumps(vec),
            )
            for c, vec in zip(chunks, vectors)
        ]

        with self._connect() as conn:
            with conn.cursor() as cur:
                # 1. Idempotent upsert
                upsert_sql = """
                    INSERT INTO chunks (
                        strategy, chunk_id, document_id, source, page, text, metadata, embedding, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::vector, CURRENT_TIMESTAMP)
                    ON CONFLICT (strategy, chunk_id) DO UPDATE SET
                        document_id = EXCLUDED.document_id,
                        source = EXCLUDED.source,
                        page = EXCLUDED.page,
                        text = EXCLUDED.text,
                        metadata = EXCLUDED.metadata,
                        embedding = EXCLUDED.embedding,
                        updated_at = CURRENT_TIMESTAMP;
                """
                cur.executemany(upsert_sql, upsert_records)

                # 2. Stale-chunk cleanup: delete chunks for these documents that are not in the new batch
                cleanup_sql = """
                    DELETE FROM chunks
                    WHERE strategy = %s
                      AND document_id = %s
                      AND chunk_id != ALL(%s);
                """
                for doc_id, valid_ids in doc_chunks_map.items():
                    cur.execute(cleanup_sql, (strategy, doc_id, valid_ids))

            conn.commit()

    def search(
        self,
        strategy: str,
        query_vector: list[float],
        top_k: int = 3,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Filter permitted metadata in SQL, rank by cosine distance, return top-k."""
        if len(query_vector) != self.dimensions:
            raise ValueError(
                f"Query vector dimension {len(query_vector)} != store dimension {self.dimensions}"
            )

        if top_k <= 0:
            return []

        target_strategy = strategy
        # Strategy B and C share identical chunks/embeddings; C differs only by metadata filter
        if strategy == "C":
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 FROM chunks WHERE strategy = 'C' LIMIT 1;")
                    if not cur.fetchone():
                        target_strategy = "B"

        where_clauses = ["strategy = %s"]
        params: list[Any] = [target_strategy]

        if filters:
            for k, v in filters.items():
                if v is None:
                    continue
                if k in ("document_id", "source", "page"):
                    where_clauses.append(f"{k} = %s")
                    params.append(v)
                else:
                    where_clauses.append("metadata->>%s = %s")
                    params.extend([str(k), str(v)])

        where_sql = " AND ".join(where_clauses)
        q_vec_json = json.dumps(query_vector)

        sql = f"""
            SELECT 
                chunk_id,
                document_id,
                source,
                page,
                text,
                metadata,
                1 - (embedding <=> %s::vector) AS score
            FROM chunks
            WHERE {where_sql}
            ORDER BY embedding <=> %s::vector ASC
            LIMIT %s;
        """
        exec_params = [q_vec_json] + params + [q_vec_json, top_k]

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, exec_params)
                rows = cur.fetchall()

        results: list[dict[str, Any]] = []
        for r in rows:
            meta = r[5] if isinstance(r[5], dict) else json.loads(r[5])
            results.append(
                {
                    "chunk_id": r[0],
                    "document_id": r[1],
                    "source": r[2],
                    "page": r[3],
                    "text": r[4],
                    "metadata": meta,
                    "score": float(r[6]),
                }
            )

        return results

