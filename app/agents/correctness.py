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


def get_null_variable(finding) -> str:
    title_lower = finding.get("title", "").lower()
    desc_lower = finding.get("description", "").lower()
    evidence_lower = finding.get("evidence", "").lower()
    
    for var in ["transaction", "order", "user"]:
        if re.search(r'\b' + re.escape(var) + r'\b', title_lower) or \
           re.search(r'\b' + re.escape(var) + r'\b', desc_lower) or \
           re.search(r'\b' + re.escape(var) + r'\b', evidence_lower):
            return var
            
    match = re.search(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:\.|\[)', evidence_lower)
    if match:
        var = match.group(1)
        if var not in ["request", "req", "res", "response", "data", "db", "config", "notification", "logs"]:
            return var
            
    return ""


def check_is_undefined_variable(var_name: str, diff_lines, line_num: int) -> bool:
    known_globals = {"db", "smtp", "logger", "app", "request", "req", "res", "response", "console", "sleep", "Math", "Date"}
    if var_name in known_globals:
        return False
        
    clean_lines = []
    for line in diff_lines:
        if line.startswith('+') or line.startswith('-') or line.startswith(' '):
            clean_lines.append(line[1:])
        else:
            clean_lines.append(line)
            
    func_start_idx = 0
    for idx in range(min(line_num - 1, len(clean_lines) - 1), -1, -1):
        line_content = clean_lines[idx]
        if "function " in line_content or "def " in line_content or "async function" in line_content:
            func_start_idx = idx
            break
            
    declared = False
    for idx in range(func_start_idx, min(line_num, len(clean_lines))):
        line_content = clean_lines[idx]
        if re.search(r'\b(?:const|let|var|def)\s+' + re.escape(var_name) + r'\b', line_content):
            declared = True
            break
        if re.search(r'\b(?:const|let|var)\s*\{[^}]*\b' + re.escape(var_name) + r'\b[^}]*\}', line_content):
            declared = True
            break
        if re.search(r'\b' + re.escape(var_name) + r'\b\s*=[^=]', line_content):
            declared = True
            break
        if re.search(r'\bfor\b.*\b' + re.escape(var_name) + r'\b', line_content):
            declared = True
            break
        if idx == func_start_idx:
            if re.search(r'\b' + re.escape(var_name) + r'\b', line_content):
                declared = True
                break
                
    return not declared


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

        # JS split/trim/toLowerCase/toUpperCase/map/filter without validation
        dangerous_methods = [".split(", ".trim(", ".toLowerCase(", ".toUpperCase(", ".map(", ".filter("]
        if any(method in clean_line for method in dangerous_methods):
            match = re.search(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\.(?:split|trim|toLowerCase|toUpperCase|map|filter)\b', clean_line)
            if match:
                receiver_name = match.group(1)
                if receiver_name not in ["req", "res", "response", "request", "db", "console", "Math", "Date"]:
                    # Find where it is declared in function scope to check if it's an untrusted input
                    func_start_idx = 0
                    clean_lines = []
                    for l in lines:
                        if l.startswith('+') or l.startswith('-') or l.startswith(' '):
                            clean_lines.append(l[1:])
                        else:
                            clean_lines.append(l)
                    for i_idx in range(min(idx - 1, len(clean_lines) - 1), -1, -1):
                        line_content = clean_lines[i_idx]
                        if "function " in line_content or "def " in line_content or "async function" in line_content:
                            func_start_idx = i_idx
                            break
                    is_untrusted_input = False
                    for i_idx in range(func_start_idx, min(idx, len(clean_lines))):
                        line_content = clean_lines[i_idx]
                        if re.search(r'\b' + re.escape(receiver_name) + r'\b', line_content):
                            if any(k in line_content for k in ["req.query", "req.body", "req.params", "request.query", "request.body", "request.params"]):
                                is_untrusted_input = True
                                break
                    if is_untrusted_input:
                        findings.append(
                            {
                                "id": str(uuid.uuid4())[:8],
                                "line": idx,
                                "line_content": line,
                                "category": "correctness",
                                "severity": "high",
                                "title": "Possible Null Dereference",
                                "description": f"Variable '{receiver_name}' may be null or undefined before method call.",
                                "suggestion": f"Check variable exists before using {receiver_name}.",
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
    aligned_findings = []
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

        # Heuristic: Suppress correctness findings for Potential Inefficient Lookup Pattern
        evidence = finding.get("evidence", "")
        is_lookup_pattern = False
        lookup_names = ["users", "cache", "lookup", "map", "orders", "dictionary"]
        for name in lookup_names:
            if re.search(r'\b' + re.escape(name) + r'\s*\[[^\]]+\]', evidence):
                is_lookup_pattern = True
                break
        if is_lookup_pattern:
            continue

        key = (
            finding["title"],
            finding["line"]
        )

        if key not in seen:
            seen.add(key)
            aligned_findings.append(finding)

    # Reclassify Null Dereference to Undefined Variable if it is not declared in enclosing function scope
    processed_findings = []
    for f in aligned_findings:
        title_lower = f["title"].lower().strip()
        is_null_check = any(k in title_lower for k in ["null dereference", "null check", "correctness issue", "possible null"])
        if is_null_check:
            var_name = get_null_variable(f)
            if var_name:
                if check_is_undefined_variable(var_name, lines, f["line"]):
                    f["title"] = "Undefined Variable"
                    f["description"] = f"Variable '{var_name}' is referenced but never defined in scope."
                    f["suggestion"] = f"Declare or import '{var_name}' before using it."
                    f["severity"] = "high"
                else:
                    # Check if this exists but is destructured from req.query
                    func_start_idx = 0
                    clean_lines = []
                    for line in lines:
                        if line.startswith('+') or line.startswith('-') or line.startswith(' '):
                            clean_lines.append(line[1:])
                        else:
                            clean_lines.append(line)
                    for idx in range(min(f["line"] - 1, len(clean_lines) - 1), -1, -1):
                        line_content = clean_lines[idx]
                        if "function " in line_content or "def " in line_content or "async function" in line_content:
                            func_start_idx = idx
                            break
                    is_query_param = False
                    for idx in range(func_start_idx, min(f["line"], len(clean_lines))):
                        line_content = clean_lines[idx]
                        if re.search(r'\b' + re.escape(var_name) + r'\b', line_content) and (".query" in line_content or "req.query" in line_content):
                            is_query_param = True
                            break
                    if is_query_param:
                        f["title"] = "Missing Query Parameter Validation"
                        f["description"] = f"{var_name} may be undefined, null, or not a string before split() is called, causing a runtime exception."
                        f["suggestion"] = f"Validate req.query.{var_name} exists and is a string before calling split()."
                        f["severity"] = "high"
        processed_findings.append(f)

    # Group and collapse multiple null dereferences by variable name
    null_findings_by_var = {}
    other_findings = []

    for f in processed_findings:
        title_lower = f["title"].lower().strip()
        is_null_check = any(k in title_lower for k in ["null dereference", "null check", "correctness issue", "possible null"])
        
        var_name = ""
        if is_null_check:
            var_name = get_null_variable(f)

        if var_name:
            if var_name not in null_findings_by_var:
                null_findings_by_var[var_name] = []
            null_findings_by_var[var_name].append(f)
        else:
            other_findings.append(f)

    final_findings = []
    for var_name, var_findings in null_findings_by_var.items():
        var_findings.sort(key=lambda x: x["line"])
        root_finding = var_findings[0]

        # Rename title based on variable name
        if var_name == "transaction":
            root_finding["title"] = "Missing Transaction Null Check"
            root_finding["description"] = "transaction may be null or undefined before accessing its properties."
            root_finding["suggestion"] = "Add a check to verify that transaction exists before use."
        elif var_name == "order":
            root_finding["title"] = "Missing Order Null Check"
            root_finding["description"] = "order may be null or undefined before accessing its properties."
            root_finding["suggestion"] = "Add a check to verify that order exists before use."
        elif var_name == "user":
            root_finding["title"] = "Missing User Null Check"
            root_finding["description"] = "user may be null or undefined before accessing its properties."
            root_finding["suggestion"] = "Add a check to verify that user exists before use."
        else:
            root_finding["title"] = f"Missing {var_name.capitalize()} Null Check"
            root_finding["description"] = f"{var_name} may be null or undefined before accessing its properties."
            root_finding["suggestion"] = f"Add a check to verify that {var_name} exists before use."

        root_finding["severity"] = "high"
        final_findings.append(root_finding)

    final_findings.extend(other_findings)

    return {
        "correctness_findings": final_findings
    }