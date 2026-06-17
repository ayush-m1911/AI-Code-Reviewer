from langgraph.graph import StateGraph, START, END

from app.state import ReviewState

from app.agents.security import security_agent
from app.agents.performance import performance_agent
from app.agents.correctness import correctness_agent
from app.agents.style import style_agent
from app.agents.test_coverage import test_coverage_agent

from app.merge import merge_node

builder = StateGraph(ReviewState)

builder.add_node("security", security_agent)
builder.add_node("performance", performance_agent)
builder.add_node("correctness", correctness_agent)
builder.add_node("style", style_agent)
builder.add_node("test", test_coverage_agent)

builder.add_node("merge", merge_node)

builder.add_edge(START, "security")
builder.add_edge(START, "performance")
builder.add_edge(START, "correctness")
builder.add_edge(START, "style")
builder.add_edge(START, "test")
builder.add_edge("security", "merge")
builder.add_edge("performance", "merge")
builder.add_edge("correctness", "merge")
builder.add_edge("style", "merge")
builder.add_edge("test", "merge")
builder.add_edge("merge", END)

review_graph = builder.compile()