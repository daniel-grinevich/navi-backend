"""Checkout with rewards: capped discounts, $0 orders, refunds on cancellation."""

from decimal import Decimal
from unittest import mock

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from navi_backend.awards.models import RedemptionStatus
from navi_backend.awards.models import RewardRedemption
from navi_backend.awards.models import UserLoyalty
from navi_backend.awards.tests.factories import RewardFactory
from navi_backend.awards.tests.factories import UserLoyaltyFactory
from navi_backend.devices.tests.factories import NaviPortFactory
from navi_backend.devices.tests.factories import RaspberryPiFactory
from navi_backend.menu.tests.factories import MenuItemFactory
from navi_backend.orders.models import Order
from navi_backend.payments.services import StripePaymentService

from .factories import OrderFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def member(user):
    UserLoyaltyFactory(user=user, balance_points=500, lifetime_points=500)
    return user


@pytest.fixture
def member_client(member):
    client = APIClient()
    client.force_authenticate(user=member)
    return client


@pytest.fixture
def stripe_mock():
    with mock.patch("navi_backend.payments.services.stripe") as stripe:
        stripe.Customer.create.return_value = mock.Mock(id="cus_test")
        stripe.PaymentIntent.create.return_value = mock.Mock(
            id="pi_test_rewards",
            client_secret="secret_123",  # noqa: S106
        )
        yield stripe


def _place_order(client, menu_item, reward=None):
    item = {"menu_item": str(menu_item.id), "quantity": 1}
    if reward is not None:
        item["reward"] = str(reward.id)
    return client.post("/api/orders/", {"items": [item]}, format="json")


def _balance(user):
    return UserLoyalty.objects.get(user=user).balance_points


class TestCheckoutWithRewards:
    def test_reward_capped_at_max_value_charges_the_difference(
        self, member, member_client, stripe_mock
    ):
        latte = MenuItemFactory(price=Decimal("7.50"))
        reward = RewardFactory(
            menu_item=latte, points_cost=200, max_value=Decimal("6.00")
        )

        resp = _place_order(member_client, latte, reward)

        assert resp.status_code == 201, resp.data
        assert stripe_mock.PaymentIntent.create.call_args.kwargs["amount"] == 150
        assert resp.data["client_secret"] == "secret_123"  # noqa: S105
        order = resp.data["order"]
        assert Decimal(str(order["price"])) == Decimal("1.50")
        assert Decimal(str(order["subtotal"])) == Decimal("7.50")
        assert Decimal(str(order["discount_total"])) == Decimal("6.00")
        assert str(order["redemptions"][0]["reward"]) == str(reward.id)
        assert _balance(member) == 300

    def test_fully_covered_order_skips_stripe(self, member, member_client, stripe_mock):
        espresso = MenuItemFactory(price=Decimal("4.00"))
        reward = RewardFactory(menu_item=espresso, max_value=Decimal("6.00"))

        resp = _place_order(member_client, espresso, reward)

        assert resp.status_code == 201, resp.data
        stripe_mock.PaymentIntent.create.assert_not_called()
        assert resp.data["client_secret"] is None
        order = Order.objects.get(pk=resp.data["order"]["id"])
        assert order.payment is None
        assert order.price == Decimal("0.00")
        order.is_dispatchable()  # no payment needed for a $0 order

    def test_leftover_below_stripe_minimum_is_waived(
        self, member, member_client, stripe_mock
    ):
        drink = MenuItemFactory(price=Decimal("6.30"))
        reward = RewardFactory(
            menu_item=drink, points_cost=200, max_value=Decimal("6.00")
        )

        resp = _place_order(member_client, drink, reward)

        assert resp.status_code == 201, resp.data
        stripe_mock.PaymentIntent.create.assert_not_called()
        assert resp.data["client_secret"] is None
        order = Order.objects.get(pk=resp.data["order"]["id"])
        assert order.payment is None
        assert order.price == Decimal("0.00")
        assert RewardRedemption.objects.get().discount_amount == Decimal("6.30")
        assert _balance(member) == 300

    def test_order_below_stripe_minimum_without_rewards_is_rejected(
        self, member, member_client, stripe_mock
    ):
        cheap = MenuItemFactory(price=Decimal("0.30"))

        resp = _place_order(member_client, cheap)

        assert resp.status_code == 400
        assert "price" in resp.data["error"]["message"]
        assert not Order.objects.exists()
        stripe_mock.PaymentIntent.create.assert_not_called()

    def test_not_enough_points_rejects_the_whole_order(self, user, stripe_mock):
        UserLoyaltyFactory(user=user, balance_points=50)
        client = APIClient()
        client.force_authenticate(user=user)
        latte = MenuItemFactory(price=Decimal("5.00"))
        reward = RewardFactory(menu_item=latte, points_cost=200)

        resp = _place_order(client, latte, reward)

        assert resp.status_code == 400
        assert "rewards" in resp.data["error"]["message"]
        assert not Order.objects.exists()
        stripe_mock.PaymentIntent.create.assert_not_called()
        assert _balance(user) == 50

    def test_order_without_rewards_is_unchanged(
        self, member, member_client, stripe_mock
    ):
        latte = MenuItemFactory(price=Decimal("5.00"))

        resp = _place_order(member_client, latte)

        assert resp.status_code == 201, resp.data
        assert stripe_mock.PaymentIntent.create.call_args.kwargs["amount"] == 500
        assert resp.data["order"]["redemptions"] == []


