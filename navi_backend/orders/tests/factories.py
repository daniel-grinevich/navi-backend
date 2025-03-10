import factory
from factory import Faker
from ..models import Order, OrderItem, Category, PaymentType, Port, MenuItem
from ...users.tests.factories import UserFactory
import random
from django.utils import timezone


class CategoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Category

    name = Faker("name")
    slug = factory.Sequence(lambda n: n)


class MenuItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = MenuItem

    name = Faker("name")
    category = factory.SubFactory(CategoryFactory)
    description = Faker("paragraph")
    price = factory.LazyFunction(lambda: round(random.uniform(10.00, 100.00), 2))
    image = factory.django.ImageField(color="blue")
    created_at = timezone.now()
    slug = factory.Sequence(lambda n: n)


class PortFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Port

    name = Faker("name")
    slug = factory.Sequence(lambda n: n)


class PaymentTypeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PaymentType

    name = Faker("name")
    slug = factory.Sequence(lambda n: n)


class OrderFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Order

    user = factory.SubFactory(UserFactory)
    payment_type = factory.SubFactory(PaymentTypeFactory)
    port = factory.SubFactory(PortFactory)
    totalPrice = factory.LazyFunction(lambda: round(random.uniform(10.00, 100.00), 2))
    created_at = timezone.now()
    slug = factory.Sequence(lambda n: n)


class OrderItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = OrderItem

    name = Faker("name")
    order = factory.SubFactory(OrderFactory)
    menu_item = factory.SubFactory(MenuItemFactory)
    qty = factory.LazyFunction(lambda: random.randint(1, 9))
    price = factory.LazyFunction(lambda: round(random.uniform(10.00, 100.00), 2))
