"""LLM diagnosis. Produces proposals only.

This package must never import from app.executors — a proposal reaches an
executor solely by way of app.policy.gate.
"""