class TestRefundsOnCancellation:
    def _order_with_reward(self, client):
        latte = MenuItemFactory(price=Decimal("7.50"))
        reward = RewardFactory(menu_item=latte, points_cost=200)
        resp = _place_order(client, latte, reward)
        assert resp.status_code == 201, resp.data
        return Order.objects.get(pk=resp.data["order"]["id"])

    def test_customer_cancel_refunds_points(self, member, member_client, stripe_mock):
        order = self._order_with_reward(member_client)
        assert _balance(member) == 300

        with mock.patch("navi_backend.orders.api.views.cancel_stripe_payment") as task:
            resp = member_client.put(f"/api/orders/{order.id}/cancel_order/")

        assert resp.status_code == 200
        task.apply_async.assert_called_once()
        assert _balance(member) == 500
        assert RewardRedemption.objects.get().status == RedemptionStatus.REVERSED

    def test_canceled_payment_webhook_refunds_points(
        self, member, member_client, stripe_mock
    ):
        order = self._order_with_reward(member_client)

        with mock.patch("navi_backend.payments.services.notify_machines_queue_changed"):
            StripePaymentService.handle_webhook_event(
                {
                    "type": "payment_intent.canceled",
                    "data": {"object": {"id": order.payment.stripe_payment_intent_id}},
                }
            )

        order.refresh_from_db()
        assert order.order_status == "C"
        assert _balance(member) == 500


class TestMachineCompleteForFreeOrders:
    def test_free_order_completes_without_a_capture(self, member):
        pi = RaspberryPiFactory(is_connected=True)
        navi_port = NaviPortFactory(raspberry_pi=pi)
        order = OrderFactory(
            user=member, order_status="S", payment=None, navi_port=navi_port
        )
        Order.objects.filter(pk=order.pk).update(claimed_by=pi)
        client = APIClient()
        client.credentials(HTTP_X_DEVICE_TOKEN=pi.device_token)

        with mock.patch.multiple(
            "navi_backend.orders.api.machine_views",
            capture_stripe_payment=mock.DEFAULT,
            create_order_invoice=mock.DEFAULT,
            process_order_awards=mock.DEFAULT,
            broadcast_order_status=mock.DEFAULT,
            notify_machines_queue_changed=mock.DEFAULT,
        ) as mocks:
            resp = client.post(
                reverse("api:machine-order-complete", args=[order.id]),
                {"outcome": "complete"},
                format="json",
            )

        assert resp.status_code == 200, resp.data
        mocks["capture_stripe_payment"].apply_async.assert_not_called()
        mocks["process_order_awards"].apply_async.assert_called_once()
