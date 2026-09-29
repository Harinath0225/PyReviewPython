from __future__ import annotations

import ast
import base64
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.app.config import get_settings

try:
    from google import genai
    from google.genai import types
except Exception:
    genai = None
    types = None


@dataclass
class RequirementItem:
    id: str
    title: str
    description: str
    req_type: str = "functional_requirement"  # user_story, acceptance_criteria, business_rule, functional_requirement, constraint
    critical_terms: list[str] = field(default_factory=list)
    raw_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "type": self.req_type,
            "critical_terms": self.critical_terms,
            "raw_text": self.raw_text,
        }


@dataclass
class RequirementMapping:
    requirement_id: str
    title: str
    requirement_text: str
    status: str  # COVERED, PARTIALLY_COVERED, MISSING, MISALIGNED, VULNERABLE
    coverage_score: float  # 0.0 - 100.0
    mapped_symbols: list[dict[str, Any]] = field(default_factory=list)
    evidence: str = ""
    gap_or_risk: str | None = None
    remediation: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "title": self.title,
            "requirement_text": self.requirement_text,
            "status": self.status,
            "coverage_score": self.coverage_score,
            "mapped_symbols": self.mapped_symbols,
            "evidence": self.evidence,
            "gap_or_risk": self.gap_or_risk,
            "remediation": self.remediation,
        }


