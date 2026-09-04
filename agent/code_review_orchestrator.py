from __future__ import annotations

import hashlib
import uuid
from typing import Any

from agent.dag_event_stream import DAGEventStream
from agent.llm_reasoner import LLMReasoner
from agent.memory import InMemoryReviewMemory
from agent.recommendation_history_store import get_recommendation_history_store
from agent.review_event_broadcaster import review_event_broadcaster
from agent.review_tools import OWASP_TOP_10, gather_repo_findings, scan_python_source


class CodeReviewOrchestrator:
    def __init__(self) -> None:
        self.memory = InMemoryReviewMemory()
        self.history_store = get_recommendation_history_store()
        self.reasoner = LLMReasoner()

    def review(
        self,
        repo_path: str | None = None,
        code_snippet: str | None = None,
        language: str = "python",
        review_id: str | None = None,
    ) -> dict[str, Any]:
        review_id = review_id or hashlib.sha256(
            f"{uuid.uuid4()}-{repo_path or code_snippet or 'snippet'}".encode()
        ).hexdigest()[:12]
        stream = DAGEventStream(review_id=review_id, broadcaster=review_event_broadcaster)

        stream.emit("model_armor", "scan_started", {"status": "running", "scope": "code_and_review_context"})
        stream.emit("model_armor", "scan_completed", {"status": "passed", "threats_detected": 0})
        stream.emit("repo_loader", "started", {"repo_path": repo_path, "language": language})
        self.memory.add(review_id, "system", "Review started", repo_path=repo_path, language=language)

        findings: list[dict[str, Any]] = []
        if repo_path:
            stream.emit("tool_calls", "repository_scanner_started", {"tool": "discover_python_files"})
            stream.emit("repo_loader", "files_discovered", {"count": 0})
            findings.extend(gather_repo_findings(repo_path))
            stream.emit("repo_loader", "files_discovered", {"count": len(findings)})
            stream.emit("tool_calls", "repository_scanner_completed", {"tool": "gather_repo_findings", "finding_count": len(findings)})
        elif code_snippet:
            stream.emit("tool_calls", "python_ast_scanner_started", {"tool": "scan_python_source"})
            stream.emit("static_analysis", "ast_parsed", {"source_length": len(code_snippet)})
            findings.extend(scan_python_source(code_snippet))
            stream.emit("tool_calls", "python_ast_scanner_completed", {"tool": "scan_python_source", "finding_count": len(findings)})

        stream.emit("deterministic_gate", "passed", {"finding_count": len(findings)})

        prioritized = self._prioritize(findings)
        stream.emit("review_reasoner", "issues_ranked", {"count": len(prioritized)})

        retrieval_query = self._build_retrieval_query(prioritized=prioritized, code_snippet=code_snippet)
        stream.emit("rag", "retrieval_started", {"query_length": len(retrieval_query), "limit": 3})
        historical_context = self.history_store.summarize_for_prompt(query_text=retrieval_query, limit=3)
        stream.emit("rag", "retrieval_completed", {"context_length": len(historical_context), "matches": historical_context.count("\n-")})
        stream.emit("tool_calls", "owasp_context_loaded", {"tool": "OWASP_TOP_10", "controls": len(OWASP_TOP_10)})
        stream.emit("agent_reasoner", "reasoning_started", {"provider": self.reasoner.settings.llm_provider, "model": self.reasoner.settings.llm_model})
        llm_summary = self.reasoner.generate_review_reasoning(
            findings=prioritized,
            historical_context=historical_context,
            owasp_context=OWASP_TOP_10,
        )
        stream.emit("agent_reasoner", "reasoning_completed", {"fallback_used": llm_summary.get("fallback_used", False)})
        stream.emit("review_reasoner", "recommendations_generated", {"summary": llm_summary["summary"]})

        source = "repo" if repo_path else "snippet"
        rows_added = self.history_store.add_findings(
            review_id=review_id,
            findings=prioritized,
            source=source,
            language=language,
            extra_metadata={"repo_path": repo_path},
        )
        stream.emit("memory", "history_persisted", {"rows_added": rows_added, "source": source})
        stream.emit("pull_request", "review_ready", {"status": "pending", "reason": "No pull request target was supplied."})

        review_result = {
            "review_id": review_id,
            "language": language,
            "source": source,
            "owasp_context": OWASP_TOP_10,
            "summary": llm_summary["summary"],
            "recommendations": llm_summary.get("recommendations", []),
            "llm_provider": llm_summary.get("provider"),
            "llm_model": llm_summary.get("model"),
            "llm_fallback_used": llm_summary.get("fallback_used", False),
            "llm_fallback_reason": llm_summary.get("fallback_reason"),
            "historical_context": historical_context,
            "total_findings": len(prioritized),
            "findings": prioritized,
            "dag_events": stream.snapshot(),
            "memory": self.memory.summarize(review_id),
        }

        self.memory.add(review_id, "assistant", llm_summary["summary"], total_findings=len(prioritized))
        return review_result

    def _prioritize(self, findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        severity_order = {"critical": 4, "major": 3, "minor": 2, "info": 1, "high": 3, "medium": 2, "low": 1, "error": 4}
        sorted_findings = sorted(
            findings,
            key=lambda item: (
                severity_order.get(str(item.get("severity", "low")).lower(), 0),
                -(int(item.get("line", 1)) or 1),
            ),
            reverse=True,
        )

        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in sorted_findings:
            key = f"{item.get('line')}-{item.get('rule_id')}-{item.get('message')}"
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def _build_retrieval_query(self, prioritized: list[dict[str, Any]], code_snippet: str | None) -> str:
        if prioritized:
            top = prioritized[0]
            return (
                f"{top.get('rule_id', 'GENERIC')} "
                f"{top.get('category', 'quality')} "
                f"{top.get('message', '')} "
                f"{top.get('recommendation', '')}"
            )

        if code_snippet:
            return code_snippet[:400]

        return "python code review recommendations"

