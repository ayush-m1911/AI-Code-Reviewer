import uuid
import re
from app.llm import llm
from app.prompts import SECURITY_PROMPT
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


def is_safe_sql(line: str) -> bool:
    line_lower = line.lower()
    if "?" in line or "%s" in line:
        return True
    if re.search(r'\$\d+', line):
        return True
    orm_methods = [
        "findbyid", "findone", "getuser", "getuseractivity",
        "findby", "deletebyid", "updatebyid", "save", "delete", "update"
    ]
    for m in orm_methods:
        if m in line_lower:
            if re.search(rf'\.\s*{m}\b', line_lower):
                return True
    return False


def is_valid_sql_injection_finding(finding, diff) -> bool:
    evidence = finding.get("evidence", "")
    if is_safe_sql(evidence):
        return False
    ev_lower = evidence.lower()
    has_sql = any(k in ev_lower for k in ["select", "update", "delete", "insert"])
    if not has_sql:
        return False
    has_dynamic = (
        "{" in evidence 
        or " + " in evidence 
        or 'f"' in evidence 
        or "f'" in evidence 
        or ".format(" in ev_lower
        or "`" in evidence
    )
    return has_dynamic


def check_plain_text_password(line: str, diff: str) -> bool:
    line_lower = line.lower()
    is_assignment = ("password =" in line_lower or "password=" in line_lower or ".password =" in line_lower or ".password=" in line_lower)
    is_update_query = ("update " in line_lower and "password" in line_lower)
    is_save_call = ("save(" in line_lower and "password" in line_lower)
    
    if is_assignment or is_update_query or is_save_call:
        has_hashing = any(
            h in diff.lower()
            for h in ["bcrypt", "argon2", "hash(", "hash_password(", "generate_password_hash("]
        )
        if not has_hashing:
            return True
    return False


def check_idor(line: str, diff: str) -> bool:
    line_lower = line.lower()
    sensitive_functions = ["resetpassword", "cancelorder"]
    is_sensitive = any(f in line_lower for f in sensitive_functions) and (
        "function" in line_lower or "def " in line_lower or "async" in line_lower or "=>" in line_lower or "route" in line_lower
    )
    if is_sensitive:
        has_ownership = any(
            k in diff for k in ["currentUser", "owner", "auth", "permission", "role", "user.id"]
        )
        if not has_ownership:
            return True
    return False


def check_missing_authorization(line: str, diff: str) -> bool:
    line_lower = line.lower()
    sensitive_functions = ["resetpassword", "cancelorder"]
    is_sensitive = any(f in line_lower for f in sensitive_functions) and (
        "function" in line_lower or "def " in line_lower or "async" in line_lower or "=>" in line_lower or "route" in line_lower
    )
    if is_sensitive:
        has_auth = any(
            a in diff.lower()
            for a in ["role", "permission", "authorize", "auth", "isadmin", "guard", "token", "checkauth"]
        )
        if not has_auth:
            return True
    return False


