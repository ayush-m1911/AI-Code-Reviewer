from typing import List, Literal, Optional
from pydantic import BaseModel


Severity = Literal[
    "critical",
    "high",
    "medium",
    "low"
]

Category = Literal[
    "security",
    "performance",
    "correctness",
    "style",
    "test_coverage"
]


class ReviewRequest(BaseModel):
    diff: str
    language: str
    context: Optional[str] = None


class Finding(BaseModel):
    id: str
    line: int
    line_content: str

    category: Category
    severity: Severity

    title: str
    description: str
    suggestion: str
    evidence: str = ""



class AgentFindingsCount(BaseModel):
    security: int = 0
    performance: int = 0
    correctness: int = 0
    style: int = 0
    test_coverage: int = 0


class ReviewReport(BaseModel):
    pr_summary: str

    verdict: Literal[
        "approve",
        "request_changes",
        "needs_discussion"
    ]

    verdict_reason: str

    overall_severity: Literal[
        "critical",
        "high",
        "medium",
        "low",
        "clean"
    ]

    findings: List[Finding]

    positive_observations: List[str]

    missing_tests: List[str]

    agent_findings_count: AgentFindingsCount

    processing_time_ms: int


class StoredReview(BaseModel):
    review_id: str
    created_at: str
    report: ReviewReport