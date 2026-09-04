from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx

from backend.app.config import get_settings
from agent.recommendation_history_store import get_recommendation_history_store
from agent.review_tools import scan_python_source


@dataclass(slots=True)
class GitHubPRReviewRequest:
    owner: str
    repo: str
    pull_number: int
    max_findings: int = 30
    dry_run: bool = False
    review_event: str = "COMMENT"
    review_body: str | None = None


class GitHubPRReviewService:
    def __init__(self, timeout_seconds: float = 10.0) -> None:
        self.timeout_seconds = timeout_seconds
        self.history_store = get_recommendation_history_store()
        self.settings = get_settings()

    async def review_pull_request(self, request: GitHubPRReviewRequest) -> dict[str, Any]:
        token = self.settings.github_token
        if not token:
            return self._fallback(
                request,
                reason="Missing GitHub token. Set GITHUB_TOKEN in .env.",
                findings=[],
            )

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "code-assist-pr-reviewer",
        }

        async with httpx.AsyncClient(timeout=self.timeout_seconds, headers=headers) as client:
            pr, pr_error = await self._get_json(
                client,
                f"https://api.github.com/repos/{request.owner}/{request.repo}/pulls/{request.pull_number}",
            )
            if pr_error:
                return self._fallback(request, reason=f"Failed to fetch PR metadata: {pr_error}", findings=[])

            files, files_error = await self._get_json(
                client,
                f"https://api.github.com/repos/{request.owner}/{request.repo}/pulls/{request.pull_number}/files",
            )
            if files_error:
                return self._fallback(request, reason=f"Failed to fetch PR files: {files_error}", findings=[])

            findings = self._scan_changed_python_lines(files)
            findings = findings[: max(1, request.max_findings)]

            history_rows_added = self.history_store.add_findings(
                review_id=f"pr-{request.owner}-{request.repo}-{request.pull_number}",
                findings=findings,
                source="github_pr",
                language="python",
                extra_metadata={
                    "owner": request.owner,
                    "repo": request.repo,
                    "pull_number": request.pull_number,
                },
            )

            comment_body = self._build_comment_body(findings, request.review_body)
            inline_comments = self._build_inline_comments(findings)

            posted = False
            posted_review_id: int | None = None
            comment_error: str | None = None
            if not request.dry_run:
                review_payload: dict[str, Any] = {
                    "event": self._normalize_review_event(request.review_event),
                    "body": comment_body,
                    "comments": inline_comments,
                }
                posted_review, post_error = await self._post_json(
                    client,
                    f"https://api.github.com/repos/{request.owner}/{request.repo}/pulls/{request.pull_number}/reviews",
                    review_payload,
                )
                if post_error:
                    fallback_payload = {
                        "body": comment_body,
                    }
                    _, fallback_post_error = await self._post_json(
                        client,
                        f"https://api.github.com/repos/{request.owner}/{request.repo}/issues/{request.pull_number}/comments",
                        fallback_payload,
                    )
                    if fallback_post_error:
                        comment_error = post_error
                    else:
                        posted = True
                        comment_error = (
                            "Inline PR review failed; posted a regular PR comment instead. "
                            f"Reason: {post_error}"
                        )
                elif isinstance(posted_review, dict):
                    posted_review_id = posted_review.get("id")
                    posted = True
                else:
                    posted = True
            
            event_used = self._normalize_review_event(request.review_event)

        return {
            "status": "ok" if posted or request.dry_run else "partial",
            "mode": "dry_run" if request.dry_run else "live",
            "owner": request.owner,
            "repo": request.repo,
            "pull_number": request.pull_number,
            "pr_title": pr.get("title") if isinstance(pr, dict) else None,
            "total_findings": len(findings),
            "findings": findings,
            "review_event": event_used,
            "inline_comments_count": len(inline_comments),
            "history_rows_added": history_rows_added,
            "review_submitted": posted,
            "review_id": posted_review_id,
            "comment_posted": posted,
            "fallback_used": bool(comment_error),
            "fallback_reason": comment_error,
            "fallback_comment_preview": comment_body if comment_error else None,
        }

    async def _get_json(self, client: httpx.AsyncClient, url: str) -> tuple[Any, str | None]:
        try:
            response = await client.get(url)
            response.raise_for_status()
            return response.json(), None
        except Exception as exc:
            return None, str(exc)

    async def _post_json(self, client: httpx.AsyncClient, url: str, payload: dict[str, Any]) -> tuple[Any, str | None]:
        try:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return response.json(), None
        except Exception as exc:
            return None, str(exc)

    def _normalize_review_event(self, value: str) -> str:
        event = (value or "COMMENT").strip().upper()
        allowed = {"COMMENT", "APPROVE", "REQUEST_CHANGES"}
        return event if event in allowed else "COMMENT"

    def _build_inline_comments(self, findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        comments: list[dict[str, Any]] = []
        for item in findings:
            path = str(item.get("path", "")).strip()
            line = int(item.get("line", 1) or 1)
            severity = str(item.get("severity", "low")).lower()
            severity_label = str(item.get("severity_label", severity.title()))
            blocking = "Yes" if item.get("pr_blocking", False) else "No"
            rule_id = str(item.get("rule_id", "GENERIC"))
            message = str(item.get("message", "Issue detected"))
            recommendation = str(item.get("recommendation", "Review this code block."))
            if not path:
                continue

            body = (
                f"### **[{severity_label}] ({severity.title()})**\n"
                f"{message}\n\n"
                f"**PR Blocking:** {blocking}\n\n"
                f"**Suggested Fix:** {recommendation}"
            )
            comments.append({"path": path, "line": line, "side": "RIGHT", "body": body})
        return comments

    def _scan_changed_python_lines(self, files: Any) -> list[dict[str, Any]]:
        if not isinstance(files, list):
            return []

        findings: list[dict[str, Any]] = []
        for file_item in files:
            if not isinstance(file_item, dict):
                continue
            filename = str(file_item.get("filename", ""))
            if not filename.endswith(".py"):
                continue

            patch = file_item.get("patch")
            if not isinstance(patch, str) or not patch.strip():
                continue

            added_lines = self._extract_added_lines_with_numbers(patch)
            if not added_lines:
                continue

            code_snippet = "\n".join(line for _, line in added_lines)
            snippet_findings = scan_python_source(code_snippet)

            for finding in snippet_findings:
                relative_line = int(finding.get("line", 1))
                if 1 <= relative_line <= len(added_lines):
                    absolute_line = added_lines[relative_line - 1][0]
                else:
                    absolute_line = added_lines[0][0]

                findings.append(
                    {
                        "path": filename,
                        "line": absolute_line,
                        "severity": finding.get("severity", "low"),
                        "severity_label": finding.get("severity_label", ""),
                        "pr_blocking": finding.get("pr_blocking", False),
                        "rule_id": finding.get("rule_id", "GENERIC"),
                        "category": finding.get("category", "quality"),
                        "message": finding.get("message", "Issue detected"),
                        "recommendation": finding.get("recommendation", "Review this code block."),
                        "evidence": finding.get("evidence", ""),
                    }
                )

        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in findings:
            key = f"{item['path']}:{item['line']}:{item['rule_id']}:{item['message']}"
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def _extract_added_lines_with_numbers(self, patch: str) -> list[tuple[int, str]]:
        added: list[tuple[int, str]] = []
        current_new_line = 0

        for raw_line in patch.splitlines():
            if raw_line.startswith("@@"):
                match = re.search(r"\+(\d+)(?:,\d+)?", raw_line)
                if match:
                    current_new_line = int(match.group(1))
                continue

            if raw_line.startswith("+++") or raw_line.startswith("---"):
                continue

            if raw_line.startswith("+"):
                added.append((current_new_line, raw_line[1:]))
                current_new_line += 1
            elif raw_line.startswith("-"):
                continue
            else:
                current_new_line += 1

        return added

    def _build_comment_body(self, findings: list[dict[str, Any]], review_body: str | None = None) -> str:
        if review_body and review_body.strip():
            prefix = review_body.strip()
        else:
            prefix = "## Automated Peer Review"

        if not findings:
            return (
                f"{prefix}\n\n"
                "No deterministic issues were detected in changed Python lines.\n"
                "Review scope: changed `.py` lines from this PR only."
            )

        lines = [
            prefix,
            "",
            "Deterministic scan of changed Python lines found the following:",
            "",
        ]

        for item in findings:
            lines.append(
                f"- `{item['path']}:{item['line']}` **[{item.get('severity_label', item['severity'])}]** "
                f"({item['severity'].title()}) `{item['rule_id']}` - {item['message']} "
                f"(PR Blocking: {'Yes' if item.get('pr_blocking', False) else 'No'})"
            )
            lines.append(f"  - Recommendation: {item['recommendation']}")

        lines.append("")
        lines.append("This review was generated by the code review assistant with graceful fallback enabled.")
        return "\n".join(lines)

    def _fallback(self, request: GitHubPRReviewRequest, reason: str, findings: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "status": "fallback",
            "mode": "live",
            "owner": request.owner,
            "repo": request.repo,
            "pull_number": request.pull_number,
            "total_findings": len(findings),
            "findings": findings,
            "review_event": self._normalize_review_event(request.review_event),
            "inline_comments_count": len(self._build_inline_comments(findings)),
            "history_rows_added": 0,
            "review_submitted": False,
            "review_id": None,
            "comment_posted": False,
            "fallback_used": True,
            "fallback_reason": reason,
            "fallback_comment_preview": self._build_comment_body(findings, request.review_body),
        }