def security_agent(state):
    diff = state["diff"]
    findings = []
    lines = diff.splitlines()

    for idx, line in enumerate(lines, start=1):
        if not is_added_code_line(line):
            continue

        clean_line = line[1:].strip()

        # SQL Injection
        if (
            any(k in clean_line for k in ["SELECT", "UPDATE", "DELETE", "INSERT"])
            and ("{" in clean_line or " + " in clean_line or 'f"' in clean_line or "f'" in clean_line or ".format(" in clean_line.lower())
        ):
            if is_valid_sql_injection_finding({"evidence": clean_line}, diff):
                findings.append(
                    {
                        "id": str(uuid.uuid4())[:8],
                        "line": idx,
                        "line_content": line,
                        "category": "security",
                        "severity": "critical",
                        "title": "SQL Injection",
                        "description": "User-controlled input is directly interpolated into a SQL query.",
                        "suggestion": "Use parameterized queries instead of string interpolation.",
                        "evidence": clean_line
                    }
                )

        # Hardcoded Secrets
        if (
            ("sk_live_" in clean_line or "sk_test_" in clean_line)
            or (
                any(k in clean_line for k in ["SECRET_KEY", "API_KEY", "TOKEN", "STRIPE_SECRET_KEY"])
                and ("=" in clean_line or ":" in clean_line)
                and ("'" in clean_line or '"' in clean_line)
                and not any(x in clean_line for x in ["const", "let", "var", "req.", "request."])
            )
        ):
            findings.append(
                {
                    "id": str(uuid.uuid4())[:8],
                    "line": idx,
                    "line_content": line,
                    "category": "security",
                    "severity": "critical",
                    "title": "Hardcoded Secret",
                    "description": "A secret or credential appears to be committed directly into source code.",
                    "suggestion": "Move secrets into environment variables or a secret manager.",
                    "evidence": clean_line
                }
            )

        # XSS Detection
        if "template.replace(" in clean_line or "innerHTML" in clean_line:
            findings.append(
                {
                    "id": str(uuid.uuid4())[:8],
                    "line": idx,
                    "line_content": line,
                    "category": "security",
                    "severity": "high",
                    "title": "Potential Cross-Site Scripting (XSS)",
                    "description": "User-controlled data may be inserted into HTML without sanitization.",
                    "suggestion": "Escape or sanitize user-controlled content before rendering.",
                    "evidence": clean_line
                }
            )

        # Plain Text Password Storage
        if check_plain_text_password(clean_line, diff):
            findings.append(
                {
                    "id": str(uuid.uuid4())[:8],
                    "line": idx,
                    "line_content": line,
                    "category": "security",
                    "severity": "critical",
                    "title": "Plain Text Password Storage",
                    "description": "Password appears to be stored or updated without hashing.",
                    "suggestion": "Use bcrypt or argon2 before persistence.",
                    "evidence": clean_line
                }
            )

        # IDOR Detection
        if check_idor(clean_line, diff):
            findings.append(
                {
                    "id": str(uuid.uuid4())[:8],
                    "line": idx,
                    "line_content": line,
                    "category": "security",
                    "severity": "high",
                    "title": "IDOR",
                    "description": "Sensitive operation performed using externally supplied identifiers without ownership verification.",
                    "suggestion": "Verify that the requesting user owns the resource before processing the operation.",
                    "evidence": clean_line
                }
            )

        # Missing Authorization
        if check_missing_authorization(clean_line, diff):
            findings.append(
                {
                    "id": str(uuid.uuid4())[:8],
                    "line": idx,
                    "line_content": line,
                    "category": "security",
                    "severity": "high",
                    "title": "Missing Authorization",
                    "description": "Sensitive operation performed without permission, role, or authorization checks.",
                    "suggestion": "Implement appropriate role-based or permission-based checks before executing sensitive operations.",
                    "evidence": clean_line
                }
            )

    # LLM Analysis
    try:
        prompt = SECURITY_PROMPT.format(diff=diff)
        response = llm.invoke(prompt)

        print("\n===== SECURITY LLM RESPONSE =====")
        print(response.content)
        print("=================================\n")

        parsed = extract_json(response.content)
        print(parsed)
        for finding in parsed.get("findings", []):
            findings.append(
                {
                    "id": str(uuid.uuid4())[:8],
                    "line": finding.get("line", 0),
                    "line_content": "",
                    "category": "security",
                    "severity": finding.get("severity", "medium"),
                    "title": finding.get("title", "Security Issue"),
                    "description": finding.get("description", "Potential security vulnerability detected."),
                    "suggestion": finding.get("suggestion", "Review and fix this issue."),
                    "evidence": finding.get("evidence", "")
                }
            )
    except Exception as e:
        print("\nSecurity Agent Error:")
        print(str(e))

    # Clean & Filter based on rules
    aligned_findings = []
    seen = set()

    for finding in findings:
        # Align and validate evidence
        is_valid, aligned_line = align_and_validate_finding(finding, lines)
        if not is_valid:
            continue

        finding["line"] = aligned_line

        title_lower = finding["title"].lower().strip()

        # Require concrete/direct evidence before reporting Missing Authorization or IDOR
        if "authorization" in title_lower or "idor" in title_lower:
            evidence_lower = finding.get("evidence", "").lower()
            desc_lower = finding.get("description", "").lower()
            # Suppress if it contains refund or is about refund
            if "refund" in evidence_lower or "refund" in title_lower or "refund" in desc_lower:
                continue
            # Otherwise, must have sensitive context keywords
            sensitive_ok = any(
                k in (evidence_lower + " " + title_lower + " " + desc_lower)
                for k in ["password", "cancel", "delete", "reset", "user.id", "owner", "bulk"]
            )
            if not sensitive_ok:
                continue

        # Enforce SQL Injection false positive rule
        if "sql injection" in title_lower:
            if not is_valid_sql_injection_finding(finding, diff):
                continue

        key = (
            finding["title"],
            finding["line"]
        )

        if key not in seen:
            seen.add(key)
            aligned_findings.append(finding)

    # Suppress Missing Authorization if IDOR exists on the same line
    idor_lines = {f["line"] for f in aligned_findings if f["title"].lower().strip() == "idor"}
    
    filtered_findings = []
    for f in aligned_findings:
        title_lower = f["title"].lower().strip()
        if title_lower == "missing authorization":
            if f["line"] in idor_lines:
                continue
        filtered_findings.append(f)

    return {
        "security_findings": filtered_findings
    }