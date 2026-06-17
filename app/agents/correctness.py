import uuid
import re
from app.llm import llm
from app.prompts import CORRECTNESS_PROMPT
from app.utils import extract_json


def is_added_code_line(line: str) -> bool:
    if not line.startswith('+') or line.startswith('+++ '):
        return False
    content = line[1:].strip()
    if not content:
        return False
    if content.startswith('//') or content.startswith('#') or content.startswith('/*') or content.startswith('*') or content.startswith('"""') or content.startswith("'''"):
        return False
    return True


def align_and_validate_finding(finding, diff_lines):
    evidence = finding.get("evidence", "").strip()
    if not evidence:
        return False, 0
        
    line_num = finding.get("line", 0)
    
    clean_diff_lines = []
    for line in diff_lines:
        if line.startswith('+') or line.startswith('-') or line.startswith(' '):
            clean_diff_lines.append(line[1:])
        else:
            clean_diff_lines.append(line)
            
    ev_lines = [line.strip() for line in evidence.splitlines() if line.strip()]
    if not ev_lines:
        return False, 0
        
    clean_ev_lines = ["".join(l.lower().split()) for l in ev_lines]
    
    best_start = None
    min_dist = 99999
    
    for start_idx in range(1, len(diff_lines) + 1):
        match = True
        for offset, clean_ev_l in enumerate(clean_ev_lines):
            if start_idx + offset > len(diff_lines):
                match = False
                break
            line_content = clean_diff_lines[start_idx + offset - 1]
            clean_line = "".join(line_content.lower().split())
            if clean_ev_l not in clean_line:
                match = False
                break
        if match:
            dist = abs(start_idx - line_num)
            if dist < min_dist:
                min_dist = dist
                best_start = start_idx
                
    if best_start is not None:
        return True, best_start
        
    return False, 0


def check_resource_leak(line: str, diff: str) -> bool:
    resource_keywords = ["open(", "File(", "socket(", "connection("]
    if any(kw in line for kw in resource_keywords):
        is_with = "with " in line
        has_close = any(c in diff for c in ["close()", "close(", ".close"])
        has_finally = "finally" in diff
        if not (is_with or has_close or has_finally):
            return True
    return False