class BusinessRequirementSubagent:
    """Specialized Subagent to parse BRDs, Jira tickets, and Jira/BRD screenshots,

    create a structured business requirement summary, and map requirements
    directly to the codebase AST with a traceability matrix and gap analysis.
    """

    def __init__(self, model_name: str | None = None, vision_model: str | None = None) -> None:
        self.settings = get_settings()
        self.model_name = (
            model_name
            or os.getenv("LLM_MODEL")
            or os.getenv("GEMMA_MODEL")
            or self.settings.llm_model
            or "gemma-4-26b-a4b-it"
        )
        self.vision_model = (
            vision_model
            or getattr(self.settings, "vision_llm_model", None)
            or getattr(self.settings, "diagram_llm_model", None)
            or "gemini-3.1-flash-lite"
        )

    def analyze_and_map(
        self,
        business_input: Any,
        code_snippet: str | None = None,
        repo_path: str | None = None,
        doc_type: str = "auto",
    ) -> dict[str, Any]:
        """End-to-end pipeline:

        1. Process input (text, BRD, Jira story, or screenshot/image)
        2. Create structured business summary and requirements list
        3. Map requirements to codebase AST symbols (traceability matrix)
        4. Detect business logic flaws (e.g., sticker price refund, threshold abuse, discount stacking)
        5. Return comprehensive result with coverage metrics and review findings.
        """
        extracted_data = self.process_business_input(business_input, doc_type=doc_type)
        summary = self.create_summary(extracted_data)
        requirements = extracted_data.get("requirements", [])

        # If no requirements were extracted, generate baseline requirements from summary
        if not requirements:
            requirements = self._derive_fallback_requirements(summary)

        # Map requirements to code
        code_text = code_snippet or ""
        if not code_text and repo_path and Path(repo_path).exists():
            code_text = self._load_repo_code_sample(repo_path)

        traceability_matrix, coverage_score, findings = self.map_requirements_to_code(
            requirements=requirements,
            code=code_text,
            repo_path=repo_path,
        )

        # Check for flawed requirement patterns in the raw business document text
        raw_doc_text = extracted_data.get("raw_text", "")
        if raw_doc_text:
            flaws = self._detect_flawed_requirement_patterns(raw_doc_text)
            for flaw in flaws:
                if not any(f.get("rule_id") == flaw.get("rule_id") for f in findings):
                    findings.append(flaw)

        return {
            "summary": summary,
            "requirements": [r.to_dict() if isinstance(r, RequirementItem) else r for r in requirements],
            "traceability_matrix": [m.to_dict() if isinstance(m, RequirementMapping) else m for m in traceability_matrix],
            "coverage_score": coverage_score,
            "findings": findings,
            "is_screenshot": extracted_data.get("is_screenshot", False),
            "source_type": extracted_data.get("doc_type", doc_type),
        }

    def process_business_input(self, business_input: Any, doc_type: str = "auto") -> dict[str, Any]:
        """Normalize and parse business input from text, dictionary, or screenshot image."""
        if not business_input:
            return {
                "title": "Unspecified Business Requirement",
                "summary": "No business requirement document or screenshot provided.",
                "requirements": [],
                "raw_text": "",
                "is_screenshot": False,
                "doc_type": "none",
            }

        # Check if list of documents
        if isinstance(business_input, list):
            merged_text = []
            combined_reqs = []
            is_screenshot = False
            for item in business_input:
                sub_res = self.process_business_input(item)
                if sub_res.get("raw_text"):
                    merged_text.append(sub_res["raw_text"])
                if sub_res.get("requirements"):
                    combined_reqs.extend(sub_res["requirements"])
                if sub_res.get("is_screenshot"):
                    is_screenshot = True
            
            full_text = "\n\n".join(merged_text)
            summary = self.extract_from_text(full_text, doc_type="merged")
            if combined_reqs:
                summary["requirements"] = combined_reqs
            summary["is_screenshot"] = is_screenshot
            return summary

        # Check if dictionary input
        if isinstance(business_input, dict):
            # Check for image data or screenshot type
            dtype = str(business_input.get("type", "")).lower()
            image_data = business_input.get("image_data") or business_input.get("screenshot") or business_input.get("image")
            content = business_input.get("content") or business_input.get("text") or ""
            
            if dtype in {"screenshot", "image", "jira_screenshot", "brd_screenshot"} or image_data:
                img_payload = image_data or content
                mime_type = business_input.get("mime_type", "image/png")
                return self.extract_from_screenshot(img_payload, mime_type=mime_type, context_text=content)
            
            # Content is text
            return self.extract_from_text(str(content), doc_type=dtype or doc_type)

        # Check if string input
        if isinstance(business_input, str):
            clean_str = business_input.strip()
            # Detect data URL (e.g. data:image/png;base64,...)
            if clean_str.startswith("data:image/") and ";base64," in clean_str:
                return self.extract_from_screenshot(clean_str)

            # Detect existing image file path
            if (clean_str.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp")) or "\x00" not in clean_str) and len(clean_str) < 500:
                p = Path(clean_str)
                if p.exists() and p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                    return self.extract_from_screenshot(clean_str)

            # Plain text input
            return self.extract_from_text(clean_str, doc_type=doc_type)

        return self.extract_from_text(str(business_input), doc_type=doc_type)

    def extract_from_screenshot(
        self,
        image_input: str | bytes,
        mime_type: str = "image/png",
        context_text: str = "",
    ) -> dict[str, Any]:
        """Extract business requirements from Jira ticket or BRD screenshot using multimodal Gemini

        with deterministic fallback.
        """
        image_bytes: bytes | None = None

        if isinstance(image_input, bytes):
            image_bytes = image_input
        elif isinstance(image_input, str):
            clean = image_input.strip()
            if clean.startswith("data:image/") and ";base64," in clean:
                header, b64_data = clean.split(";base64,", 1)
                mime_type = header.replace("data:", "")
                try:
                    image_bytes = base64.b64decode(b64_data)
                except Exception:
                    image_bytes = None
            elif Path(clean).exists() and Path(clean).is_file():
                try:
                    p = Path(clean)
                    suffix = p.suffix.lower()
                    if suffix in {".jpg", ".jpeg"}:
                        mime_type = "image/jpeg"
                    elif suffix == ".webp":
                        mime_type = "image/webp"
                    else:
                        mime_type = "image/png"
                    image_bytes = p.read_bytes()
                except Exception:
                    image_bytes = None
            else:
                # Try raw base64 decode if it looks like base64
                if len(clean) > 50 and re.match(r"^[A-Za-z0-9+/=\r\n]+$", clean):
                    try:
                        image_bytes = base64.b64decode(clean)
                    except Exception:
                        image_bytes = None

        # 1. Try Gemini Vision multimodal extraction if API key is present
        api_key = self.settings.gemini_api_key or os.getenv("GOOGLE_API_KEY")
        if image_bytes and api_key and genai is not None and types is not None:
            try:
                client = genai.Client(api_key=api_key)
                part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
                prompt = (
                    "You are an expert business systems analyst. Inspect this screenshot of a Jira ticket, "
                    "BRD, user story, or business requirements document. "
                    "Extract all business requirements, user stories, acceptance criteria, formulas, and business rules. "
                    "Return strictly valid JSON with this schema: "
                    "{\n"
                    '  "ticket_key": "string or null (e.g. PAY-101)",\n'
                    '  "title": "string (feature/ticket title)",\n'
                    '  "summary": "string (executive summary of requirement)",\n'
                    '  "business_goals": ["string"],\n'
                    '  "user_stories": [{"role": "string", "want": "string", "so_that": "string"}],\n'
                    '  "acceptance_criteria": ["string (e.g. AC-1: Given/When/Then or requirement statement)"],\n'
                    '  "business_rules": ["string (pricing rules, validation, formulas, edge cases)"],\n'
                    '  "constraints": ["string"]\n'
                    "}\n"
                    "Do not include markdown fences. Output strictly raw JSON."
                )
                v_model = self.vision_model if ("gemma" in self.model_name.lower()) else self.model_name
                response = client.models.generate_content(
                    model=v_model,
                    contents=[part, prompt],
                )
                resp_text = getattr(response, "text", "") or ""
                parsed = self._parse_json(resp_text)
                if parsed and isinstance(parsed, dict) and parsed.get("title"):
                    parsed_reqs = self._convert_dict_to_requirements(parsed)
                    parsed["requirements"] = parsed_reqs
                    parsed["is_screenshot"] = True
                    parsed["raw_text"] = resp_text or f"Screenshot: {parsed.get('title')}"
                    parsed["doc_type"] = "jira_screenshot" if parsed.get("ticket_key") else "brd_screenshot"
                    return parsed
            except Exception:
                pass  # Fall back to deterministic processing

        # 2. Deterministic / OCR fallback
        fallback_title = "Visual Business Requirement"
        ticket_key = None
        if context_text:
            text_result = self.extract_from_text(context_text, doc_type="screenshot_context")
            text_result["is_screenshot"] = True
            text_result["image_size_bytes"] = len(image_bytes) if image_bytes else 0
            return text_result

        # Synthetic requirement extraction for screenshot
        requirements = [
            RequirementItem(
                id="AC-01",
                title="Visual Ticket Requirement Implementation",
                description="Core functional workflow extracted from Jira ticket screenshot must be implemented.",
                req_type="acceptance_criteria",
                critical_terms=["order", "refund", "price", "discount", "item", "user", "status"],
                raw_text="Visual ticket requirement",
            ),
            RequirementItem(
                id="BR-01",
                title="Business Rule & Formula Compliance",
                description="Business calculation logic (discounts, refunds, thresholds) must follow strict business rules without exploits.",
                req_type="business_rule",
                critical_terms=["refund", "discount", "effective_paid_price", "threshold", "total"],
                raw_text="Business calculation rule",
            ),
            RequirementItem(
                id="BR-02",
                title="Validation and Boundary Edge Cases",
                description="All input values, boundary thresholds, and unauthorized actions must be validated.",
                req_type="business_rule",
                critical_terms=["validate", "check", "error", "raise", "exception"],
                raw_text="Validation requirement",
            ),
        ]

        return {
            "ticket_key": ticket_key,
            "title": fallback_title,
            "summary": "Visual business specification extracted from screenshot. Requires corresponding code implementation and validation.",
            "business_goals": [
                "Implement feature logic shown in visual specification",
                "Ensure business rules and formulas match business expectations",
            ],
            "user_stories": [
                {
                    "role": "User",
                    "want": "execute the business process specified in the visual document",
                    "so_that": "business operations proceed without logic flaws",
                }
            ],
            "acceptance_criteria": [r.description for r in requirements if r.req_type == "acceptance_criteria"],
            "business_rules": [r.description for r in requirements if r.req_type == "business_rule"],
            "requirements": requirements,
            "is_screenshot": True,
            "image_size_bytes": len(image_bytes) if image_bytes else 0,
            "raw_text": f"Screenshot: {fallback_title}",
            "doc_type": "screenshot",
        }

    def extract_from_text(self, text: str, doc_type: str = "auto") -> dict[str, Any]:
        """Parse structured requirements from BRD, Jira markdown, or specifications."""
        cleaned = text.strip()
        if not cleaned:
            return {
                "title": "Empty Document",
                "summary": "No content provided in business document.",
                "requirements": [],
                "raw_text": "",
                "is_screenshot": False,
                "doc_type": doc_type,
            }

        # 1. Detect Jira Ticket Pattern
        ticket_match = re.search(r"\b([A-Z]{2,10}-\d+)\b", cleaned)
        ticket_key = ticket_match.group(1) if ticket_match else None

        # 2. Extract Title
        title = self._extract_title(cleaned, ticket_key)

        # 3. Extract User Stories
        user_stories = self._extract_user_stories(cleaned)

        # 4. Extract Acceptance Criteria
        acceptance_criteria = self._extract_acceptance_criteria(cleaned)

        # 5. Extract Business Rules & Policies
        business_rules = self._extract_business_rules(cleaned)

        # 6. Build RequirementItem list
        requirements: list[RequirementItem] = []
        counter = 1

        for story in user_stories:
            role = story.get("role", "User")
            want = story.get("want", "")
            so_that = story.get("so_that", "")
            desc = f"As a {role}, I want to {want}" + (f", so that {so_that}" if so_that else "")
            req_id = f"US-{counter:02d}"
            counter += 1
            requirements.append(
                RequirementItem(
                    id=req_id,
                    title=f"User Story: {want[:40]}...",
                    description=desc,
                    req_type="user_story",
                    critical_terms=self._extract_key_terms(desc),
                    raw_text=desc,
                )
            )

        ac_counter = 1
        for ac in acceptance_criteria:
            req_id = f"AC-{ac_counter:02d}"
            ac_counter += 1
            requirements.append(
                RequirementItem(
                    id=req_id,
                    title=f"Acceptance Criteria {ac_counter-1}",
                    description=ac,
                    req_type="acceptance_criteria",
                    critical_terms=self._extract_key_terms(ac),
                    raw_text=ac,
                )
            )

        br_counter = 1
        for br in business_rules:
            req_id = f"BR-{br_counter:02d}"
            br_counter += 1
            requirements.append(
                RequirementItem(
                    id=req_id,
                    title=f"Business Rule {br_counter-1}",
                    description=br,
                    req_type="business_rule",
                    critical_terms=self._extract_key_terms(br),
                    raw_text=br,
                )
            )

        # If none of the specific formats matched, parse generic requirements
        if not requirements:
            generic_items = self._extract_generic_requirements(cleaned)
            for idx, item_text in enumerate(generic_items, 1):
                requirements.append(
                    RequirementItem(
                        id=f"REQ-{idx:02d}",
                        title=f"Requirement {idx}",
                        description=item_text,
                        req_type="functional_requirement",
                        critical_terms=self._extract_key_terms(item_text),
                        raw_text=item_text,
                    )
                )

        summary_text = (
            f"Business requirement for {title}. "
            f"Defines {len(requirements)} requirements across "
            f"{len(user_stories)} user stories, {len(acceptance_criteria)} acceptance criteria, "
            f"and {len(business_rules)} business rules."
        )

        return {
            "ticket_key": ticket_key,
            "title": title,
            "summary": summary_text,
            "business_goals": [f"Deliver {title} according to specifications"],
            "user_stories": user_stories,
            "acceptance_criteria": acceptance_criteria,
            "business_rules": business_rules,
            "requirements": requirements,
            "is_screenshot": False,
            "raw_text": cleaned,
            "doc_type": "jira" if ticket_key else ("brd" if "brd" in doc_type.lower() or "requirement" in cleaned.lower() else doc_type),
        }

    def create_summary(self, extracted_data: dict[str, Any]) -> dict[str, Any]:
        """Generate structured business summary suitable for engineering and product alignment."""
        title = extracted_data.get("title", "Business Requirement")
        summary_text = extracted_data.get("summary", "")
        goals = extracted_data.get("business_goals", [])
        stories = extracted_data.get("user_stories", [])
        ac_list = extracted_data.get("acceptance_criteria", [])
        rules = extracted_data.get("business_rules", [])

        # Check for flawed requirement patterns
        raw_text = extracted_data.get("raw_text", "")
        flaws = self._detect_flawed_requirement_patterns(raw_text)

        return {
            "title": title,
            "ticket_key": extracted_data.get("ticket_key"),
            "executive_summary": summary_text,
            "business_goals": goals or [f"Implement business logic for {title}"],
            "user_stories_count": len(stories),
            "acceptance_criteria_count": len(ac_list),
            "business_rules_count": len(rules),
            "identified_flaws_count": len(flaws),
            "identified_flaws": flaws,
        }

    def map_requirements_to_code(
        self,
        requirements: list[RequirementItem | dict[str, Any]],
        code: str,
        repo_path: str | None = None,
    ) -> tuple[list[RequirementMapping], float, list[dict[str, Any]]]:
        """Perform semantic and AST-based traceability mapping of each requirement to code elements."""
        normalized_reqs: list[RequirementItem] = []
        for r in requirements:
            if isinstance(r, RequirementItem):
                normalized_reqs.append(r)
            elif isinstance(r, dict):
                normalized_reqs.append(
                    RequirementItem(
                        id=str(r.get("id") or f"REQ-{len(normalized_reqs)+1:02d}"),
                        title=str(r.get("title") or "Requirement"),
                        description=str(r.get("description") or r.get("raw_text") or ""),
                        req_type=str(r.get("type", "functional_requirement")),
                        critical_terms=r.get("critical_terms") or self._extract_key_terms(str(r.get("description", ""))),
                        raw_text=str(r.get("raw_text", "")),
                    )
                )

        if not normalized_reqs:
            return [], 100.0, []

        # Extract symbols from code
        code_symbols = self._extract_code_symbols(code)
        mappings: list[RequirementMapping] = []
        findings: list[dict[str, Any]] = []

        for req in normalized_reqs:
            mapping, finding = self._map_single_requirement(req, code, code_symbols)
            mappings.append(mapping)
            if finding:
                findings.append(finding)

        # Calculate overall coverage score
        total_score = sum(m.coverage_score for m in mappings)
        overall_coverage = round(total_score / max(len(mappings), 1), 1)

        return mappings, overall_coverage, findings

    def _map_single_requirement(
        self,
        req: RequirementItem,
        code: str,
        symbols: list[dict[str, Any]],
    ) -> tuple[RequirementMapping, dict[str, Any] | None]:
        req_text_lower = (req.title + " " + req.description).lower()
        terms = req.critical_terms or self._extract_key_terms(req_text_lower)

        # Find matching code symbols
        matched_symbols: list[dict[str, Any]] = []
        for sym in symbols:
            sym_name = sym["name"].lower()
            sym_body = sym.get("snippet", "").lower()
            score = 0
            for term in terms:
                if term in sym_name:
                    score += 3
                elif term in sym_body:
                    score += 1
            if score >= 2 or (len(terms) <= 2 and score >= 1):
                matched_symbols.append({
                    "symbol": sym["name"],
                    "kind": sym["kind"],
                    "start_line": sym["start_line"],
                    "end_line": sym["end_line"],
                    "match_score": score,
                })

        # Sort matched symbols by score
        matched_symbols.sort(key=lambda s: s["match_score"], reverse=True)

        # Check for specific business logic flaws
        # 1. Sticker price refund exploit (BIZ001)
        if any(kw in req_text_lower for kw in ["refund", "purchase price", "sticker price", "return item"]):
            refund_sym = next((s for s in symbols if "refund" in s["name"].lower()), None)
            if refund_sym:
                sym_body = refund_sym.get("snippet", "")
                # If code returns item.price directly rather than effective_paid_price
                if "return item.price" in sym_body or "return self.price" in sym_body or "item.price" in sym_body and "effective_paid_price" not in sym_body:
                    mapping = RequirementMapping(
                        requirement_id=req.id,
                        title=req.title,
                        requirement_text=req.description,
                        status="VULNERABLE",
                        coverage_score=35.0,
                        mapped_symbols=matched_symbols or [{"symbol": refund_sym["name"], "start_line": refund_sym["start_line"], "end_line": refund_sym["end_line"]}],
                        evidence=f"Method `{refund_sym['name']}` returns sticker price without factoring in discounts.",
                        gap_or_risk="Exploit 'Buy to Discount, Return to Profit': Customers pocket discounts by returning high-ticket items at sticker price.",
                        remediation="Calculate and return proportional line-item net realized price (effective_paid_price).",
                    )
                    finding = {
                        "rule_id": "BIZ001",
                        "severity": "critical",
                        "pr_blocking": True,
                        "line": refund_sym["start_line"],
                        "category": "business_logic",
                        "message": "Business Requirement Misalignment: Sticker Price Refund Exploit (BIZ001)",
                        "recommendation": "Require proportional discount attribution at transaction time (effective_paid_price = price - item_discount).",
                    }
                    return mapping, finding
                elif "effective_paid_price" in sym_body:
                    mapping = RequirementMapping(
                        requirement_id=req.id,
                        title=req.title,
                        requirement_text=req.description,
                        status="COVERED",
                        coverage_score=100.0,
                        mapped_symbols=matched_symbols or [{"symbol": refund_sym["name"], "start_line": refund_sym["start_line"], "end_line": refund_sym["end_line"]}],
                        evidence=f"Securely implemented in `{refund_sym['name']}` using proportional `effective_paid_price`.",
                    )
                    return mapping, None

        # 2. Threshold abuse / Missing promotion clawback (BIZ002)
        if any(kw in req_text_lower for kw in ["threshold", "cart total", "minimum basket", "qualifying subtotal"]):
            threshold_sym = next((s for s in symbols if "subtotal" in s.get("snippet", "").lower() and "discount" in s.get("snippet", "").lower()), None)
            if threshold_sym:
                sym_body = threshold_sym.get("snippet", "")
                code_lower = code.lower()
                if "clawback" not in code_lower and "recalculate" not in code_lower and "_apply_discounts" not in sym_body:
                    mapping = RequirementMapping(
                        requirement_id=req.id,
                        title=req.title,
                        requirement_text=req.description,
                        status="VULNERABLE",
                        coverage_score=40.0,
                        mapped_symbols=matched_symbols or [{"symbol": threshold_sym["name"], "start_line": threshold_sym["start_line"], "end_line": threshold_sym["end_line"]}],
                        evidence=f"Threshold discount logic found in `{threshold_sym['name']}`, but return recalculation or clawback is absent.",
                        gap_or_risk="Threshold Padding Exploit: Customer adds filler items to unlock tier discount, then cancels or refunds filler items.",
                        remediation="Add clawback and promotion recalculation when returns drop subtotal below threshold.",
                    )
                    finding = {
                        "rule_id": "BIZ002",
                        "severity": "major",
                        "pr_blocking": True,
                        "line": threshold_sym["start_line"],
                        "category": "business_logic",
                        "message": "Business Requirement Misalignment: Missing Promotion Clawback on Returns (BIZ002)",
                        "recommendation": "Recalculate promotion eligibility and clawback tier discounts upon partial refund or cancellation.",
                    }
                    return mapping, finding

        # 3. Unconstrained coupon stacking (BIZ003)
        if any(kw in req_text_lower for kw in ["stack", "additive", "coupon", "promo"]):
            promo_sym = next((s for s in symbols if "promo" in s.get("snippet", "").lower() or "discount" in s.get("snippet", "").lower()), None)
            if promo_sym:
                sym_body = promo_sym.get("snippet", "")
                if ("+=" in sym_body and "subtotal" in sym_body) and ("floor" not in sym_body and "min(" not in sym_body and "margin" not in sym_body):
                    mapping = RequirementMapping(
                        requirement_id=req.id,
                        title=req.title,
                        requirement_text=req.description,
                        status="VULNERABLE",
                        coverage_score=45.0,
                        mapped_symbols=matched_symbols or [{"symbol": promo_sym["name"], "start_line": promo_sym["start_line"], "end_line": promo_sym["end_line"]}],
                        evidence=f"Additive promo discounts stacked without floor check in `{promo_sym['name']}`.",
                        gap_or_risk="Negative Margin Risk: Multiple discounts stack to exceed total order value or violate profit floor.",
                        remediation="Enforce margin floor limit (e.g. min(subtotal, discount)) and explicit stacking sequence.",
                    )
                    finding = {
                        "rule_id": "BIZ003",
                        "severity": "major",
                        "pr_blocking": False,
                        "line": promo_sym["start_line"],
                        "category": "business_logic",
                        "message": "Business Requirement Misalignment: Unconstrained Discount Stacking (BIZ003)",
                        "recommendation": "Define strict discount evaluation ordering and post-discount floor limits.",
                    }
                    return mapping, finding

        # Standard Coverage Evaluation
        if not matched_symbols:
            mapping = RequirementMapping(
                requirement_id=req.id,
                title=req.title,
                requirement_text=req.description,
                status="MISSING",
                coverage_score=0.0,
                mapped_symbols=[],
                evidence="No class, function, or statement matching requirement keywords was detected in the code.",
                gap_or_risk=f"Requirement '{req.title}' is not implemented in codebase.",
                remediation=f"Implement business logic for: {req.description[:100]}...",
            )
            finding = {
                "rule_id": f"BIZ_MISSING_{req.id.replace('-', '_')}",
                "severity": "high" if req.req_type in ["acceptance_criteria", "business_rule"] else "medium",
                "pr_blocking": False,
                "line": 1,
                "category": "business_logic",
                "message": f"Unimplemented Business Requirement: {req.title}",
                "recommendation": f"Add code implementation satisfying requirement {req.id}: {req.description[:120]}.",
            }
            return mapping, finding

        # Partially covered or covered
        top_sym = matched_symbols[0]
        # Check if error handling / validation exists
        has_checks = any(
            pat in code.lower()
            for pat in ["raise valueerror", "raise", "if not", "assert", "try:", "except"]
        )
        if has_checks:
            mapping = RequirementMapping(
                requirement_id=req.id,
                title=req.title,
                requirement_text=req.description,
                status="COVERED",
                coverage_score=100.0,
                mapped_symbols=matched_symbols,
                evidence=f"Implemented in symbol `{top_sym['symbol']}` (lines {top_sym['start_line']}-{top_sym['end_line']}).",
            )
            return mapping, None
        else:
            mapping = RequirementMapping(
                requirement_id=req.id,
                title=req.title,
                requirement_text=req.description,
                status="PARTIALLY_COVERED",
                coverage_score=70.0,
                mapped_symbols=matched_symbols,
                evidence=f"Partially implemented in `{top_sym['symbol']}` (lines {top_sym['start_line']}-{top_sym['end_line']}), but lacks boundary validation or error checks.",
                gap_or_risk="Missing edge case handling or input validation.",
                remediation="Add boundary checks and exception handling for this requirement.",
            )
            return mapping, None

    def _extract_code_symbols(self, code: str) -> list[dict[str, Any]]:
        """Extract classes, functions, and key methods from Python source using AST."""
        symbols: list[dict[str, Any]] = []
        if not code or not code.strip():
            return symbols

        lines = code.splitlines()
        try:
            tree = ast.parse(code)
        except Exception:
            # Fallback regex extraction if AST parse fails
            for idx, line in enumerate(lines, 1):
                class_m = re.match(r"^\s*class\s+([A-Za-z0-9_]+)", line)
                if class_m:
                    symbols.append({
                        "name": class_m.group(1),
                        "kind": "class",
                        "start_line": idx,
                        "end_line": idx,
                        "snippet": line,
                    })
                func_m = re.match(r"^\s*def\s+([A-Za-z0-9_]+)", line)
                if func_m:
                    symbols.append({
                        "name": func_m.group(1),
                        "kind": "function",
                        "start_line": idx,
                        "end_line": idx,
                        "snippet": line,
                    })
            return symbols

        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                start = getattr(node, "lineno", 1)
                end = getattr(node, "end_lineno", start)
                snippet = "\n".join(lines[start - 1 : end]) if lines else ""
                symbols.append({
                    "name": node.name,
                    "kind": "class",
                    "start_line": start,
                    "end_line": end,
                    "snippet": snippet,
                })
                # Methods
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        sub_start = getattr(sub, "lineno", start)
                        sub_end = getattr(sub, "end_lineno", sub_start)
                        sub_snippet = "\n".join(lines[sub_start - 1 : sub_end]) if lines else ""
                        symbols.append({
                            "name": f"{node.name}.{sub.name}",
                            "kind": "method",
                            "start_line": sub_start,
                            "end_line": sub_end,
                            "snippet": sub_snippet,
                        })
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                start = getattr(node, "lineno", 1)
                end = getattr(node, "end_lineno", start)
                snippet = "\n".join(lines[start - 1 : end]) if lines else ""
                symbols.append({
                    "name": node.name,
                    "kind": "function",
                    "start_line": start,
                    "end_line": end,
                    "snippet": snippet,
                })

        return symbols

    def _detect_flawed_requirement_patterns(self, document: str) -> list[dict[str, Any]]:
        """Detect known flawed requirement patterns that lead to severe exploits."""
        from agent.business_logic_analyzer import BusinessLogicAnalyzer

        analyzer = BusinessLogicAnalyzer()
        return analyzer.analyze_flawed_requirements(document)

    def _extract_title(self, text: str, ticket_key: str | None) -> str:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        # First priority: check for explicit summary/title/feature/epic/story label
        for line in lines[:8]:
            clean_line = re.sub(r"^[#\*\-\s]+", "", line)
            if re.match(r"^(?:summary|title|feature|epic|story)\s*:\s*", clean_line, re.IGNORECASE):
                return re.sub(r"^(?:summary|title|feature|epic|story)\s*:\s*", "", clean_line, flags=re.IGNORECASE).strip()
        # Second priority: check markdown headings or descriptive first line (skipping ticket metadata labels)
        for line in lines[:8]:
            clean_line = re.sub(r"^[#\*\-\s]+", "", line)
            if re.match(r"^(?:key|issue\s+type|priority|reporter|assignee|status)\s*:\s*", clean_line, re.IGNORECASE):
                continue
            if len(clean_line) > 5 and len(clean_line) < 80 and not clean_line.lower().startswith("as a"):
                return clean_line
        if ticket_key:
            return f"Feature Ticket {ticket_key}"
        return "Business Requirement Specification"

    def _extract_user_stories(self, text: str) -> list[dict[str, str]]:
        stories: list[dict[str, str]] = []
        # Pattern: As a <role>, I want <want> so that <so_that>
        pattern = re.compile(
            r"as an?\s+([^,\n]+?),?\s*(?:i want to|i want|we want to|we want)\s+([^,\.\n]+?)(?:,?\s*(?:so that|in order to)\s+([^\.\n]+))?",
            re.IGNORECASE,
        )
        for match in pattern.finditer(text):
            role = match.group(1).strip()
            want = match.group(2).strip()
            so_that = match.group(3).strip() if match.group(3) else ""
            stories.append({"role": role, "want": want, "so_that": so_that})
        return stories

    def _extract_acceptance_criteria(self, text: str) -> list[str]:
        ac_list: list[str] = []
        # Check for Given/When/Then blocks
        gwt_pattern = re.compile(r"(given\s+.+?when\s+.+?then\s+[^\.\n]+)", re.IGNORECASE | re.DOTALL)
        for match in gwt_pattern.finditer(text):
            ac_list.append(match.group(1).strip().replace("\n", " "))

        # Check for explicit AC blocks: Acceptance Criteria:\n - ...
        ac_section = re.search(r"(?:acceptance criteria|criteria for acceptance)[\s:]*\n([\s\S]*?)(?:\n\n[A-Z]|\Z)", text, re.IGNORECASE)
        if ac_section:
            section_text = ac_section.group(1)
            for line in section_text.splitlines():
                clean = re.sub(r"^\s*[-*•\d\.]+\s*", "", line).strip()
                if len(clean) > 8 and clean not in ac_list:
                    ac_list.append(clean)

        return ac_list

    def _extract_business_rules(self, text: str) -> list[str]:
        rules: list[str] = []
        # Patterns for business rules: Rule 1: ..., Requirement 1: ..., BR1: ..., Refund ...
        rule_pattern = re.compile(r"(?:rule|requirement|req|br)\s*#?\d*[\s:]+([^\n]+)", re.IGNORECASE)
        for match in rule_pattern.finditer(text):
            rule_text = match.group(1).strip()
            if len(rule_text) > 8 and rule_text not in rules:
                rules.append(rule_text)

        # Look for explicit domain keywords (refund, discount, coupon, threshold, margin, tax)
        for line in text.splitlines():
            line_clean = line.strip()
            if any(kw in line_clean.lower() for kw in ["refund", "threshold discount", "coupon stack", "purchase price"]):
                cleaned_line = re.sub(r"^\s*[-*•\d\.]+\s*", "", line_clean)
                if len(cleaned_line) > 12 and cleaned_line not in rules:
                    rules.append(cleaned_line)

        return rules

    def _extract_generic_requirements(self, text: str) -> list[str]:
        items: list[str] = []
        for line in text.splitlines():
            line_str = line.strip()
            if line_str.startswith(("-", "*", "•")) or re.match(r"^\d+[\.\)]", line_str):
                clean = re.sub(r"^[-*•\d\.\)]+\s*", "", line_str).strip()
                if len(clean) > 10:
                    items.append(clean)
            elif any(kw in line_str.lower() for kw in ["must", "shall", "should", "will", "required to"]):
                if len(line_str) > 15:
                    items.append(line_str)
        return items[:10]

    def _extract_key_terms(self, text: str) -> list[str]:
        stop_words = {
            "the", "a", "an", "and", "or", "is", "are", "was", "were", "be", "by",
            "to", "in", "of", "on", "at", "for", "with", "that", "this", "from",
            "user", "system", "want", "so", "that", "can", "able", "as", "it",
        }
        words = re.findall(r"[A-Za-z_]{3,}", text.lower())
        return list(dict.fromkeys([w for w in words if w not in stop_words]))[:8]

    def _derive_fallback_requirements(self, summary: dict[str, Any]) -> list[RequirementItem]:
        title = summary.get("title", "Feature Requirement")
        return [
            RequirementItem(
                id="REQ-01",
                title=f"{title} Implementation",
                description=f"Implement all functionality specified in {title}.",
                req_type="functional_requirement",
                critical_terms=self._extract_key_terms(title),
                raw_text=title,
            )
        ]

    def _load_repo_code_sample(self, repo_path: str) -> str:
        snippets = []
        try:
            for p in Path(repo_path).rglob("*.py"):
                if "test" not in p.name.lower() and not p.name.startswith("."):
                    snippets.append(p.read_text(encoding="utf-8", errors="ignore"))
                    if len(snippets) >= 5:
                        break
        except Exception:
            pass
        return "\n\n".join(snippets)

    def _parse_json(self, text: str) -> dict[str, Any] | None:
        cleaned = text.strip()
        if not cleaned:
            return None
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(cleaned[start : end + 1])
                except json.JSONDecodeError:
                    return None
        return None

    def _convert_dict_to_requirements(self, data: dict[str, Any]) -> list[RequirementItem]:
        reqs: list[RequirementItem] = []
        idx = 1
        for story in data.get("user_stories", []):
            if isinstance(story, dict):
                desc = f"As a {story.get('role', 'User')}, I want to {story.get('want', '')}, so that {story.get('so_that', '')}"
                reqs.append(
                    RequirementItem(
                        id=f"US-{idx:02d}",
                        title=f"User Story {idx}",
                        description=desc,
                        req_type="user_story",
                        critical_terms=self._extract_key_terms(desc),
                    )
                )
                idx += 1

        ac_idx = 1
        for ac in data.get("acceptance_criteria", []):
            reqs.append(
                RequirementItem(
                    id=f"AC-{ac_idx:02d}",
                    title=f"Acceptance Criteria {ac_idx}",
                    description=str(ac),
                    req_type="acceptance_criteria",
                    critical_terms=self._extract_key_terms(str(ac)),
                )
            )
            ac_idx += 1

        br_idx = 1
        for br in data.get("business_rules", []):
            reqs.append(
                RequirementItem(
                    id=f"BR-{br_idx:02d}",
                    title=f"Business Rule {br_idx}",
                    description=str(br),
                    req_type="business_rule",
                    critical_terms=self._extract_key_terms(str(br)),
                )
            )
            br_idx += 1

        return reqs
