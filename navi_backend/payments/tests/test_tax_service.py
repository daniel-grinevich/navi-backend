from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

import pytest
from django.utils import timezone

from navi_backend.devices.tests.factories import NaviPortFactory
from navi_backend.orders.tests.factories import OrderFactory
from navi_backend.orders.tests.factories import OrderItemFactory
from navi_backend.payments.models import EffectiveTaxRate
from navi_backend.payments.services import StripePaymentService
from navi_backend.payments.tests.factories import PaymentFactory

SERVICE = "navi_backend.payments.services.stripe"
TAX_TASK = "navi_backend.payments.tasks.record_stripe_tax_transaction"


class TestNaviPortTaxAddress:
    def test_returns_none_without_port(self):
        assert StripePaymentService._navi_port_tax_address(None) is None

    @pytest.mark.django_db
    def test_returns_none_without_postal_code(self):
        port = NaviPortFactory.build(postal_code="")
        assert StripePaymentService._navi_port_tax_address(port) is None

    @pytest.mark.django_db
    def test_builds_address_from_port(self):
        port = NaviPortFactory.build(
            postal_code="98101",
            country="US",
            address_line_1="123 Pike St",
            city="Seattle",
            state_or_region="WA",
        )

        address = StripePaymentService._navi_port_tax_address(port)

        assert address == {
            "country": "US",
            "postal_code": "98101",
            "line1": "123 Pike St",
            "city": "Seattle",
            "state": "WA",
        }

    @pytest.mark.django_db
    def test_omits_blank_optional_fields(self):
        port = NaviPortFactory.build(
            postal_code="98101",
            country="US",
            address_line_1="",
            address_line_2="",
            city="",
            state_or_region="",
        )

        address = StripePaymentService._navi_port_tax_address(port)

        assert address == {"country": "US", "postal_code": "98101"}


@pytest.mark.django_db
class TestCalculateTax:
    def _order_with_subtotal(self, subtotal, **port_kwargs):
        port = NaviPortFactory(**port_kwargs) if port_kwargs else NaviPortFactory()
        order = OrderFactory(navi_port=port)
        OrderItemFactory(order=order, quantity=1, unit_price=Decimal(subtotal))
        return order

    def test_falls_back_to_zero_tax_without_address(self):
        port = NaviPortFactory(postal_code="")
        order = OrderFactory(navi_port=port)
        OrderItemFactory(order=order, quantity=1, unit_price=Decimal("10.00"))

        with mock.patch(SERVICE) as stripe:
            result = StripePaymentService.calculate_tax(order)
            stripe.tax.Calculation.create.assert_not_called()

        assert result["tax_amount"] == Decimal("0.00")
        assert result["total"] == order.price
        assert result["total_cents"] == int(order.price * 100)
        assert result["calculation_id"] is None

    def test_maps_stripe_calculation(self):
        order = self._order_with_subtotal("10.00", postal_code="98101")

        fake_calc = SimpleNamespace(
            id="taxcalc_123",
            tax_amount_exclusive=87,
            amount_total=1087,
        )
        with mock.patch(SERVICE) as stripe:
            stripe.tax.Calculation.create.return_value = fake_calc
            result = StripePaymentService.calculate_tax(order)
            stripe.tax.Calculation.create.assert_called_once()

        assert result["subtotal"] == Decimal("10.00")
        assert result["tax_amount"] == Decimal("0.87")
        assert result["total"] == Decimal("10.87")
        assert result["total_cents"] == 1087
        assert result["calculation_id"] == "taxcalc_123"


@pytest.mark.django_db
class TestCreateSetupIntent:
    def test_saves_card_without_charging_or_taxing(self):
        order = OrderFactory(payment=None)

        fake_intent = SimpleNamespace(id="seti_123", client_secret="seti_secret")
        with (
            mock.patch(SERVICE) as stripe,
            mock.patch.object(
                StripePaymentService,
                "get_or_create_stripe_customer",
                return_value="cus_123",
            ),
        ):
            stripe.SetupIntent.create.return_value = fake_intent
            client_secret, payment = StripePaymentService.create_setup_intent(order)
            # No money moves and no tax is computed at checkout.
            stripe.PaymentIntent.create.assert_not_called()
            stripe.tax.Calculation.create.assert_not_called()

        assert client_secret == "seti_secret"
        payment.refresh_from_db()
        assert payment.stripe_setup_intent_id == "seti_123"
        assert payment.status == "requires_setup"


