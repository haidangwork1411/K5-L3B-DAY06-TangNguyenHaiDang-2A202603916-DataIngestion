"""Choose a real embedding provider (API or local) and implement this contract."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Protocol

from dotenv import dotenv_values


class Embedder(Protocol):
    model_name: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text, in the same order."""
        ...

    def embed_query(self, question: str) -> list[float]:
        """Return a query vector compatible with the stored document vectors."""
        ...


class MyEmbedder:
    """Gemini API embedding adapter implementing Embedder protocol with 768 dimensions."""

    def __init__(
        self,
        model_name: str = "gemini-embedding-001",
        api_key: str | None = None,
        dimensions: int = 768,
    ) -> None:
        self.model_name = model_name
        self.dimensions = dimensions

        # Resolve API key securely without exposing it
        resolved_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not resolved_key:
            env_path = Path(__file__).resolve().parent.parent / ".env"
            if env_path.exists():
                vals = dotenv_values(env_path)
                resolved_key = vals.get("GEMINI_API_KEY")

        if not resolved_key or not resolved_key.strip():
            raise ValueError(
                "GEMINI_API_KEY is missing or empty. Please set GEMINI_API_KEY in starter/.env or environment variables."
            )

        self._api_key = resolved_key.strip()

    @property
    def _clean_model_name(self) -> str:
        """Strip 'models/' prefix if present for URL path."""
        if self.model_name.startswith("models/"):
            return self.model_name[len("models/") :]
        return self.model_name

    @property
    def _full_model_name(self) -> str:
        """Ensure 'models/' prefix is present for JSON payload."""
        if self.model_name.startswith("models/"):
            return self.model_name
        return f"models/{self.model_name}"

    def _execute_request(self, url: str, payload: dict[str, Any], max_retries: int = 5) -> dict[str, Any]:
        """Send JSON POST request to Gemini API with retries and exponential backoff."""
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers={"Content-Type": "application/json"},
        )

        last_error: Exception | None = None
        for attempt in range(max_retries):
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                last_error = e
                # Mask key in error message to guarantee API key security
                masked_url = url.split("?key=")[0] + "?key=***"
                err_body = ""
                try:
                    err_body = e.read().decode("utf-8")
                except Exception:
                    pass

                if e.code == 429 and attempt < max_retries - 1:
                    # Attempt to extract precise retry delay from Gemini API response
                    sleep_time = 25.0
                    try:
                        err_json = json.loads(err_body)
                        # Check details for RetryInfo
                        for detail in err_json.get("error", {}).get("details", []):
                            if "retryDelay" in detail:
                                rd_str = str(detail["retryDelay"]).rstrip("s")
                                sleep_time = float(rd_str) + 2.0
                                break
                        else:
                            # Search in message string e.g. "Please retry in 20.77s"
                            msg = err_json.get("error", {}).get("message", "")
                            match = re.search(r"retry in ([\d\.]+)s", msg)
                            if match:
                                sleep_time = float(match.group(1)) + 2.0
                    except Exception:
                        sleep_time = (2 ** attempt) * 10.0 + 5.0

                    print(f"[Embedder] Rate limited (429). Waiting {sleep_time:.1f}s before retry {attempt + 1}/{max_retries}...")
                    time.sleep(sleep_time)
                    continue

                if e.code in (500, 503) and attempt < max_retries - 1:
                    sleep_time = (2 ** attempt) * 2.0 + 1.0
                    print(f"[Embedder] Server error ({e.code}). Waiting {sleep_time:.1f}s before retry {attempt + 1}/{max_retries}...")
                    time.sleep(sleep_time)
                    continue

                raise RuntimeError(
                    f"Gemini API HTTP {e.code} on {masked_url}: {e.reason}. Details: {err_body[:200]}"
                ) from e
            except urllib.error.URLError as e:
                last_error = e
                if attempt < max_retries - 1:
                    sleep_time = (2 ** attempt) * 2.0 + 1.0
                    time.sleep(sleep_time)
                    continue
                masked_url = url.split("?key=")[0] + "?key=***"
                raise RuntimeError(f"Gemini API network error on {masked_url}: {e.reason}") from e

        raise RuntimeError(f"Gemini API request failed after {max_retries} attempts: {last_error}")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text, in the same order."""
        if not texts:
            return []

        batch_size = 50
        all_embeddings: list[list[float]] = []
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self._clean_model_name}:batchEmbedContents?key={self._api_key}"
        )

        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i : i + batch_size]
            requests_payload = [
                {
                    "model": self._full_model_name,
                    "content": {"parts": [{"text": t}]},
                    "taskType": "RETRIEVAL_DOCUMENT",
                    "outputDimensionality": self.dimensions,
                }
                for t in batch_texts
            ]

            payload = {"requests": requests_payload}
            res = self._execute_request(url, payload)
            embeddings = res.get("embeddings", [])
            if len(embeddings) != len(batch_texts):
                raise RuntimeError(
                    f"Expected {len(batch_texts)} embeddings, but received {len(embeddings)}"
                )

            for emb in embeddings:
                vals = emb.get("values", [])
                if len(vals) != self.dimensions:
                    raise ValueError(
                        f"Expected vector dimension {self.dimensions}, got {len(vals)}"
                    )
                all_embeddings.append(vals)

        return all_embeddings

    def embed_query(self, question: str) -> list[float]:
        """Return a query vector compatible with the stored document vectors."""
        if not question.strip():
            raise ValueError("Query string cannot be empty")

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self._clean_model_name}:embedContent?key={self._api_key}"
        )
        payload = {
            "model": self._full_model_name,
            "content": {"parts": [{"text": question}]},
            "taskType": "RETRIEVAL_QUERY",
            "outputDimensionality": self.dimensions,
        }

        res = self._execute_request(url, payload)
        vals = res.get("embedding", {}).get("values", [])
        if len(vals) != self.dimensions:
            raise ValueError(
                f"Expected query vector dimension {self.dimensions}, got {len(vals)}"
            )

        return vals

