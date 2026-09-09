from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import chromadb
except Exception:
    chromadb = None


@dataclass(slots=True)
class HistoryRecord:
    row_id: int
    review_id: str
    source: str
    language: str
    title: str
    category: str
    severity: str
    recommendation: str
    issue_message: str
    code_excerpt: str
    metadata: dict[str, Any]
    created_at: str


class RecommendationHistoryStore:
    def __init__(
        self,
        sqlite_path: str = "data/recommendation_history.sqlite3",
        chroma_path: str = "data/chroma_history",
        collection_name: str = "recommendation_history",
    ) -> None:
        self.sqlite_path = sqlite_path
        self.chroma_path = chroma_path
        self.collection_name = collection_name
        self._ensure_dirs()
        self._init_sqlite()

        self._chroma_client: Any | None = None
        self._chroma_collection: Any | None = None
        self._vector_store_enabled = False

        if chromadb is not None:
            try:
                self._chroma_client = chromadb.PersistentClient(path=self.chroma_path)
                self._chroma_collection = self._chroma_client.get_or_create_collection(name=self.collection_name)
                self._vector_store_enabled = True
            except Exception:
                self._chroma_client = None
                self._chroma_collection = None
                self._vector_store_enabled = False

    @property
    def vector_store_enabled(self) -> bool:
        return self._vector_store_enabled

    def _ensure_dirs(self) -> None:
        Path(self.sqlite_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.chroma_path).mkdir(parents=True, exist_ok=True)

    def _conn(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.sqlite_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_sqlite(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS recommendation_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    review_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    language TEXT NOT NULL,
                    title TEXT NOT NULL,
                    category TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    recommendation TEXT NOT NULL,
                    issue_message TEXT NOT NULL,
                    code_excerpt TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_recommendation_history_created_at
                ON recommendation_history(created_at DESC)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_recommendation_history_source
                ON recommendation_history(source)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS review_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    review_id TEXT NOT NULL,
                    rating TEXT NOT NULL,
                    comment TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def add_feedback(self, review_id: str, rating: str, comment: str = "") -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO review_feedback (review_id, rating, comment) VALUES (?, ?, ?)",
                (review_id, rating, comment),
            )

    def add_findings(
        self,
        review_id: str,
        findings: list[dict[str, Any]],
        source: str,
        language: str = "python",
        extra_metadata: dict[str, Any] | None = None,
    ) -> int:
        if not findings:
            return 0

        rows_added = 0
        vector_ids: list[str] = []
        vector_docs: list[str] = []
        vector_meta: list[dict[str, Any]] = []
        vector_embeddings: list[list[float]] = []

        with self._conn() as conn:
            for index, finding in enumerate(findings):
                title = str(finding.get("rule_id", "GENERIC"))
                category = str(finding.get("category", "quality"))
                severity = str(finding.get("severity", "low"))
                recommendation = str(finding.get("recommendation", "Review this code block."))
                issue_message = str(finding.get("message", "Issue detected"))
                code_excerpt = str(finding.get("evidence", ""))
                metadata: dict[str, Any] = {
                    "line": finding.get("line"),
                    "path": finding.get("path"),
                }
                if extra_metadata:
                    metadata.update(extra_metadata)

                conn.execute(
                    """
                    INSERT INTO recommendation_history (
                        review_id, source, language, title, category, severity,
                        recommendation, issue_message, code_excerpt, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        review_id,
                        source,
                        language,
                        title,
                        category,
                        severity,
                        recommendation,
                        issue_message,
                        code_excerpt,
                        json.dumps(metadata, ensure_ascii=False),
                    ),
                )
                rows_added += 1

                document = (
                    f"Title: {title}\n"
                    f"Source: {source}\n"
                    f"Language: {language}\n"
                    f"Category: {category}\n"
                    f"Severity: {severity}\n"
                    f"Message: {issue_message}\n"
                    f"Recommendation: {recommendation}\n"
                    f"Evidence: {code_excerpt}"
                )
                vector_id = self._stable_vector_id(review_id=review_id, item_index=index, doc=document)
                vector_ids.append(vector_id)
                vector_docs.append(document)
                vector_meta.append(
                    {
                        "review_id": review_id,
                        "source": source,
                        "language": language,
                        "title": title,
                        "category": category,
                        "severity": severity,
                    }
                )
                vector_embeddings.append(self._hash_embedding(document))

        if self._vector_store_enabled and self._chroma_collection is not None and vector_ids:
            try:
                self._chroma_collection.upsert(
                    ids=vector_ids,
                    documents=vector_docs,
                    metadatas=vector_meta,
                    embeddings=vector_embeddings,
                )
            except Exception:
                pass

        return rows_added

    def list_history(self, limit: int = 50, source: str | None = None) -> list[dict[str, Any]]:
        cap = max(1, min(limit, 500))
        query = (
            "SELECT id, review_id, source, language, title, category, severity, recommendation, "
            "issue_message, code_excerpt, metadata_json, created_at "
            "FROM recommendation_history"
        )
        params: list[Any] = []
        if source:
            query += " WHERE source = ?"
            params.append(source)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(cap)

        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()

        return [self._row_to_dict(row) for row in rows]

    def search_similar(self, query_text: str, limit: int = 5) -> list[dict[str, Any]]:
        cap = max(1, min(limit, 20))
        query = (query_text or "").strip()
        if not query:
            return []

        if self._vector_store_enabled and self._chroma_collection is not None:
            try:
                result = self._chroma_collection.query(
                    query_embeddings=[self._hash_embedding(query)],
                    n_results=cap,
                )
                docs = result.get("documents", [[]])[0] if isinstance(result, dict) else []
                metas = result.get("metadatas", [[]])[0] if isinstance(result, dict) else []
                distances = result.get("distances", [[]])[0] if isinstance(result, dict) else []
                output: list[dict[str, Any]] = []
                for idx, doc in enumerate(docs):
                    meta = metas[idx] if idx < len(metas) and isinstance(metas[idx], dict) else {}
                    score = distances[idx] if idx < len(distances) else None
                    output.append(
                        {
                            "document": doc,
                            "metadata": meta,
                            "distance": score,
                        }
                    )
                return output
            except Exception:
                pass

        like_query = f"%{query}%"
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id, review_id, source, language, title, category, severity, recommendation,
                       issue_message, code_excerpt, metadata_json, created_at
                FROM recommendation_history
                WHERE recommendation LIKE ? OR issue_message LIKE ? OR category LIKE ? OR title LIKE ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (like_query, like_query, like_query, like_query, cap),
            ).fetchall()

        return [{"row": self._row_to_dict(row)} for row in rows]

    def summarize_for_prompt(self, query_text: str, limit: int = 3) -> str:
        results = self.search_similar(query_text=query_text, limit=limit)
        if not results:
            return ""

        lines: list[str] = ["Historical recommendations from prior reviews:"]
        for item in results:
            if "row" in item:
                row = item["row"]
                lines.append(
                    f"- [{row.get('severity', 'low')}] {row.get('title', 'GENERIC')}: "
                    f"{row.get('recommendation', '')}"
                )
                continue

            metadata = item.get("metadata", {}) if isinstance(item, dict) else {}
            document = str(item.get("document", ""))
            title = metadata.get("title", "GENERIC")
            severity = metadata.get("severity", "low")
            lines.append(f"- [{severity}] {title}: {document[:180]}")

        return "\n".join(lines)

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        metadata_json = row["metadata_json"] if "metadata_json" in row.keys() else "{}"
        try:
            metadata = json.loads(metadata_json or "{}")
        except Exception:
            metadata = {}

        return {
            "id": row["id"],
            "review_id": row["review_id"],
            "source": row["source"],
            "language": row["language"],
            "title": row["title"],
            "category": row["category"],
            "severity": row["severity"],
            "recommendation": row["recommendation"],
            "issue_message": row["issue_message"],
            "code_excerpt": row["code_excerpt"],
            "metadata": metadata,
            "created_at": row["created_at"],
        }

    def _hash_embedding(self, text: str, dimensions: int = 256) -> list[float]:
        vector = [0.0] * dimensions
        tokens = text.lower().split()
        if not tokens:
            return vector

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
            bucket = int(digest[:8], 16) % dimensions
            sign = 1.0 if int(digest[8:10], 16) % 2 == 0 else -1.0
            vector[bucket] += sign

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]

    def _stable_vector_id(self, review_id: str, item_index: int, doc: str) -> str:
        digest = hashlib.sha256(f"{review_id}:{item_index}:{doc}".encode("utf-8")).hexdigest()
        return digest[:32]


_store_singleton: RecommendationHistoryStore | None = None


def get_recommendation_history_store() -> RecommendationHistoryStore:
    global _store_singleton
    if _store_singleton is None:
        _store_singleton = RecommendationHistoryStore()
    return _store_singleton
