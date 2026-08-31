"""Durable delayed execution.

One interface (base.Scheduler), one implementation (poller). The requirement
is durable delay across days; Inngest is one way to buy it, a due-date column
plus a claiming poller is another, and the latter has no vendor dependency.
"""
