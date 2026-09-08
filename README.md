# Latency-First FastAPI + Google ADK Starter

This codebase is optimized for low request-path latency:

- Thin FastAPI routes
- Reused async HTTP clients
- One-time ADK runtime initialization
- Local, cheap security checks
- Request timing histogram with p50/p95/p99 measurement
- High-throughput JSON responses with `orjson`

## Structure

- `data/` – runtime data and seed files
- `backend/` – FastAPI service and app lifecycle
- `security/` – auth and lightweight request middleware
- `agent/` – Google ADK runtime and manager

## Run locally

```bash
uv sync
uv run uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

Create `.env` from `.env.example` and set secrets there (`API_KEY`, `GITHUB_TOKEN`, `GEMINI_API_KEY`).

LLM configuration is provider-driven and swappable:

- `LLM_PROVIDER=gemini`
- `LLM_MODEL=gemini-2.5-flash`

Gemini AI Studio is used by default for review reasoning when `GEMINI_API_KEY` is set. If unavailable, deterministic fallback reasoning is used.

## Prompt Injection Guard (Programmatic)

The `/api/v1/agent/invoke` endpoint can enforce a local programmatic prompt injection and jailbreak detector.

Important scope:

- Guard applies to user prompt text only.
- It does not block repository code scanning or code-snippet deterministic analysis.

Environment settings:

- `PROMPT_GUARD_ENABLED=true`
- `PROMPT_GUARD_MIN_MATCH_HITS=1`
- `PROMPT_GUARD_BLOCK_ON_ERROR=false`
- `PROMPT_GUARD_ALLOWLIST=security test prompt,internal red-team simulation`

## Model Armor and agent evaluation

The local Model Armor implementation is deterministic and auditable. It reports whether prompt text is passed or blocked, the matched threat names, and the screening provider:

```bash
curl -X POST http://localhost:8000/api/v1/security/model-armor/check \
  -H "Content-Type: application/json" \
  -d '{"text":"Review this code for security issues.","source":"evaluation"}'
```

Use the scorecard API to test an agent prompt against a code sample. It scores safety, deterministic analysis, OWASP grounding, and response completeness:

```bash
curl -X POST http://localhost:8000/api/v1/agent/evaluate \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Review this code for security issues.","code_snippet":"import subprocess\nsubprocess.run(command, shell=True)","expected_keywords":["injection"]}'
```

Security findings are passed to `OWASPWebsiteTool`, which categorizes them, checks the official OWASP URL, and returns the category, importance, link, and reachability in `owasp_findings`. This is context for the LLM, not a replacement for deterministic checks.

## Health endpoints

- `GET /healthz`
- `GET /readyz`
- `GET /metrics`

## Example call

```bash
curl -H "X-API-Key: change-me" -X POST http://localhost:8000/api/v1/agent/invoke \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Summarize the latest latency improvements."}'
```

# Intelligent Code Review Assistant

This project is designed for application-development teams that need a code review assistant for Python repositories and snippets. The system uses a deterministic-first agentic design, combining static analysis, Ruff linting, OWASP Top 10 security context, an LLM reasoning layer, tool orchestration, in-memory context, and a live DAG event stream.

## Agentic AI design pattern

Use a Supervisor / Planner-Worker architecture:

- Planner: receives the repo or snippet and defines the review workflow.
- Deterministic gate: runs AST validation and Ruff linting before LLM reasoning.
- Security context: injects OWASP Top 10 into the reasoning prompt.
- Worker tools: repo scanner, Python AST inspector, Ruff runner, vulnerability policy lookup, findings classifier.
- Reasoner: uses the LLM to rank, explain, and recommend fixes.
- Memory: keeps in-memory session history and findings for the current review.
- Event stream: emits DAG-like events so the UI can render a live progress graph.

This is the best fit here because code review needs trust, explainability, and latency control. Deterministic tools handle the fast, consistent checks first; the LLM is then used only for reasoning and recommendations, not for all critical validation.

## High-level flow

1. Receive repo or code snippet.
2. Run deterministic checks: Python AST parse + Ruff.
3. Attach OWASP Top 10 threat context.
4. Rank risky findings by severity.
5. Ask the LLM to explain root cause and recommend fix actions.
6. Store review context in in-memory state.
7. Emit DAG events for UI progress streaming.
8. Return findings with line numbers, issue category, severity, and recommendation.

## Core structure

- `agent/` – orchestrator, DAG event stream, memory, review tools
- `backend/` – FastAPI API service and route layer
- `security/` – authentication and lightweight request middleware
- `data/` – output samples and local artifacts

## Example API

```bash
curl -X POST http://localhost:8000/api/v1/review \
  -H "Content-Type: application/json" \
  -d '{
    "code_snippet": "import subprocess\napi_key = \"secret\"\nsubprocess.run(\"ls -l\", shell=True)\nassert True\n",
    "language": "python"
  }'
