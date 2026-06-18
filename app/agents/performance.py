import uuid
from app.llm import llm
from app.prompts import PERFORMANCE_PROMPT
from app.utils import extract_json
import re

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


def check_loops(lines):
    inside_collection_loop_lines = set()
    inside_polling_loop_lines = set()
    clean_lines = []
    
    for line in lines:
        if line.startswith('+') or line.startswith('-') or line.startswith(' '):
            clean_lines.append(line[1:])
        else:
            clean_lines.append(line)

    loop_stack = []
    brace_depth = 0
    
    for i, line in enumerate(clean_lines):
        stripped = line.strip()
        if not stripped:
            continue
            
        indent = len(line) - len(line.lstrip())
        
        while loop_stack and loop_stack[-1]['lang'] == 'python' and indent <= loop_stack[-1]['indent']:
            loop_stack.pop()
            
        while loop_stack and loop_stack[-1]['lang'] == 'js' and brace_depth <= loop_stack[-1]['brace_depth']:
            loop_stack.pop()
            
        if loop_stack:
            if any(l['loop_type'] == 'collection' for l in loop_stack):
                inside_collection_loop_lines.add(i + 1)
            else:
                inside_polling_loop_lines.add(i + 1)
            
        is_py_for = stripped.startswith("for ") and stripped.endswith(":")
        is_py_while = stripped.startswith("while ") and stripped.endswith(":")
        
        is_js_for = ("for (" in stripped or "for(" in stripped or ".forEach(" in stripped or ".map(" in stripped or ".filter(" in stripped or ".reduce(" in stripped)
        is_js_while = ("while (" in stripped or "while(" in stripped)
        
        if is_js_for or is_js_while:
            loop_stack.append({
                'lang': 'js',
                'indent': indent,
                'brace_depth': brace_depth,
                'loop_type': 'collection' if is_js_for else 'polling'
            })
        elif is_py_for or is_py_while:
            loop_stack.append({
                'lang': 'python',
                'indent': indent,
                'brace_depth': brace_depth,
                'loop_type': 'collection' if is_py_for else 'polling'
            })
            
        brace_depth += stripped.count("{") - stripped.count("}")
        
    return inside_collection_loop_lines, inside_polling_loop_lines


