from __future__ import annotations

import re
from typing import Any


class BusinessLogicAnalyzer:
    """Analyzes business documents against code to find alignment issues and risks."""

    def __init__(self) -> None:
        self.critical_keywords = {
            'security': ['auth', 'permission', 'encryption', 'token', 'password', 'credential'],
            'data_integrity': ['transaction', 'rollback', 'atomicity', 'consistency', 'unique', 'constraint'],
            'performance': ['cache', 'optimize', 'load', 'throughput', 'latency', 'concurrent'],
            'compliance': ['gdpr', 'pci', 'hipaa', 'audit', 'log', 'track'],
        }

    def analyze(self, business_document: str, code_snippet: str, doc_type: str = 'other') -> list[dict[str, Any]]:
        """
        Analyze business document against code for alignment and risks.
        
        Returns list of BusinessLogicFinding dicts with:
        - issue: description of the misalignment
        - severity: critical | high | medium | low
        - context: relevant business requirement
        - alignment: how code does/doesn't implement business logic
        """
        findings: list[dict[str, Any]] = []

        # Extract business requirements from document
        requirements = self._extract_requirements(business_document, doc_type)
        
        # Check each requirement against code
        for req in requirements:
            finding = self._check_requirement_coverage(req, code_snippet)
            if finding:
                findings.append(finding)

        # Check for critical business keywords coverage
        findings.extend(self._check_keyword_coverage(business_document, code_snippet))

        # Check for flawed requirement patterns
        findings.extend(self.analyze_flawed_requirements(business_document))

        # Check code for business logic vulnerabilities
        if code_snippet:
            findings.extend(self.analyze_code_business_logic(code_snippet))

        return findings

    def analyze_code_business_logic(self, code_snippet: str) -> list[dict[str, Any]]:
        """Directly analyze code for business logic vulnerabilities like threshold abuse and refund exploits."""
        from agent.review_tools import scan_python_source
        findings = scan_python_source(code_snippet)
        return [f for f in findings if f.get("category") == "business_logic"]

    def analyze_flawed_requirements(self, document: str) -> list[dict[str, Any]]:
        """Detect flawed requirement patterns that lead to severe business logic exploits."""
        flaws: list[dict[str, Any]] = []
        doc_lower = document.lower()

        # Pattern 1: Ambiguous refund of purchase price / sticker price
        if any(p in doc_lower for p in ["refund the item's purchase price", "refund purchase price", "refund item's price", "refund sticker price"]):
            flaws.append({
                "rule_id": "BIZ001",
                "flawed_pattern": "Refund the item's purchase price",
                "business_risk": "Ambiguity between MSRP/sticker price and net realized revenue (customer buys to discount, returns high-ticket item for sticker price, pocketing cash profit).",
                "mitigation": "Require proportional line-item discount attribution at transaction time (effective_paid_price = price - item_discount).",
                "severity": "critical",
                "issue": "Flawed requirement: Ambiguous purchase price refund enables 'Buy to Discount, Return to Profit' exploit",
                "context": "Pricing, promotions and refund policies",
                "alignment": "Requirements must enforce proportional discount allocation across line items",
            })

        # Pattern 2: Threshold discounts apply to cart total without clawback
        if any(p in doc_lower for p in ["threshold discounts apply to cart total", "threshold discount", "spend over", "qualifying subtotal", "minimum basket"]):
            if "clawback" not in doc_lower and "recalculate" not in doc_lower:
                flaws.append({
                    "rule_id": "BIZ002",
                    "flawed_pattern": "Threshold discounts apply to cart total without return recalculation",
                    "business_risk": "Threshold padding (adding filler items to trigger tier discount, then cancelling/returning filler items).",
                    "mitigation": "Clawback / recalculation of promotions upon partial cancellation or return.",
                    "severity": "major",
                    "issue": "Flawed requirement: Missing clawback or recalculation when partial returns drop basket below tier threshold",
                    "context": "Promotion eligibility and return policy",
                    "alignment": "Requirements must specify promotion adjustment on partial returns",
                })

        # Pattern 3: Unconstrained coupon stacking with sales
        if any(p in doc_lower for p in ["coupons stack with global sales", "coupons stack", "stack with flat coupons", "additive discount"]):
            if "floor" not in doc_lower and "cogs" not in doc_lower and "margin" not in doc_lower:
                flaws.append({
                    "rule_id": "BIZ003",
                    "flawed_pattern": "Coupons stack with global sales",
                    "business_risk": "Unintended negative margin transactions (selling below cost of goods sold).",
                    "mitigation": "Define strict evaluation ordering (percentage first, floor limits, or mutual exclusion).",
                    "severity": "major",
                    "issue": "Flawed requirement: Unconstrained additive discount stacking allows negative margins",
                    "context": "Discount stacking and profit margin controls",
                    "alignment": "Requirements must enforce post-discount basket floor and sequential evaluation",
                })

        return flaws

    def _extract_requirements(self, document: str, doc_type: str) -> list[dict[str, str]]:
        """Extract key requirements from business document."""
        requirements: list[dict[str, str]] = []
        doc_lower = document.lower()

        # Jira story parsing
        if doc_type == 'jira':
            # Look for "As a", "I want", "So that" patterns
            as_pattern = r'as a\s+([^,]+)'
            want_pattern = r'i want to\s+([^,\.]+)'
            that_pattern = r'so that\s+([^\.]+)'

            as_match = re.search(as_pattern, doc_lower)
            want_match = re.search(want_pattern, doc_lower)
            that_match = re.search(that_pattern, doc_lower)

            if want_match:
                requirements.append({
                    'user': as_match.group(1).strip() if as_match else 'user',
                    'action': want_match.group(1).strip(),
                    'reason': that_match.group(1).strip() if that_match else ''
                })

            # Look for acceptance criteria
            acceptance_pattern = r'(?:acceptance criteria|given when then)[\s\n]*([\s\S]*?)(?:\n\n|\Z)'
            ac_match = re.search(acceptance_pattern, doc_lower)
            if ac_match:
                criteria = ac_match.group(1)
                steps = re.split(r'\n\s*-\s*', criteria)
                for step in steps:
                    if step.strip():
                        requirements.append({'action': step.strip(), 'user': 'system', 'reason': 'acceptance criteria'})

        # Specification document parsing
        elif doc_type == 'specification':
            # Look for "SHALL", "MUST", "SHOULD" requirements
            for keyword in ['shall', 'must', 'should', 'will']:
                pattern = rf'{keyword}\s+([^\.]+)'
                for match in re.finditer(pattern, doc_lower):
                    requirements.append({'action': match.group(1).strip(), 'user': 'system', 'reason': f'{keyword} requirement'})

        # Requirements document parsing
        elif doc_type == 'requirements':
            # Look for numbered or bulleted requirements
            patterns = [
                r'(?:req|requirement|req-?#?)\s*\d+[\s:]*([^\n]+)',
                r'^\s*[-*]\s+([^\n]+)',
            ]
            for pattern in patterns:
                for match in re.finditer(pattern, document, re.MULTILINE | re.IGNORECASE):
                    requirements.append({'action': match.group(1).strip(), 'user': 'system', 'reason': 'requirement'})

        return requirements

    def _check_requirement_coverage(self, requirement: dict[str, str], code: str) -> dict[str, Any] | None:
        """Check if code implements the business requirement."""
        action = requirement.get('action', '').lower()
        
        # Extract key verbs and nouns from requirement
        key_terms = self._extract_key_terms(action)
        
        # Check if key terms appear in code
        code_lower = code.lower()
        coverage = sum(1 for term in key_terms if term in code_lower) / max(len(key_terms), 1)
        
        if coverage < 0.3:  # Less than 30% of key terms found
            return {
                'issue': f'Business requirement "{action[:50]}..." may not be fully implemented',
                'severity': 'high' if coverage == 0 else 'medium',
                'context': requirement.get('reason', 'specified requirement'),
                'alignment': f'Found {int(coverage * 100)}% of expected implementation indicators'
            }
        
        return None

    def _check_keyword_coverage(self, business_doc: str, code: str) -> list[dict[str, Any]]:
        """Check if business-critical keywords are handled in code."""
        findings: list[dict[str, Any]] = []
        doc_lower = business_doc.lower()
        code_lower = code.lower()

        for category, keywords in self.critical_keywords.items():
            for keyword in keywords:
                if keyword in doc_lower and keyword not in code_lower:
                    findings.append({
                        'issue': f'Business document mentions "{keyword}" but not found in code implementation',
                        'severity': 'high' if category in ['security', 'compliance'] else 'medium',
                        'context': f'{category.replace("_", " ").title()} requirement',
                        'alignment': f'Code does not address "{keyword}" handling'
                    })

        return findings

    def _check_error_handling(self, business_doc: str, code: str) -> list[dict[str, Any]]:
        """Check if business-critical operations have error handling."""
        findings: list[dict[str, Any]] = []
        
        # Check for critical operations without error handling
        critical_ops = ['database', 'payment', 'transaction', 'api', 'save', 'delete', 'update']
        code_lower = code.lower()
        
        for op in critical_ops:
            if op in business_doc.lower() and op in code_lower:
                # Check if error handling exists (try/except, if/else, logging)
                if not self._has_error_handling(code):
                    findings.append({
                        'issue': f'Business requirement mentions "{op}" but code lacks error handling',
                        'severity': 'critical',
                        'context': 'Data integrity and reliability',
                        'alignment': 'No try/except or error recovery pattern detected'
                    })
                    break

        return findings

    def _extract_key_terms(self, text: str) -> list[str]:
        """Extract key terms from text for matching."""
        # Remove common words and extract meaningful terms
        common_words = {'the', 'a', 'an', 'and', 'or', 'is', 'are', 'was', 'be', 'by', 'to', 'in', 'of', 'on', 'at', 'for'}
        words = re.findall(r'\w{3,}', text.lower())
        return [w for w in words if w not in common_words]

    def _has_error_handling(self, code: str) -> bool:
        """Check if code has error handling patterns."""
        patterns = [
            r'try\s*:',
            r'except\s+',
            r'except\s*:',
            r'raise\s+',
            r'if\s+.*error',
            r'logger\.error',
            r'catch\s*\(',
        ]
        code_lower = code.lower()
        return any(re.search(pattern, code_lower) for pattern in patterns)
