"""
graph/__init__.py
Exports the compiled finassist_graph singleton for use by the chatbot route.
"""
from app.graph.graph import finassist_graph

__all__ = ["finassist_graph"]
