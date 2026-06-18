import json
from pathlib import Path

import requests


BASE_URL = "http://127.0.0.1:8000"

DIFF_FILES = [
    ("diff1_python.txt", "python"),
    ("diff2_javascript.txt", "javascript"),
    ("diff3_typescript.txt", "typescript")
]


def review_diff(diff_file, language):

    with open(diff_file, "r", encoding="utf-8") as f:
        diff_content = f.read()

    payload = {
        "diff": diff_content,
        "language": language,
        "context": f"Automated review for {diff_file}"
    }

    response = requests.post(
        f"{BASE_URL}/review",
        json=payload,
        timeout=120
    )

    response.raise_for_status()

    return response.json()


def save_review(diff_file, review):

    reviews_dir = Path("reviews")
    reviews_dir.mkdir(exist_ok=True)

    output_name = (
        Path(diff_file)
        .stem
        .replace("_python", "")
        .replace("_javascript", "")
        .replace("_typescript", "")
        + "_review.json"
    )

    output_path = reviews_dir / output_name

    with open(
        output_path,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            review,
            f,
            indent=2
        )

    print(
        f"Saved {output_path}"
    )


def main():

    print("\nStarting AI Code Reviews...\n")

    for diff_file, language in DIFF_FILES:

        print(
            f"Reviewing {diff_file}..."
        )

        try:

            review = review_diff(
                diff_file,
                language
            )

            save_review(
                diff_file,
                review
            )

            print(
                f"Verdict: {review['verdict']}"
            )

            print(
                f"Severity: {review['overall_severity']}"
            )

            print(
                f"Findings: {len(review['findings'])}"
            )

            print("-" * 50)

        except Exception as e:

            print(
                f"Error reviewing {diff_file}: {e}"
            )

    print("\nAll reviews completed.\n")


if __name__ == "__main__":
    main()