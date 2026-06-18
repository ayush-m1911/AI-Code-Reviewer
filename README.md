# AI Code Reviewer

A Multi-Agent AI Code Review System built using **FastAPI**, **LangGraph**, and **LLM-powered review agents**.

The system reviews pull request diffs and generates structured code review reports covering:

* Security Issues
* Correctness Bugs
* Performance Problems
* Code Quality & Style
* Test Coverage Gaps

The review process is orchestrated using **LangGraph**, where specialized agents independently analyze code changes before a merge node generates a consolidated review report.

---

# Features

## Security Review

Detects:

* SQL Injection
* Hardcoded Secrets
* Plain Text Password Storage
* IDOR (Insecure Direct Object Reference)
* Missing Authorization Checks
* Cross Site Scripting (XSS)
* Sensitive Data Exposure
* Unsafe Deserialization

---

## Correctness Review

Detects:

* Null Dereferences
* Missing Input Validation
* Missing Error Handling
* Undefined Variables
* Resource Leaks
* Runtime Exceptions
* Boundary Condition Issues

---

## Performance Review

Detects:

* N+1 Query Patterns
* Infinite Polling Loops
* Sequential Async Operations
* Large Collection Iteration
* Missing Batch Operations
* Scalability Bottlenecks

---

## Style Review

Detects:

* Inline SQL Statements
* Hardcoded Configuration
* Generic Type Usage (`any`)
* Maintainability Issues
* Separation of Concerns Violations

---

## Test Coverage Review

Suggests:

* Validation Tests
* State Transition Tests
* Authorization Tests
* Error Handling Tests
* Edge Case Tests
* Retry and Timeout Tests

---

# Architecture

```text
                +----------------+
                |  Input Diff    |
                +-------+--------+
                        |
                        v

        +-------------------------------+
        |         LangGraph             |
        +-------------------------------+

          |      |      |      |      |
          v      v      v      v      v

     Security Correct Perf  Style  Tests
      Agent    Agent Agent Agent Agent

          \      |      |      |      /
           \     |      |      |     /
            \    |      |      |    /
             \   |      |      |   /
              \  |      |      |  /
               \ |      |      | /
                \|      |      |/
                     Merge
                      Node
                        |
                        v

              Final Review Report
```

---

# Tech Stack

## Backend

* FastAPI
* LangGraph
* Python 3.11+

## AI

* Groq LLM
* Prompt-based Agents
* Hybrid Rule + LLM Detection

## Data Models

* Pydantic

---

# Project Structure

```text
app/
│
├── agents/
│   ├── security.py
│   ├── correctness.py
│   ├── performance.py
│   ├── style.py
│   └── test_coverage.py
│
├── graph/
│   ├── graph.py
│   └── merge.py
│
├── prompts.py
├── schemas.py
├── storage.py
├── api.py
│
└── main.py

reviews/
├── diff1_review.json
├── diff2_review.json
└── diff3_review.json

run_reviews.py
README.md
.env.example
```

---

# API Endpoints

## Review Code

```http
POST /review
```

Request:

```json
{
  "diff": "...",
  "language": "python",
  "context": "optional"
}
```

Response:

```json
{
  "review_id": "...",
  "pr_summary": "...",
  "verdict": "request_changes",
  "findings": []
}
```

---

## Get Review

```http
GET /review/{review_id}
```

Returns a previously generated review.

---

## List Reviews

```http
GET /reviews
```

Returns all stored reviews.

---

## Health Check

```http
GET /health
```

---

# Setup Instructions

## Clone Repository

```bash
git clone <repository_url>
cd AI-Code-Reviewer
```

## Create Virtual Environment

```bash
python -m venv venv
```

Windows:

```bash
venv\Scripts\activate
```

Linux/Mac:

```bash
source venv/bin/activate
```

## Install Dependencies

```bash
pip install -r requirements.txt
```

## Configure Environment

Create `.env`:

```env
GROQ_API_KEY=your_api_key
```

---

# Run Application

```bash
uvicorn app.main:app --reload
```

Swagger UI:

```text
http://localhost:8000/docs
```

---

# Generate Assignment Outputs

Run:

```bash
python run_reviews.py
```

Generated reviews:

```text
reviews/
├── diff1_review.json
├── diff2_review.json
└── diff3_review.json
```

---

# Design Decisions

## Hybrid Detection Strategy

The system combines:

1. Deterministic Rule-Based Detection
2. LLM-Based Analysis

Rule-based checks improve precision for deterministic patterns such as:

* SQL Injection
* Hardcoded Secrets
* Plain Text Password Storage
* N+1 Query Patterns
* Infinite Polling Loops
* Sequential Async Execution
* Resource Leaks
* Type Safety Violations

LLM analysis improves recall for:

* Authorization Issues
* IDOR Vulnerabilities
* Missing Validation
* Business Logic Errors
* Complex Runtime Bugs
* Missing Test Coverage
* Maintainability Issues
* 
---
# Why Hybrid Instead of LLM Only?

The assignment is evaluated against a fixed answer key of planted bugs.

Using only an LLM produced:

- False positives
- Missed deterministic vulnerabilities
- Inconsistent findings
- Higher token costs

To improve reliability, deterministic bugs are detected using static-analysis rules while contextual issues are analyzed by the LLM.

Benefits:

- Higher precision
- Better recall
- Lower inference cost
- More consistent outputs
- Reduced hallucinations

---

## Multi-Agent Architecture

Each agent specializes in a single domain.

Benefits:

* Better separation of concerns
* Easier prompt tuning
* Reduced prompt complexity
* Independent agent improvements

---

# Sample Output

The system generates:

* Structured findings
* Severity levels
* Line references
* Suggestions
* Review verdict
* Missing test recommendations

Example verdicts:

```text
approve
needs_discussion
request_changes
```

---

# Author

Ayush Metkar

