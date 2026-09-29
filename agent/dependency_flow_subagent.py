from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from backend.app.config import get_settings

try:
    from google import genai
except Exception:
    genai = None


class DependencyFlowSubagent:
    """Specialized Subagent to generate a Mermaid dependency flow diagram
    showing which parts of the code and functionality are impacted by changes,
    helping developers identify edge cases (e.g. backend impacts from frontend changes).
    """

    def __init__(self, model_name: str | None = None) -> None:
        self.settings = get_settings()
        self.model_name = (
            model_name
            or getattr(self.settings, "diagram_llm_model", None)
            or os.getenv("DIAGRAM_LLM_MODEL")
            or os.getenv("MERMAID_LLM_MODEL")
            or os.getenv("DIAGRAM_MODEL")
            or "gemini-3.1-flash-lite"
        )

    def generate_diagram(
        self,
        code_snippet: str | None = None,
        repo_path: str | None = None,
        business_documents: list[dict[str, Any]] | None = None,
        model_name: str | None = None,
    ) -> str:
        """Analyzes the code and business logic to generate a Mermaid flow diagram."""
        target_model = model_name or self.model_name
        code_text = code_snippet or ""
        if not code_text and repo_path and Path(repo_path).exists():
            code_text = self._load_repo_code_sample(repo_path)
            
        doc_texts = []
        if business_documents:
            for doc in business_documents:
                if isinstance(doc, dict):
                    content = doc.get("content") or doc.get("text") or doc.get("raw_text") or ""
                    if content:
                        doc_texts.append(str(content))
        
        business_context = "\n\n".join(doc_texts)

        api_key = self.settings.gemini_api_key or os.getenv("GOOGLE_API_KEY")
        if not api_key or genai is None:
            return self._fallback_diagram()

        try:
            client = genai.Client(api_key=api_key)
            prompt = (
                "You are an expert software architect. Analyze the provided code and business requirements. "
                "Generate a detailed Mermaid dependency flow diagram (graph TD) that shows how the functionality flows, "
                "and clearly identifies which parts of the code (frontend and backend) are executed and impacted by changes. "
                "This helps QA and developers not miss edge cases.\n\n"
                "Return ONLY the valid Mermaid diagram code, starting with 'graph TD' or 'flowchart TD'. "
                "Do not include markdown fences like ```mermaid.\n"
                "CRITICAL: You MUST use newlines to separate statements. Do NOT put the entire diagram on a single line. "
                "Each node, edge, subgraph, and end statement MUST be on its own line.\n\n"
            )
            
            if business_context:
                prompt += f"Business Requirements:\n{business_context}\n\n"
            if code_text:
                prompt += f"Code:\n{code_text[:100000]}\n\n"

            response = client.models.generate_content(
                model=target_model,
                contents=[prompt],
            )
            
            diagram = getattr(response, "text", "") or ""
            
            # Clean up markdown fences if present
            if diagram.startswith("```mermaid"):
                diagram = diagram.replace("```mermaid", "", 1)
            elif diagram.startswith("```"):
                diagram = diagram.replace("```", "", 1)
            diagram = diagram.strip()
            if diagram.endswith("```"):
                diagram = diagram[:-3].strip()
            
            if not (diagram.startswith("graph ") or diagram.startswith("flowchart ")):
                diagram = "graph TD\n" + diagram
                
            return diagram
        except Exception:
            return self._fallback_diagram()

    def _load_repo_code_sample(self, repo_path: str) -> str:
        combined = []
        try:
            root = Path(repo_path)
            for p in root.rglob("*.py"):
                if p.is_file() and "test" not in p.name.lower():
                    try:
                        content = p.read_text(encoding='utf-8')
                        combined.append(f"--- {p.name} ---\n{content[:2000]}")
                        if len(combined) > 10:
                            break
                    except Exception:
                        continue
        except Exception:
            pass
        return "\n".join(combined)

    def _fallback_diagram(self) -> str:
        return (
            "graph TD\n"
            "    A[Frontend Client] -->|API Request| B(Backend Service)\n"
            "    B --> C{Validation}\n"
            "    C -->|Pass| D[Process Logic]\n"
            "    C -->|Fail| E[Return Error]\n"
            "    D --> F[(Database)]\n"
            "    F --> D\n"
            "    D --> G[Response to Frontend]\n"
            "    style A fill:#f9f,stroke:#333,stroke-width:2px\n"
            "    style B fill:#bbf,stroke:#333,stroke-width:2px"
        )
