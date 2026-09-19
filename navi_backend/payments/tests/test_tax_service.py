from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

import pytest

from navi_backend.devices.tests.factories import NaviPortFactory
from navi_backend.orders.tests.factories import OrderFactory
from navi_backend.orders.tests.factories import OrderItemFactory
from navi_backend.payments.services import StripePaymentService
from navi_backend.payments.tests.factories import PaymentFactory

SERVICE = "navi_backend.payments.services.stripe"


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
class TestCreatePaymentIntent:
    def test_charges_taxed_total_and_persists_breakdown(self):
        port = NaviPortFactory(postal_code="98101")
        order = OrderFactory(navi_port=port, payment=None)
        OrderItemFactory(order=order, quantity=1, unit_price=Decimal("10.00"))

        fake_calc = SimpleNamespace(
            id="taxcalc_123", tax_amount_exclusive=87, amount_total=1087
        )
        fake_intent = SimpleNamespace(id="pi_abc123", client_secret="secret_abc")

        with (
            mock.patch(SERVICE) as stripe,
            mock.patch.object(
                StripePaymentService,
                "get_or_create_stripe_customer",
                return_value="cus_123",
            ),
        ):
            stripe.tax.Calculation.create.return_value = fake_calc
            stripe.PaymentIntent.create.return_value = fake_intent

            client_secret, payment = StripePaymentService.create_payment_intent(order)

        # Amount authorized must be the taxed total, in cents.
        _, kwargs = stripe.PaymentIntent.create.call_args
        assert kwargs["amount"] == 1087
        assert kwargs["metadata"]["tax_calculation_id"] == "taxcalc_123"

        assert client_secret == "secret_abc"
        payment.refresh_from_db()
        assert payment.subtotal == Decimal("10.00")
        assert payment.tax_amount == Decimal("0.87")
        assert payment.total_amount == Decimal("10.87")
        assert payment.stripe_tax_calculation_id == "taxcalc_123"
        assert payment.status == "requires_capture"


@pytest.mark.django_db
class TestRecordTaxTransaction:
    def test_records_transaction_once(self):
        payment = PaymentFactory(
            stripe_payment_intent_id="pi_abc123",
            stripe_tax_calculation_id="taxcalc_123",
            status="succeeded",
        )

        with mock.patch(SERVICE) as stripe:
            stripe.tax.Transaction.create_from_calculation.return_value = (
                SimpleNamespace(id="taxtxn_123")
            )
            StripePaymentService._record_tax_transaction(payment)

        payment.refresh_from_db()
        assert payment.stripe_tax_transaction_id == "taxtxn_123"

    def test_noop_without_calculation(self):
        payment = PaymentFactory(
            stripe_payment_intent_id="pi_abc123",
            stripe_tax_calculation_id="",
            status="succeeded",
        )

        with mock.patch(SERVICE) as stripe:
            StripePaymentService._record_tax_transaction(payment)
            stripe.tax.Transaction.create_from_calculation.assert_not_called()

    def test_noop_when_already_recorded(self):
        payment = PaymentFactory(
            stripe_payment_intent_id="pi_abc123",
            stripe_tax_calculation_id="taxcalc_123",
            stripe_tax_transaction_id="taxtxn_existing",
            status="succeeded",
        )

        with mock.patch(SERVICE) as stripe:
            StripePaymentService._record_tax_transaction(payment)
            stripe.tax.Transaction.create_from_calculation.assert_not_called()