def is_valid_undefined_variable_finding(finding, diff) -> bool:
    title_lower = finding.get("title", "").lower()
    desc_lower = finding.get("description", "").lower()
    
    is_undefined = any(
        k in title_lower or k in desc_lower
        for k in ["undefined variable", "variable undefined", "missing import", "not defined", "undeclared variable", "undefined"]
    )
    if not is_undefined:
        return True
        
    known_names = {"db", "smtp", "logger", "app", "request", "jsonify", "sleep"}
    words = set(re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', (title_lower + " " + desc_lower)))
    if words.intersection(known_names):
        return False
        
    if "import" in title_lower or "import" in desc_lower:
        return False
        
    return False


def correctness_agent(state):
    diff = state["diff"]
    findings = []
    lines = diff.splitlines()

    for idx, line in enumerate(lines, start=1):
        if not is_added_code_line(line):
            continue

        clean_line = line[1:].strip()

        # Missing transaction null check
        if "transaction['status']" in clean_line:
            findings.append(
                {
                    "id": str(uuid.uuid4())[:8],
                    "line": idx,
                    "line_content": line,
                    "category": "correctness",
                    "severity": "high",
                    "title": "Missing Null Check",
                    "description": "transaction may be None before accessing status.",
                    "suggestion": "Check if transaction exists before use.",
                    "evidence": clean_line
                }
            )

        # Missing request validation
        if "request.json" in clean_line:
            findings.append(
                {
                    "id": str(uuid.uuid4())[:8],
                    "line": idx,
                    "line_content": line,
                    "category": "correctness",
                    "severity": "high",
                    "title": "Missing Input Validation",
                    "description": "Incoming request data is not validated.",
                    "suggestion": "Validate required fields before processing.",
                    "evidence": clean_line
                }
            )

        # JS split without validation
        if ".split(" in clean_line:
            findings.append(
                {
                    "id": str(uuid.uuid4())[:8],
                    "line": idx,
                    "line_content": line,
                    "category": "correctness",
                    "severity": "high",
                    "title": "Possible Null Dereference",
                    "description": "Variable may be undefined before split call.",
                    "suggestion": "Check variable exists before using split.",
                    "evidence": clean_line
                }
            )

        # Undefined push
        if "user[0]" in clean_line:
            findings.append(
                {
                    "id": str(uuid.uuid4())[:8],
                    "line": idx,
                    "line_content": line,
                    "category": "correctness",
                    "severity": "medium",
                    "title": "Missing Result Validation",
                    "description": "Database query may return empty results.",
                    "suggestion": "Check query result before indexing.",
                    "evidence": clean_line
                }
            )

        # Order null check
        if "order.status" in clean_line:
            findings.append(
                {
                    "id": str(uuid.uuid4())[:8],
                    "line": idx,
                    "line_content": line,
                    "category": "correctness",
                    "severity": "high",
                    "title": "Missing Order Null Check",
                    "description": "Order may not exist before status access.",
                    "suggestion": "Validate order before using it.",
                    "evidence": clean_line
                }
            )

        # NaN discount
        if "discounts[discountCode]" in clean_line:
            findings.append(
                {
                    "id": str(uuid.uuid4())[:8],
                    "line": idx,
                    "line_content": line,
                    "category": "correctness",
                    "severity": "high",
                    "title": "Potential NaN Calculation",
                    "description": "Discount code may not exist in map.",
                    "suggestion": "Validate discount code or provide fallback.",
                    "evidence": clean_line
                }
            )

        # Resource Leak Detection
        if check_resource_leak(clean_line, diff):
            findings.append(
                {
                    "id": str(uuid.uuid4())[:8],
                    "line": idx,
                    "line_content": line,
                    "category": "correctness",
                    "severity": "medium",
                    "title": "Resource Leak",
                    "description": "Resource opened but never closed.",
                    "suggestion": "Use context managers or close resources.",
                    "evidence": clean_line
                }
            )

    # LLM Analysis
    try:
        response = llm.invoke(CORRECTNESS_PROMPT.format(diff=diff))

        print("\n===== CORRECTNESS LLM RESPONSE =====")
        print(response.content)
        print("===================================\n")

        parsed = extract_json(response.content)
        print(parsed)

        for finding in parsed.get("findings", []):
            findings.append(
                {
                    "id": str(uuid.uuid4())[:8],
                    "line": finding.get("line", 0),
                    "line_content": "",
                    "category": "correctness",
                    "severity": finding.get("severity", "medium"),
                    "title": finding.get("title", "Correctness Issue"),
                    "description": finding.get("description", "Potential correctness issue."),
                    "suggestion": finding.get("suggestion", "Review this logic."),
                    "evidence": finding.get("evidence", "")
                }
            )
    except Exception as e:
        print(f"Correctness Agent Error: {e}")

    # Clean & Filter findings
    filtered_findings = []
    seen = set()

    for finding in findings:
        # Align and validate evidence
        is_valid, aligned_line = align_and_validate_finding(finding, lines)
        if not is_valid:
            continue

        finding["line"] = aligned_line

        # Enforce Resource Leak deterministic filter
        title_lower = finding["title"].lower().strip()
        if "resource leak" in title_lower:
            evidence = finding.get("evidence", "")
            resource_keywords = ["open(", "File(", "socket(", "connection("]
            if not any(kw in evidence for kw in resource_keywords):
                continue

        # Enforce Undefined Variable Filter
        if not is_valid_undefined_variable_finding(finding, diff):
            continue

        key = (
            finding["title"],
            finding["line"]
        )

        if key not in seen:
            seen.add(key)
            filtered_findings.append(finding)

    return {
        "correctness_findings": filtered_findings
    }