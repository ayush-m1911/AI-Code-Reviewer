from typing import TypedDict


class ReviewState(TypedDict):
    diff: str
    language: str
    context: str

    security_findings: list
    performance_findings: list
    correctness_findings: list
    style_findings: list
    test_findings: list

    review_report: dict