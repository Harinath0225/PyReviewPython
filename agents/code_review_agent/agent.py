import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from google import adk

# Ensure repository root is on sys.path
repo_root = Path(__file__).resolve().parent.parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

# Load .env
load_dotenv(repo_root / ".env")

# Ensure GOOGLE_API_KEY is populated from GEMINI_API_KEY if needed
gemini_key = os.getenv("GEMINI_API_KEY")
if gemini_key and not os.getenv("GOOGLE_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = gemini_key

# Recommended model for code review features
model_name = os.getenv("LLM_MODEL") or os.getenv("GEMMA_MODEL") or os.getenv("GEMINI_MODEL") or "gemma-4-26b-a4b-it"


def scan_python_code(code_snippet: str) -> str:
    """Scans Python source code using AST analysis for security vulnerabilities (SQL injection, Command injection, Path traversal, and business logic flaws).

    Args:
        code_snippet: Python code text to inspect.

    Returns:
        JSON string containing detected vulnerabilities, severity levels, rule IDs, and remediation guidance.
    """
    import json
    from agent.review_tools import scan_python_source

    findings = scan_python_source(code_snippet)
    return json.dumps({"findings_count": len(findings), "findings": findings}, indent=2)


def check_prompt_safety(text: str) -> str:
    """Checks untrusted input text or instructions against Model Armor guardrails for prompt injection or system prompt extraction.

    Args:
        text: Untrusted user input text.

    Returns:
        JSON string containing threat flags and blocked status.
    """
    import json
    from security.model_armor import ModelArmorService

    result = ModelArmorService().check(text)
    return json.dumps(result, indent=2)


def lookup_owasp_guidance(vulnerability_category: str) -> str:
    """Provides OWASP Top 10 context, CWE mapping, and remediation best practices.

    Args:
        vulnerability_category: Name or type of vulnerability (e.g., 'Injection', 'Broken Access Control').

    Returns:
        Remediation advice and OWASP documentation references.
    """
    from agent.review_tools import OWASP_TOP_10

    matches = [cat for cat in OWASP_TOP_10 if vulnerability_category.lower() in cat.lower()]
    return f"OWASP Top 10 Category Matches: {matches}. Always use parameterized queries, safe execution APIs, and boundary checks."


def analyze_and_map_business_requirements(business_requirement: str, code_snippet: str) -> str:
    """Analyzes business requirements (BRD text, Jira ticket, user story, or screenshot data URL)

    and maps them to Python code elements (traceability matrix, coverage score, flaws).

    Args:
        business_requirement: Text or base64 screenshot data URL of the business requirement or Jira story.
        code_snippet: Python code snippet to map against requirements.

    Returns:
        JSON string containing business summary, requirements list, traceability matrix, and coverage score.
    """
    import json
    from agent.business_requirement_subagent import BusinessRequirementSubagent

    subagent = BusinessRequirementSubagent()
    result = subagent.analyze_and_map(
        business_input=business_requirement,
        code_snippet=code_snippet,
    )
    return json.dumps(result, indent=2)


def extract_jira_or_brd_screenshot(screenshot_data_url_or_path: str) -> str:
    """Extracts structured business requirements, user stories, and acceptance criteria from a Jira ticket or BRD screenshot.

    Args:
        screenshot_data_url_or_path: Base64 data URL (e.g. data:image/png;base64,...) or file path to image.

    Returns:
        JSON string containing extracted ticket key, title, summary, user stories, acceptance criteria, and business rules.
    """
    import json
    from agent.business_requirement_subagent import BusinessRequirementSubagent

    subagent = BusinessRequirementSubagent()
    result = subagent.extract_from_screenshot(screenshot_data_url_or_path)
    return json.dumps(result, indent=2)


from google.genai import types

safety_settings = [
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
        threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
    ),
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
    ),
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
        threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
    ),
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
    ),
]

business_requirement_subagent = adk.Agent(
    name="business_requirement_subagent",
    description="Subagent specializing in parsing BRDs, Jira tickets, and Jira/BRD screenshots, creating summaries, and mapping business requirements to the codebase.",
    model=model_name,
    instruction=(
        "You are an expert business systems analyst and software architecture alignment reviewer. "
        "Your role is to: "
        "1. Ingest BRDs, Jira user stories, acceptance criteria, or Jira screenshots. "
        "2. Create a clear, structured summary of business objectives, user stories, and acceptance criteria. "
        "3. Map each business requirement to the codebase AST components (traceability matrix). "
        "4. Identify any unimplemented, misaligned, or vulnerable business logic (e.g. refund price exploits, threshold padding, unconstrained stacking). "
        "5. Provide actionable recommendations to achieve 100% compliance with business requirements."
    ),
    tools=[analyze_and_map_business_requirements, extract_jira_or_brd_screenshot],
    generate_content_config=types.GenerateContentConfig(
        safety_settings=safety_settings,
        temperature=0.2,
    ),
)

root_agent = adk.Agent(
    name="code_review_agent",
    description="Agentic Code Review & Security Analysis Engine powered by Gemini.",
    model=model_name,
    sub_agents=[business_requirement_subagent],
    instruction=(
        "You are an authorized defensive security engineer, static code analyzer, and code quality assistant. "
        "Your role is to help software developers write robust, clean, and defensively protected Python applications. "
        "When code is provided for review or vulnerability assessment: "
        "1. First call the `scan_python_code` tool to run deterministic AST static security analysis. "
        "2. If business requirements, Jira tickets, or Jira screenshots are present, delegate to `business_requirement_subagent` "
        "   or call `analyze_and_map_business_requirements` to create a business summary and traceability matrix. "
        "3. If applicable, call `lookup_owasp_guidance` to correlate OWASP Top 10 categories. "
        "4. Explain the identified security and business logic risks constructively, focusing on root causes (such as unescaped input, shell execution, or purchase price refund ambiguity). "
        "5. Always provide safe, refactored Python code demonstrating standard defensive remediations: "
        "   - Use parameterized queries (e.g., cursor.execute('SELECT ... ?', (param,))) instead of string formatting. "
        "   - Use safe subprocess execution (e.g., subprocess.run(['cmd', arg], shell=False)) instead of shell=True. "
        "   - Use os.path.realpath / path boundary checks for file paths. "
        "   - Enforce proportional discount attribution (effective_paid_price) and threshold clawback rules. "
        "Do not provide weaponized attack payloads or malicious instructions. Focus entirely on constructive remediation and secure development."
    ),
    tools=[
        scan_python_code,
        check_prompt_safety,
        lookup_owasp_guidance,
        analyze_and_map_business_requirements,
        extract_jira_or_brd_screenshot,
    ],
    generate_content_config=types.GenerateContentConfig(
        safety_settings=safety_settings,
        temperature=0.2,
    ),
)
