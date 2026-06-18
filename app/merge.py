import re

def normalize(text):

    if not text:
        return ""

    return (
        text.lower()
        .strip()
        .replace("-", "")
        .replace("_", "")
    )

def normalize_title(title: str) -> str:
    if not title:
        return ""
    t = title.lower().strip()
    # Remove punctuation
    t = re.sub(r'[^\w\s]', '', t)
    # Remove common words
    for word in ["statement", "pattern", "issue", "potential"]:
        t = t.replace(word, "")
    t = " ".join(t.split())
    # Handle plural/singular
    if t.endswith("s"):
        if t.endswith("ies"):
            t = t[:-3] + "y"
        else:
            t = t[:-1]
    return t.strip()
def merge_node(state):

    security = state.get(
        "security_findings",
        []
    )

    performance = state.get(
        "performance_findings",
        []
    )

    correctness = state.get(
        "correctness_findings",
        []
    )

    style = state.get(
        "style_findings",
        []
    )

    test = state.get(
        "test_findings",
        []
    )

    findings = (
        security
        + performance
        + correctness
        + style
        + test
    )

    # ----------------------------
    # Deduplicate
    # ----------------------------

    unique_findings = []
    seen = set()

    for finding in findings:

        category = finding.get(
            "category",
            ""
        )

        title = finding.get("title", "")
        norm_title = normalize_title(title)

        key = (
            category,
            norm_title,
            finding.get("line", 0)
        )

        if key not in seen:

            seen.add(key)

            unique_findings.append(
                finding
            )

    findings = unique_findings

    # Suppress Missing Authorization if IDOR exists on the same line
    idor_lines = {f.get("line", 0) for f in findings if f.get("title", "").lower().strip() == "idor"}
    filtered_findings = []
    for f in findings:
        title_lower = f.get("title", "").lower().strip()
        if title_lower == "missing authorization" and f.get("line", 0) in idor_lines:
            continue
        filtered_findings.append(f)
    findings = filtered_findings

    # ----------------------------
    # Count findings
    # ----------------------------

    counts = {
    "security": 0,
    "performance": 0,
    "correctness": 0,
    "style": 0,
    "test_coverage": 0
}

    for finding in findings:

        category = finding.get(
            "category",
            ""
        )

        if category in counts:
            counts[category] += 1

    # ----------------------------
    # Determine overall severity
    # ----------------------------

    severities = [
        finding["severity"]
        for finding in findings
    ]

    if "critical" in severities:
        overall_severity = "critical"

    elif "high" in severities:
        overall_severity = "high"

    elif "medium" in severities:
        overall_severity = "medium"

    elif "low" in severities:
        overall_severity = "low"

    else:
        overall_severity = "clean"

    # ----------------------------
    # Verdict Logic
    # ----------------------------

    critical_count = sum(
        1
        for f in findings
        if f["severity"] == "critical"
    )

    high_count = sum(
        1
        for f in findings
        if f["severity"] == "high"
    )

    if critical_count > 0:

        verdict = "request_changes"

        verdict_reason = (
            "Critical issues were found."
        )

    elif high_count >= 2:

        verdict = "request_changes"

        verdict_reason = (
            "Multiple high severity issues were found."
        )

    elif high_count == 1:

        verdict = "needs_discussion"

        verdict_reason = (
            "A high severity issue requires review."
        )

    elif len(findings) > 0:

        verdict = "needs_discussion"

        verdict_reason = (
            "Some issues were identified."
        )

    else:

        verdict = "approve"

        verdict_reason = (
            "No significant issues found."
        )

    # ----------------------------
    # Positive Observations
    # ----------------------------

    positives = []

    if len(security) == 0:
        positives.append(
            "No security issues detected."
        )

    if len(correctness) == 0:
        positives.append(
            "No correctness issues detected."
        )

    if len(performance) == 0:
        positives.append(
            "No performance issues detected."
        )

    if len(positives) == 0:
        positives.append(
            "Code structure appears reasonable."
        )

    # ----------------------------
    # Missing Tests
    # ----------------------------

    missing_tests = []

    for finding in test:

        missing_tests.append(
            finding["suggestion"]
        )

    missing_tests = list(
        set(missing_tests)
    )

    # ----------------------------
    # PR Summary
    # ----------------------------

    total_findings = len(findings)

    pr_summary = (
        f"Automated review found "
        f"{total_findings} issue(s) "
        f"across security, correctness, "
        f"performance, style, and test coverage."
    )

    # ----------------------------
    # Final Report
    # ----------------------------

    review_report = {
        "pr_summary": pr_summary,

        "verdict": verdict,

        "verdict_reason":
            verdict_reason,

        "overall_severity":
            overall_severity,

        "findings":
            findings,

        "positive_observations":
            positives,

        "missing_tests":
            missing_tests,

        "agent_findings_count":
            counts,

        "processing_time_ms":
            0
    }

    return {
        "review_report":
            review_report
    }