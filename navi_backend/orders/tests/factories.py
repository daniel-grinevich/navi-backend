import factory
from factory import Faker

from navi_backend.core.tests.factories import AuditFactory
from navi_backend.core.tests.factories import StatusFactory
from navi_backend.core.tests.factories import UpdateRecordFactory
from navi_backend.devices.tests.factories import NaviPortFactory
from navi_backend.menu.tests.factories import CustomizationFactory
from navi_backend.menu.tests.factories import MenuItemFactory
from navi_backend.orders.models import Order
from navi_backend.orders.models import OrderCustomization
from navi_backend.orders.models import OrderItem
from navi_backend.payments.tests.factories import PaymentFactory
from navi_backend.users.tests.factories import UserFactory


class OrderFactory(
    AuditFactory,
    StatusFactory,
    UpdateRecordFactory,
    factory.django.DjangoModelFactory,
):
    class Meta:
        model = Order

    user = factory.SubFactory(UserFactory)
    slug = factory.Sequence(lambda n: f"123-555-{n:04d}")
    navi_port = factory.SubFactory(NaviPortFactory)
    payment = factory.SubFactory(PaymentFactory)
    order_status = factory.Faker("random_element", elements=["O"])


class OrderItemFactory(
    AuditFactory,
    StatusFactory,
    UpdateRecordFactory,
    factory.django.DjangoModelFactory,
):
    class Meta:
        model = OrderItem

    slug = factory.Sequence(lambda n: f"123-555-{n:04d}")
    order = factory.SubFactory(OrderFactory)
    menu_item = factory.SubFactory(MenuItemFactory)
    quantity = factory.Faker("random_int", min=1, max=9)
    unit_price = Faker(
        "pydecimal",
        left_digits=3,
        right_digits=2,
        positive=True,
        min_value=10.00,
        max_value=100.00,
    )


class OrderCustomizationFactory(
    AuditFactory,
    StatusFactory,
    UpdateRecordFactory,
    factory.django.DjangoModelFactory,
):
    class Meta:
        model = OrderCustomization

    slug = factory.Sequence(lambda n: f"123-555-{n:04d}")
    customization = factory.SubFactory(CustomizationFactory)
    order_item = factory.SubFactory(OrderItemFactory)
    quantity = factory.Faker("random_int", min=1, max=9)
    unit_price = Faker(
        "pydecimal",
        left_digits=3,
        right_digits=2,
        positive=True,
        min_value=10.00,
        max_value=100.00,
    )