@pytest.mark.django_db
class TestChargeOrder:
    def _order(self, **payment_kwargs):
        port = NaviPortFactory(postal_code="98101")
        payment = PaymentFactory(stripe_payment_intent_id=None, **payment_kwargs)
        order = OrderFactory(navi_port=port, payment=payment)
        OrderItemFactory(order=order, quantity=1, unit_price=Decimal("10.00"))
        return order, payment

    def test_charges_saved_card_off_session_and_records_async(self):
        order, payment = self._order(stripe_payment_method_id="pm_123", status="ready")

        fake_calc = SimpleNamespace(
            id="taxcalc_123", tax_amount_exclusive=87, amount_total=1087
        )
        fake_intent = SimpleNamespace(
            id="pi_abc123", status="succeeded", amount_received=1087
        )
        with (
            mock.patch(SERVICE) as stripe,
            mock.patch(TAX_TASK) as record_task,
            mock.patch.object(
                StripePaymentService,
                "get_or_create_stripe_customer",
                return_value="cus_123",
            ),
        ):
            # No cached rate for this port -> falls back to a live calculation.
            stripe.tax.Calculation.create.return_value = fake_calc
            stripe.PaymentIntent.create.return_value = fake_intent
            StripePaymentService.charge_order(order)

            _, kwargs = stripe.PaymentIntent.create.call_args
            assert kwargs["amount"] == 1087
            assert kwargs["off_session"] is True
            assert kwargs["confirm"] is True
            assert kwargs["payment_method"] == "pm_123"
            # Tax recording happens asynchronously, off the scan path.
            record_task.apply_async.assert_called_once_with(args=[str(order.id)])

        payment.refresh_from_db()
        assert payment.stripe_payment_intent_id == "pi_abc123"
        assert payment.tax_amount == Decimal("0.87")
        assert payment.total_amount == Decimal("10.87")
        assert payment.amount_received == Decimal("10.87")
        assert payment.status == "succeeded"

    def test_uses_cached_rate_without_calling_stripe_tax(self):
        order, payment = self._order(stripe_payment_method_id="pm_123", status="ready")
        EffectiveTaxRate.objects.create(
            navi_port=order.navi_port,
            rate=Decimal("0.1000"),
            effective_date=timezone.localdate(),
        )
        fake_intent = SimpleNamespace(
            id="pi_abc123", status="succeeded", amount_received=1100
        )
        with (
            mock.patch(SERVICE) as stripe,
            mock.patch(TAX_TASK),
            mock.patch.object(
                StripePaymentService,
                "get_or_create_stripe_customer",
                return_value="cus_123",
            ),
        ):
            stripe.PaymentIntent.create.return_value = fake_intent
            StripePaymentService.charge_order(order)

            # Cached rate -> no live tax API call in the scan path.
            stripe.tax.Calculation.create.assert_not_called()
            _, kwargs = stripe.PaymentIntent.create.call_args
            assert kwargs["amount"] == 1100  # $10.00 + 10%

        payment.refresh_from_db()
        assert payment.tax_amount == Decimal("1.00")
        assert payment.total_amount == Decimal("11.00")

    def test_resolves_payment_method_from_setup_intent(self):
        order, payment = self._order(
            stripe_setup_intent_id="seti_123",
            stripe_payment_method_id="",
            status="ready",
        )

        fake_calc = SimpleNamespace(
            id="taxcalc_1", tax_amount_exclusive=0, amount_total=1000
        )
        fake_intent = SimpleNamespace(
            id="pi_abc123", status="succeeded", amount_received=1000
        )
        with (
            mock.patch(SERVICE) as stripe,
            mock.patch(TAX_TASK),
            mock.patch.object(
                StripePaymentService,
                "get_or_create_stripe_customer",
                return_value="cus_123",
            ),
        ):
            stripe.SetupIntent.retrieve.return_value = SimpleNamespace(
                payment_method="pm_from_setup"
            )
            stripe.tax.Calculation.create.return_value = fake_calc
            stripe.PaymentIntent.create.return_value = fake_intent
            StripePaymentService.charge_order(order)

            _, kwargs = stripe.PaymentIntent.create.call_args
            assert kwargs["payment_method"] == "pm_from_setup"

        payment.refresh_from_db()
        assert payment.stripe_payment_method_id == "pm_from_setup"


@pytest.mark.django_db
class TestRecordTaxTransaction:
    def _succeeded_order(self, **payment_kwargs):
        port = NaviPortFactory(postal_code="98101")
        payment = PaymentFactory(
            status="succeeded",
            stripe_payment_intent_id="pi_abc123",
            subtotal=Decimal("10.00"),
            **payment_kwargs,
        )
        order = OrderFactory(navi_port=port, payment=payment)
        return order, payment

    def test_records_transaction(self):
        order, payment = self._succeeded_order(stripe_tax_transaction_id="")

        with mock.patch(SERVICE) as stripe:
            stripe.tax.Calculation.create.return_value = SimpleNamespace(id="taxcalc_9")
            stripe.tax.Transaction.create_from_calculation.return_value = (
                SimpleNamespace(id="taxtxn_9")
            )
            StripePaymentService.record_tax_transaction(order.id)

        payment.refresh_from_db()
        assert payment.stripe_tax_calculation_id == "taxcalc_9"
        assert payment.stripe_tax_transaction_id == "taxtxn_9"

    def test_noop_when_not_succeeded(self):
        port = NaviPortFactory(postal_code="98101")
        payment = PaymentFactory(status="ready", subtotal=Decimal("10.00"))
        order = OrderFactory(navi_port=port, payment=payment)

        with mock.patch(SERVICE) as stripe:
            StripePaymentService.record_tax_transaction(order.id)
            stripe.tax.Calculation.create.assert_not_called()

    def test_noop_when_already_recorded(self):
        order, _ = self._succeeded_order(stripe_tax_transaction_id="taxtxn_existing")

        with mock.patch(SERVICE) as stripe:
            StripePaymentService.record_tax_transaction(order.id)
            stripe.tax.Calculation.create.assert_not_called()
