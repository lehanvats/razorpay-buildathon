"""Recoup — a payment-failure recovery agent for Indian payment rails.

The design invariant everything hangs on: the LLM can only propose; the
policy gate is the sole path to any money action. See app/policy/gate.py.
"""
