"""Policy engine and compliance gate.

Pure and deterministic by construction — this package must never import from
`app.db`, `app.integrations` or `app.executors`. If a rule needs a new fact,
add a field to CaseSnapshot and populate it at the call site.
"""
