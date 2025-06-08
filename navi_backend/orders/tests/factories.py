import factory
from factory import Faker
import random
from django.utils import timezone
from django.utils.text import slugify

from ..models import (
    Order,
    OrderItem,
    Category,
    NaviPort,
    MenuItem,
    MenuItemIngredient,
    Ingredient,
    EspressoMachine,
    RasberryPi,
    MachineType,
    Customization,
    CustomizationGroup,
    OrderCustomization,
)
from navi_backend.users.tests.factories import UserFactory
from navi_backend.payments.tests.factories import PaymentFactory
from navi_backend.core.tests.factories import (
    AuditFactory,
    SlugifiedFactory,
    StatusFactory,
    UpdateRecordFactory,
)


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
    image = factory.django.ImageField(color="blue", filename="test_menuitem.jpg")


class RasberryPiFactory(
    AuditFactory,
    SlugifiedFactory,
    StatusFactory,
    UpdateRecordFactory,
    factory.django.DjangoModelFactory,
):
    class Meta:
        model = RasberryPi

    name = factory.Sequence(lambda n: "Pi %03d" % n)
    mac_address = factory.Faker("mac_address")
    ip_address = factory.Faker("ipv4")
    location = factory.Faker("address")
    is_connected = factory.Faker("boolean")
    firmware_version = factory.Faker("bothify", text="v#.##")
    last_seen = factory.LazyFunction(timezone.now)


class MachineTypeFactory(
    AuditFactory,
    SlugifiedFactory,
    StatusFactory,
    UpdateRecordFactory,
    factory.django.DjangoModelFactory,
):
    class Meta:
        model = MachineType

    name = factory.Sequence(lambda n: "Type %03d" % n)
    model_number = factory.Faker("bothify", text="MT###")
    maintenance_frequency = factory.Faker("random_int", min=30, max=365)

    @factory.post_generation
    def supported_drinks(self, create, extracted, **kwargs):
        if not create or not extracted:
            # Simple build, or nothing to add, do nothing.
            return

        # Add the iterable of groups using bulk addition
        self.supported_drinks.add(*extracted)


class EspressoMachineFactory(
    AuditFactory,
    SlugifiedFactory,
    StatusFactory,
    UpdateRecordFactory,
    factory.django.DjangoModelFactory,
):
    class Meta:
        model = EspressoMachine

    name = factory.Sequence(lambda n: "Machine %03d" % n)
    serial_number = factory.Faker("bothify", text="EM###-####")
    machine_type = factory.SubFactory(MachineTypeFactory)
    ip_address = factory.Faker("ipv4")
    port = factory.Faker("random_int", min=8000, max=9000)
    is_online = factory.Faker("boolean")
    last_maintenance_at = factory.LazyFunction(timezone.now)


class NaviPortFactory(
    AuditFactory,
    SlugifiedFactory,
    StatusFactory,
    UpdateRecordFactory,
    factory.django.DjangoModelFactory,
):
    espresso_machine = factory.SubFactory(EspressoMachineFactory)
    rasberry_pi = factory.SubFactory(RasberryPiFactory)

    class Meta:
        model = NaviPort


class OrderFactory(
    AuditFactory,
    StatusFactory,
    UpdateRecordFactory,
    factory.django.DjangoModelFactory,
):
    class Meta:
        model = Order

    user = factory.SubFactory(UserFactory)
    slug = factory.Sequence(lambda n: "123-555-%04d" % n)
    navi_port = factory.SubFactory(NaviPortFactory)
    payment = factory.SubFactory(PaymentFactory)
    status = factory.Faker("random_element", elements=["O"])


class OrderItemFactory(
    AuditFactory,
    StatusFactory,
    UpdateRecordFactory,
    factory.django.DjangoModelFactory,
):
    class Meta:
        model = OrderItem

    slug = factory.Sequence(lambda n: "123-555-%04d" % n)
    order = factory.SubFactory(OrderFactory)
    menu_item = factory.SubFactory(MenuItemFactory)
    quantity = factory.LazyFunction(lambda: random.randint(1, 9))
    unit_price = Faker(
        "pydecimal",
        left_digits=3,
        right_digits=2,
        positive=True,
        min_value=10.00,
        max_value=100.00,
    )


class IngredientFactory(
    AuditFactory,
    SlugifiedFactory,
    StatusFactory,
    UpdateRecordFactory,
    factory.django.DjangoModelFactory,
):
    class Meta:
        model = Ingredient

    name = factory.Sequence(lambda n: "Ingredient %03d" % n)
    description = factory.Faker("sentence")


class MenuItemIngredientFactory(
    factory.django.DjangoModelFactory,
):
    class Meta:
        model = MenuItemIngredient

    menu_item = factory.SubFactory(MenuItemFactory)
    ingredient = factory.SubFactory(IngredientFactory)
    quantity = factory.Faker("pyfloat", left_digits=1, right_digits=2, positive=True)
    unit = Faker("text", max_nb_chars=10)


class CustomizationGroupFactory(
    AuditFactory,
    SlugifiedFactory,
    StatusFactory,
    UpdateRecordFactory,
    factory.django.DjangoModelFactory,
):
    class Meta:
        model = CustomizationGroup

    name = factory.Sequence(lambda n: "Customization Group %03d" % n)
    description = factory.Faker("sentence")
    display_order = factory.Faker("random_int", min=1, max=10)
    is_required = factory.Faker("boolean")

    @factory.post_generation
    def category(self, create, extracted, **kwargs):
        if not create or not extracted:
            # Simple build, or nothing to add, do nothing.
            return

        # Add the iterable of groups using bulk addition
        self.category.add(*extracted)


class CustomizationFactory(
    AuditFactory,
    SlugifiedFactory,
    StatusFactory,
    UpdateRecordFactory,
    factory.django.DjangoModelFactory,
):
    class Meta:
        model = Customization

    name = factory.Sequence(lambda n: "Customization %03d" % n)
    description = factory.Faker("sentence")
    display_order = factory.Faker("random_int", min=1, max=10)
    price = Faker(
        "pydecimal",
        left_digits=3,
        right_digits=2,
        positive=True,
        min_value=10.00,
        max_value=100.00,
    )
    group = factory.SubFactory(CustomizationGroupFactory)


class OrderCustomizationFactory(
    AuditFactory,
    StatusFactory,
    UpdateRecordFactory,
    factory.django.DjangoModelFactory,
):
    class Meta:
        model = OrderCustomization

    slug = factory.Sequence(lambda n: "123-555-%04d" % n)
    customization = factory.SubFactory(CustomizationFactory)
    order_item = factory.SubFactory(OrderItemFactory)
    quantity = factory.LazyFunction(lambda: random.randint(1, 9))
    unit_price = Faker(
        "pydecimal",
        left_digits=3,
        right_digits=2,
        positive=True,
        min_value=10.00,
        max_value=100.00,
    )
