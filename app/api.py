import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException

from app.schemas import (
    ReviewRequest,
    ReviewReport,
    StoredReview
)
from app.storage import reviews_store
from app.graph import review_graph

router = APIRouter()


@router.post("/review")
def review_code(request: ReviewRequest):

    review_id = str(uuid.uuid4())

    state = {
        "diff": request.diff,
        "language": request.language,
        "context": request.context or "",

        "security_findings": [],
        "performance_findings": [],
        "correctness_findings": [],
        "style_findings": [],
        "test_findings": [],

        "review_report": {}
    }

    try:
        
        result = review_graph.invoke(state)
        
        print("\n===== GRAPH OUTPUT =====")
        print(result)
        print("========================\n")

        report = ReviewReport(
            **result["review_report"]
        )

        stored = StoredReview(
            review_id=review_id,
            created_at=datetime.utcnow().isoformat(),
            report=report
        )

        reviews_store[review_id] = stored

        return {
            "review_id": review_id,
            **report.model_dump()
        }

    except Exception as e:

        print("\nReview Generation Error:")
        print(str(e))

        raise HTTPException(
            status_code=500,
            detail=f"Review generation failed: {str(e)}"
        )


@router.get("/review/{review_id}")
def get_review(review_id: str):

    review = reviews_store.get(review_id)

    if review is None:
        raise HTTPException(
            status_code=404,
            detail="Review not found"
        )

    return review


@router.get("/reviews")
def list_reviews():

    response = []

    for review in reviews_store.values():

        response.append(
            {
                "review_id":
                    review.review_id,

                "pr_summary":
                    review.report.pr_summary,

                "verdict":
                    review.report.verdict,

                "overall_severity":
                    review.report.overall_severity,

                "created_at":
                    review.created_at
            }
        )

    return response


@router.get("/health")
def health():

    return {
        "status": "healthy",
        "langgraph": True,
        "storage": True
    }