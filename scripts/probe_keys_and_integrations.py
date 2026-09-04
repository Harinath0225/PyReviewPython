from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from google import genai

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.config import get_settings
from backend.app.main import app


def _safe_bool(value: str | None) -> bool:
    return bool(value and value.strip())


def main() -> None:
    load_dotenv()
    settings = get_settings()

    report: dict[str, Any] = {
        "env": {
            "GEMINI_API_KEY_present": _safe_bool(settings.gemini_api_key),
            "GITHUB_TOKEN_present": _safe_bool(settings.github_token),
            "LLM_PROVIDER": settings.llm_provider,
            "LLM_MODEL": settings.llm_model,
        },
        "gemini": {},
        "github": {},
        "backend": {},
    }

    # 1) Direct Gemini API check
    try:
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY not set")
        client = genai.Client(api_key=settings.gemini_api_key)
        response = client.models.generate_content(
            model=settings.llm_model,
            contents="Return exactly this text: ok",
        )
        text = (getattr(response, "text", "") or "").strip().lower()
        report["gemini"] = {
            "ok": True,
            "response_preview": text[:60],
        }
    except Exception as exc:
        report["gemini"] = {
            "ok": False,
            "error": str(exc),
        }

    # 2) Direct GitHub token check
    try:
        if not settings.github_token:
            raise RuntimeError("GITHUB_TOKEN not set")
        headers = {
            "Authorization": f"Bearer {settings.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "code-assist-integration-probe",
        }
        response = httpx.get("https://api.github.com/user", headers=headers, timeout=15.0)
        response.raise_for_status()
        data = response.json()
        report["github"] = {
            "ok": True,
            "login": data.get("login"),
        }
    except Exception as exc:
        report["github"] = {
            "ok": False,
            "error": str(exc),
        }

    # 3) Backend review endpoint check (Gemini integration path)
    try:
        client = TestClient(app)
        review_payload = {
            "code_snippet": "import subprocess\napi_key=\"secret\"\nsubprocess.run(\"ls\", shell=True)\n",
            "language": "python",
        }
        review_response = client.post("/api/v1/review", json=review_payload)
        data = review_response.json()
        report["backend"]["review"] = {
            "status_code": review_response.status_code,
            "llm_provider": data.get("llm_provider"),
            "llm_model": data.get("llm_model"),
            "llm_fallback_used": data.get("llm_fallback_used"),
            "llm_fallback_reason": data.get("llm_fallback_reason"),
            "total_findings": data.get("total_findings"),
        }

        history_response = client.get("/api/v1/review/history?limit=5")
        hdata = history_response.json()
        report["backend"]["history"] = {
            "status_code": history_response.status_code,
            "count": hdata.get("count"),
            "vector_store_enabled": hdata.get("vector_store_enabled"),
        }
    except Exception as exc:
        report["backend"]["error"] = str(exc)

    # 4) Optional: GitHub PR review dry-run through backend route
    # Set these optional vars in .env to enable this check:
    # GITHUB_TEST_OWNER, GITHUB_TEST_REPO, GITHUB_TEST_PULL
    test_owner = os.getenv("GITHUB_TEST_OWNER")
    test_repo = os.getenv("GITHUB_TEST_REPO")
    test_pull = os.getenv("GITHUB_TEST_PULL")
    if test_owner and test_repo and test_pull:
        try:
            client = TestClient(app)
            payload = {
                "owner": test_owner,
                "repo": test_repo,
                "pull_number": int(test_pull),
                "dry_run": True,
                "review_event": "COMMENT",
            }
            pr_response = client.post("/api/v1/review/github-pr", json=payload)
            pdata = pr_response.json()
            report["backend"]["github_pr_dry_run"] = {
                "status_code": pr_response.status_code,
                "status": pdata.get("status"),
                "mode": pdata.get("mode"),
                "fallback_used": pdata.get("fallback_used"),
                "fallback_reason": pdata.get("fallback_reason"),
                "total_findings": pdata.get("total_findings"),
            }
        except Exception as exc:
            report["backend"]["github_pr_dry_run"] = {
                "status_code": None,
                "error": str(exc),
            }
    else:
        report["backend"]["github_pr_dry_run"] = {
            "status_code": None,
            "skipped": True,
            "reason": "Set GITHUB_TEST_OWNER, GITHUB_TEST_REPO, and GITHUB_TEST_PULL in .env to run this check.",
        }

    print(report)


if __name__ == "__main__":
    main()
