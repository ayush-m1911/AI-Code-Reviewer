import uuid
from app.llm import llm
from app.prompts import TEST_COVERAGE_PROMPT
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


def test_coverage_agent(state):
    diff = state["diff"]
    findings = []
    lines = diff.splitlines()

    for idx, line in enumerate(lines, start=1):
        if not is_added_code_line(line):
            continue

        clean_line = line[1:].strip()
        line_lower = clean_line.lower()

        # Payment / Refund Logic
        if "refund" in line_lower:
            findings.append(
                {
                    "id": str(uuid.uuid4())[:8],
                    "line": idx,
                    "line_content": line,
                    "category": "test_coverage",
                    "severity": "medium",
                    "title": "Missing Refund Edge Case Tests",
                    "description": "Refund logic was modified but edge cases are not verified.",
                    "suggestion": "Add unit tests covering: 1) already refunded transaction, 2) missing transaction, 3) unauthorized refund, and 4) SMTP failure.",
                    "evidence": clean_line
                }
            )

        # Password Reset / Hashing
        if "password" in line_lower and ("reset" in line_lower or "update" in line_lower):
            findings.append(
                {
                    "id": str(uuid.uuid4())[:8],
                    "line": idx,
                    "line_content": line,
                    "category": "test_coverage",
                    "severity": "medium",
                    "title": "Missing Password Reset Tests",
                    "description": "Password reset or update logic has no accompanying verification tests.",
                    "suggestion": "Add unit tests verifying: 1) user not found, 2) password hashing verification, 3) unauthorized reset, and 4) invalid email format.",
                    "evidence": clean_line
                }
            )

        # Order Cancellation
        if "cancel" in line_lower and "order" in line_lower:
            findings.append(
                {
                    "id": str(uuid.uuid4())[:8],
                    "line": idx,
                    "line_content": line,
                    "category": "test_coverage",
                    "severity": "medium",
                    "title": "Missing Order Cancellation Tests",
                    "description": "Order cancellation flow lacks critical validation tests.",
                    "suggestion": "Add unit tests for: 1) already cancelled order, 2) invalid order ID, 3) permission denied (unauthorized), and 4) notification failure.",
                    "evidence": clean_line
                }
            )

        # Discount Logic
        if "discount" in line_lower:
            findings.append(
                {
                    "id": str(uuid.uuid4())[:8],
                    "line": idx,
                    "line_content": line,
                    "category": "test_coverage",
                    "severity": "medium",
                    "title": "Missing Discount Validation Tests",
                    "description": "Discount calculation logic may fail for invalid or expired codes.",
                    "suggestion": "Add unit tests checking: 1) invalid discount code, 2) expired discount code, and 3) unsupported discount code.",
                    "evidence": clean_line
                }
            )

        # State Changes
        if "status" in line_lower:
            findings.append(
                {
                    "id": str(uuid.uuid4())[:8],
                    "line": idx,
                    "line_content": line,
                    "category": "test_coverage",
                    "severity": "low",
                    "title": "Missing State Transition Tests",
                    "description": "Status updates require validation of state transitions.",
                    "suggestion": "Add unit tests verifying valid and invalid state transitions.",
                    "evidence": clean_line
                }
            )

    try:
        response = llm.invoke(TEST_COVERAGE_PROMPT.format(diff=diff))

        print("\n===== TEST COVERAGE LLM RESPONSE =====")
        print(response.content)
        print("======================================\n")

        parsed = extract_json(response.content)
        print(parsed)

        for finding in parsed.get("findings", []):
            findings.append(
                {
                    "id": str(uuid.uuid4())[:8],
                    "line": finding.get("line", 0),
                    "line_content": "",
                    "category": "test_coverage",
                    "severity": finding.get("severity", "medium"),
                    "title": finding.get("title", "Missing Test Scenario"),
                    "description": finding.get("description", ""),
                    "suggestion": finding.get("suggestion", ""),
                    "evidence": finding.get("evidence", "")
                }
            )
    except Exception as e:
        print(f"Test Coverage Agent Error: {e}")

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
        "test_findings": filtered_findings
    }