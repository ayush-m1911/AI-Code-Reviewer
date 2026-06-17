import json
import re


def extract_json(text: str):
    """
    Extract JSON from LLM response.
    """

    match = re.search(
        r"\{.*\}",
        text,
        re.DOTALL
    )

    if not match:
        return {"findings": []}

    try:
        return json.loads(match.group())
    except Exception:
        return {"findings": []}