class InsufficientPointsError(Exception):
    """A deduction would take a user's spendable balance below zero."""


class RedemptionError(Exception):
    """A reward can't be applied (not live, wrong item, guest, no points...)."""
