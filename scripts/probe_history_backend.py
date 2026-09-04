from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.main import app


client = TestClient(app)

review_payload = {
    "code_snippet": "import subprocess\napi_key=\"secret\"\nsubprocess.run(\"ls\", shell=True)\nassert True\n",
    "language": "python",
}
review_response = client.post("/api/v1/review", json=review_payload)
review_data = review_response.json()

history_response = client.get("/api/v1/review/history?limit=5")
history_data = history_response.json()

search_response = client.get("/api/v1/review/history?query=unsafe%20execution&n_results=3")
search_data = search_response.json()

print({
    "review_status": review_response.status_code,
    "review_id": review_data.get("review_id"),
    "llm_provider": review_data.get("llm_provider"),
    "llm_model": review_data.get("llm_model"),
    "llm_fallback_used": review_data.get("llm_fallback_used"),
    "history_status": history_response.status_code,
    "history_count": history_data.get("count"),
    "vector_store_enabled": history_data.get("vector_store_enabled"),
    "similar_count": len(search_data.get("similar", [])),
})
