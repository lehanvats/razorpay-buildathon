"""Executors — the only code that acts on the outside world.

Every executor takes a Verdict, never a Proposal, and is wrapped by
executors.base.with_audit so it cannot act without leaving a trail.
"""
