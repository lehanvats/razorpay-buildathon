"""Pydantic contracts.

proposal.py is the LLM boundary (what the model may say, what the gate
answers). api.py is the HTTP boundary the React app consumes. Neither
imports the ORM models.
"""
