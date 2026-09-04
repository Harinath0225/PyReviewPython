from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.main import app


client = TestClient(app)
payload = {
    "code_snippet": "import subprocess\napi_key=\"secret\"\nsubprocess.run(\"ls\", shell=True)\n",
    "language": "python",
}
response = client.post("/api/v1/review", json=payload)
print(response.status_code)
body = response.json()
print(
    {
        "review_id": body.get("review_id"),
        "llm_provider": body.get("llm_provider"),
        "llm_model": body.get("llm_model"),
        "llm_fallback_used": body.get("llm_fallback_used"),
        "llm_fallback_reason": body.get("llm_fallback_reason"),
        "total_findings": body.get("total_findings"),
    }
)