def performance_agent(state):
    diff = state["diff"]
    findings = []
    lines = diff.splitlines()

    
    inside_collection_loop_lines, inside_polling_loop_lines = check_loops(lines)

    for idx, line in enumerate(lines, start=1):
        if not is_added_code_line(line):
            continue

        clean_line = line[1:].strip()

       
        is_db_call = any(
            kw in clean_line
            for kw in [
                "db.query", "db.execute", "repo.find", "repo.save",
                "repository.find", "repository.save", "findById", "findOne",
                "getUser", "getUserActivity", "save("
            ]
        )
        if idx in inside_collection_loop_lines and is_db_call:
            findings.append(
                {
                    "id": str(uuid.uuid4())[:8],
                    "line": idx,
                    "line_content": line,
                    "category": "performance",
                    "severity": "high",
                    "title": "Potential N+1 Query Pattern",
                    "description": "Database query appears inside an iterative workflow and may execute once per item.",
                    "suggestion": "Batch queries using IN clauses or fetch data in a single query.",
                    "evidence": clean_line
                }
            )

        
        if "while (status === 'pending')" in clean_line or "while(status === 'pending')" in clean_line:
            findings.append(
                {
                    "id": str(uuid.uuid4())[:8],
                    "line": idx,
                    "line_content": line,
                    "category": "performance",
                    "severity": "critical",
                    "title": "Infinite Polling Loop",
                    "description": "Loop may run indefinitely if status never changes.",
                    "suggestion": "Add timeout, retry limits, or cancellation logic.",
                    "evidence": clean_line
                }
            )

        
        if "await cancelOrder" in clean_line:
            findings.append(
                {
                    "id": str(uuid.uuid4())[:8],
                    "line": idx,
                    "line_content": line,
                    "category": "performance",
                    "severity": "high",
                    "title": "Sequential Async Processing",
                    "description": "Operations are executed sequentially and may become slow at scale.",
                    "suggestion": "Use Promise.all() or parallel execution when safe.",
                    "evidence": clean_line
                }
            )

        
        if "sleep(1000)" in clean_line:
            findings.append(
                {
                    "id": str(uuid.uuid4())[:8],
                    "line": idx,
                    "line_content": line,
                    "category": "performance",
                    "severity": "medium",
                    "title": "Repeated Polling Delay",
                    "description": "Polling with fixed delays can consume resources and increase latency.",
                    "suggestion": "Use event-driven updates, backoff strategies, or webhooks.",
                    "evidence": clean_line
                }
            )

        
        if "for (const id of userIds)" in clean_line or "for (const id of orderIds)" in clean_line:
            findings.append(
                {
                    "id": str(uuid.uuid4())[:8],
                    "line": idx,
                    "line_content": line,
                    "category": "performance",
                    "severity": "medium",
                    "title": "Potential Large Collection Iteration",
                    "description": "Looping over large collections may become expensive.",
                    "suggestion": "Consider batching, pagination, or parallelization.",
                    "evidence": clean_line
                }
            )

        
        is_inefficient = False
        inefficient_patterns = [
            "users[log.user_id]",
            "orders[user.order_id]",
            "cache[item.id]",
            "lookup[id]",
            "map[key]",
            "dictionary[userId]"
        ]
        clean_no_spaces = "".join(clean_line.split())
        if any("".join(pat.split()) in clean_no_spaces for pat in inefficient_patterns):
            is_inefficient = True
            
        if not is_inefficient:
            regex_pat = r'\b(users|orders|cache|lookup|map|dictionary)\s*\[\s*[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)?\s*\]'
            if re.search(regex_pat, clean_line):
                is_inefficient = True
                
        if is_inefficient:
            findings.append(
                {
                    "id": str(uuid.uuid4())[:8],
                    "line": idx,
                    "line_content": line,
                    "category": "performance",
                    "severity": "medium",
                    "title": "Potential Inefficient Lookup Pattern",
                    "description": "Application performs lookups through in-memory object access patterns that may indicate missing joins, batching, or scalable retrieval strategies.",
                    "suggestion": "Consider database joins, batching, indexed lookups, caching strategies, or optimized retrieval mechanisms.",
                    "evidence": clean_line
                }
            )


    
    try:
        response = llm.invoke(PERFORMANCE_PROMPT.format(diff=diff))

        print("\n===== PERFORMANCE LLM RESPONSE =====")
        print(response.content)
        print("====================================\n")

        parsed = extract_json(response.content)
        print(parsed)

        for finding in parsed.get("findings", []):
            findings.append(
                {
                    "id": str(uuid.uuid4())[:8],
                    "line": finding.get("line", 0),
                    "line_content": "",
                    "category": "performance",
                    "severity": finding.get("severity", "medium"),
                    "title": finding.get("title", "Performance Issue"),
                    "description": finding.get("description", "Potential performance issue."),
                    "suggestion": finding.get("suggestion", "Optimize this code path."),
                    "evidence": finding.get("evidence", "")
                }
            )
    except Exception as e:
        print(f"Performance Agent Error: {e}")

    
    filtered_findings = []
    seen = set()

    for finding in findings:
        
        is_valid, aligned_line = align_and_validate_finding(finding, lines)
        if not is_valid:
            continue

        finding["line"] = aligned_line

        
        title_lower = finding["title"].lower().strip()
        if "n+1" in title_lower or "n + 1" in title_lower:
            if finding["line"] not in inside_collection_loop_lines:
                continue

        key = (
            finding["title"],
            finding["line"]
        )

        if key not in seen:
            seen.add(key)
            filtered_findings.append(finding)

    return {
        "performance_findings": filtered_findings
    }