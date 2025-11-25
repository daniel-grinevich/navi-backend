import uuid
from decimal import Decimal

import factory

from navi_backend.core.tests.factories import AuditFactory
from navi_backend.core.tests.factories import StatusFactory
from navi_backend.core.tests.factories import UpdateRecordFactory
from navi_backend.payments.models import Payment


class PaymentFactory(
    AuditFactory,
    UpdateRecordFactory,
    StatusFactory,
    factory.django.DjangoModelFactory,
):
    class Meta:
        model = Payment

    stripe_payment_intent_id = factory.LazyFunction(
        lambda: f"pi_{uuid.uuid4().hex[:24]}"
    )
    amount_received = factory.LazyFunction(lambda: Decimal("5.00"))
    currency = "usd"
    status = "requires_capture"
