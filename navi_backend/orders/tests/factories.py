import factory
from factory import Faker
from ..models import Order, OrderItem, Category, PaymentType, Port, MenuItem
from ...users.tests.factories import UserFactory
import random
from django.utils import timezone
from django.utils.text import slugify


class AuditFactory(factory.Factory):
    """Base factory for AuditModel."""

    is_deleted = False
    deleted_at = None
    last_modified_ip = factory.Faker("ipv4")
    last_modified_user_agent = factory.Faker("user_agent")

    class Meta:
        abstract = True


class SlugifiedFactory(factory.Factory):
    """Base factory for SlugifiedModel."""

    name = factory.Faker("sentence", nb_words=3)
    slug = factory.LazyAttribute(lambda obj: slugify(obj.name))

    class Meta:
        abstract = True


class StatusFactory(factory.Factory):
    """Base factory for StatusModel."""

    status = factory.Faker("random_element", elements=["A", "I", "D", "R"])

    class Meta:
        abstract = True


class UpdateRecordFactory(factory.Factory):
    """Base factory for UpdateRecordModel."""

    created_at = factory.LazyFunction(timezone.now)
    updated_at = factory.LazyFunction(timezone.now)
    created_by = factory.SubFactory(UserFactory)
    updated_by = factory.SubFactory(UserFactory)

    class Meta:
        abstract = True


class CategoryFactory(
    AuditFactory,
    SlugifiedFactory,
    StatusFactory,
    UpdateRecordFactory,
    factory.django.DjangoModelFactory,
):
    class Meta:
        model = Category


class MenuItemFactory(
    AuditFactory,
    SlugifiedFactory,
    StatusFactory,
    UpdateRecordFactory,
    factory.django.DjangoModelFactory,
):
    class Meta:
        model = MenuItem

    category = factory.SubFactory(CategoryFactory)
    description = Faker("text", max_nb_chars=100)
    body = Faker("text", max_nb_chars=100)
    price = Faker(
        "pydecimal",
        left_digits=3,
        right_digits=2,
        positive=True,
        min_value=10.00,
        max_value=100.00,
    )
    image = factory.django.ImageField(color="blue")


class PortFactory(
    AuditFactory,
    SlugifiedFactory,
    StatusFactory,
    UpdateRecordFactory,
    factory.django.DjangoModelFactory,
):
    class Meta:
        model = Port


class PaymentTypeFactory(
    AuditFactory,
    SlugifiedFactory,
    StatusFactory,
    UpdateRecordFactory,
    factory.django.DjangoModelFactory,
):
    class Meta:
        model = PaymentType


class OrderFactory(
    AuditFactory,
    SlugifiedFactory,
    StatusFactory,
    UpdateRecordFactory,
    factory.django.DjangoModelFactory,
):
    class Meta:
        model = Order

    user = factory.SubFactory(UserFactory)
    payment_type = factory.SubFactory(PaymentTypeFactory)
    port = factory.SubFactory(PortFactory)
    totalPrice = factory.LazyFunction(lambda: round(random.uniform(10.00, 100.00), 2))


class OrderItemFactory(
    AuditFactory,
    SlugifiedFactory,
    StatusFactory,
    UpdateRecordFactory,
    factory.django.DjangoModelFactory,
):
    class Meta:
        model = OrderItem

    order = factory.SubFactory(OrderFactory)
    menu_item = factory.SubFactory(MenuItemFactory)
    qty = factory.LazyFunction(lambda: random.randint(1, 9))
    price = factory.LazyFunction(lambda: round(random.uniform(10.00, 100.00), 2))