```

## GitHub PR review API

Review only changed Python lines in a PR and post peer-review comments to that PR:

```bash
curl -X POST http://localhost:8000/api/v1/review/github-pr \
  -H "Content-Type: application/json" \
  -d '{
    "owner": "your-org",
    "repo": "your-repo",
    "pull_number": 42,
    "dry_run": false,
    "review_event": "REQUEST_CHANGES",
    "review_body": "Automated security and quality review"
  }'
```

Notes:

- Uses `GITHUB_TOKEN` from `.env` / environment.
- Scans only changed `.py` lines in the PR patch for peer-review issues.
- Submits a real PR review via GitHub Reviews API with inline line comments when possible.
- `review_event` supports `COMMENT`, `APPROVE`, and `REQUEST_CHANGES`.
- Graceful fallback returns `fallback_reason` and `fallback_comment_preview` if review submission fails.

## Review history API (SQLite + Chroma)

Each review stores recommendation history in SQLite and indexes it in Chroma (when installed) for RAG-style retrieval in future reviews.

Read history:

```bash
curl "http://localhost:8000/api/v1/review/history?limit=50"
```

Search similar historical recommendations:

```bash
curl "http://localhost:8000/api/v1/review/history?query=sql%20injection&n_results=5"
```

## Business document or Jira story

Generate both formats from a review result or selected findings:

```bash
curl -X POST http://localhost:8000/api/v1/review/story \
  -H "Content-Type: application/json" \
  -d '{"title":"Remove unsafe subprocess call","summary":"replace shell execution with a constrained API","findings":[{"rule_id":"SEC001","line":4,"severity":"critical"}]}'
```

## Intermediate developer estimate

For a production-ready version of this work, estimate **3-5 developer days**: 1 day for GitHub API integration tests and pagination/error handling, 1 day for Model Armor/provider validation, 1-2 days for scorecard calibration and OWASP tool tests, and 0.5-1 day for Jira/business-document integration and documentation. The current implementation is a working local baseline; network credentials, CI tests, and product-specific scoring calibration remain required before release.

## Response contract

The response includes:

- `review_id`
- `summary`
- `total_findings`
- `findings[]` with `line`, `severity`, `rule_id`, `message`, `recommendation`
- `owasp_context`
- `dag_events[]`
- `memory`

## Frontend sample output

See `data/sample_review_output.json` for a sample payload the frontend can render.

## Recommended best practices

- Use deterministic analysis first; never let the LLM decide whether syntax is valid.
- Keep the LLM limited to reasoning, root-cause analysis, and prioritization.
- Use severity-based filtering and confidence scoring before surfacing findings.
- Keep memory session-scoped, not global, to limit cross-review leakage.
- Emit DAG events for each stage so the UI can show progress and dependencies.
- Treat OWASP Top 10 as a policy context, not as a replacement for AST and Ruff.
- Keep tool calls explicit and auditable.
- Return evidence, line numbers, and fix recommendations with each finding.

## Live DAG event stream

Example DAG nodes:

- `repo_loader.started`
- `static_analysis.ast_parsed`
- `deterministic_gate.passed`
- `review_reasoner.issues_ranked`
- `review_reasoner.recommendations_generated`

These events can be pushed via WebSockets or Server-Sent Events for live UI progress.

### Start a review

Create the review ID before processing begins. The API returns immediately with HTTP `202`, allowing a client to open the WebSocket before DAG work starts:

```bash
curl -X POST http://localhost:8000/api/v1/review/start \
  -H "Content-Type: application/json" \
  -d '{"code_snippet":"import subprocess\nsubprocess.run(command, shell=True)","language":"python"}'
```

Response:

```json
{"review_id":"review-8e4...","status":"started"}
```

### WebSocket URL and events

```text
ws://localhost:8000/api/v1/ws/reviews/{review_id}
```

Every DAG message uses this shape:

```json
{
  "review_id": "review-8e4...",
  "node": "static_analysis",
  "event": "ast_parsed",
  "timestamp": "2026-09-04T03:15:12.423723+00:00",
  "payload": {"source_length": 64}
}
```

Lifecycle messages are `connected`, `review_started`, `review_completed`, and `review_failed`. The stream replays all events emitted before a late subscriber connects, including the terminal lifecycle event.

### Review status and result

```bash
curl http://localhost:8000/api/v1/review/review-8e4...
```

The response includes `status` (`created`, `started`, `completed`, or `failed`), the completed `result` when available, the failure `error` when applicable, and the replayable `events` list. Unknown review IDs return HTTP `404`; unknown WebSocket IDs receive a `review_failed` message and close cleanly.

The original `POST /api/v1/review` remains available and returns the completed result synchronously for backward compatibility. The new start endpoint is recommended for live streaming clients.
