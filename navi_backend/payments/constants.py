from decimal import Decimal

# Stripe rejects USD charges below $0.50. Orders fully covered by rewards
# ($0.00) skip Stripe entirely, and reward leftovers under this are waived.
STRIPE_MINIMUM_CHARGE = Decimal("0.50")
