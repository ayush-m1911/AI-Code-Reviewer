import uuid
from app.llm import llm
from app.prompts import STYLE_PROMPT
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


def style_agent(state):
    diff = state["diff"]
    findings = []
    lines = diff.splitlines()

    for idx, line in enumerate(lines, start=1):
        if not is_added_code_line(line):
            continue

        clean_line = line[1:].strip()

        # Magic Numbers
        if "sleep(1000)" in clean_line:
            findings.append(
                {
                    "id": str(uuid.uuid4())[:8],
                    "line": idx,
                    "line_content": line,
                    "category": "style",
                    "severity": "low",
                    "title": "Magic Number",
                    "description": "Hardcoded numeric value reduces maintainability.",
                    "suggestion": "Extract the value into a named constant.",
                    "evidence": clean_line
                }
            )

        # Hardcoded URLs
        if "http://" in clean_line or "https://" in clean_line:
            findings.append(
                {
                    "id": str(uuid.uuid4())[:8],
                    "line": idx,
                    "line_content": line,
                    "category": "style",
                    "severity": "low",
                    "title": "Hardcoded Configuration",
                    "description": "Configuration value appears directly in source code.",
                    "suggestion": "Move configuration into environment variables or config files.",
                    "evidence": clean_line
                }
            )

        # Hardcoded Secret (maintainability angle)
        if "SECRET_KEY" in clean_line:
            findings.append(
                {
                    "id": str(uuid.uuid4())[:8],
                    "line": idx,
                    "line_content": line,
                    "category": "style",
                    "severity": "low",
                    "title": "Hardcoded Configuration Value",
                    "description": "Configuration is embedded directly in code.",
                    "suggestion": "Store configuration separately from application logic.",
                    "evidence": clean_line
                }
            )

        # Large Inline SQL
        if any(k in clean_line for k in ["SELECT", "UPDATE", "DELETE", "INSERT"]):
            findings.append(
                {
                    "id": str(uuid.uuid4())[:8],
                    "line": idx,
                    "line_content": line,
                    "category": "style",
                    "severity": "low",
                    "title": "Inline SQL Statement",
                    "description": "Embedding SQL directly in business logic reduces maintainability.",
                    "suggestion": "Move queries into a repository or data-access layer.",
                    "evidence": clean_line
                }
            )

        # Long Chained Calls
        if clean_line.count(".") > 4:
            findings.append(
                {
                    "id": str(uuid.uuid4())[:8],
                    "line": idx,
                    "line_content": line,
                    "category": "style",
                    "severity": "low",
                    "title": "Complex Chained Expression",
                    "description": "Long chained expressions can reduce readability.",
                    "suggestion": "Break logic into intermediate variables.",
                    "evidence": clean_line
                }
            )

    try:
        response = llm.invoke(STYLE_PROMPT.format(diff=diff))

        print("\n===== STYLE LLM RESPONSE =====")
        print(response.content)
        print("================================\n")

        parsed = extract_json(response.content)
        print(parsed)

        for finding in parsed.get("findings", []):
            findings.append(
                {
                    "id": str(uuid.uuid4())[:8],
                    "line": finding.get("line", 0),
                    "line_content": "",
                    "category": "style",
                    "severity": finding.get("severity", "low"),
                    "title": finding.get("title", "Style Issue"),
                    "description": finding.get("description", "Potential maintainability issue."),
                    "suggestion": finding.get("suggestion", "Consider refactoring."),
                    "evidence": finding.get("evidence", "")
                }
            )
    except Exception as e:
        print(f"Style Agent Error: {e}")

    # Clean & Filter findings
    filtered_findings = []
    seen = set()

    for finding in findings:
        # Align and validate evidence
        is_valid, aligned_line = align_and_validate_finding(finding, lines)
        if not is_valid:
            continue

        finding["line"] = aligned_line

        key = (
            finding["title"],
            finding["line"]
        )

        if key not in seen:
            seen.add(key)
            filtered_findings.append(finding)

    return {
        "style_findings": filtered_findings
    }