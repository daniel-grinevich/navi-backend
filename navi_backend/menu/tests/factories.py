import factory
from factory import Faker

from navi_backend.core.tests.factories import AuditFactory
from navi_backend.core.tests.factories import SlugifiedFactory
from navi_backend.core.tests.factories import StatusFactory
from navi_backend.core.tests.factories import UpdateRecordFactory
from navi_backend.menu.models import Category
from navi_backend.menu.models import Customization
from navi_backend.menu.models import CustomizationGroup
from navi_backend.menu.models import Ingredient
from navi_backend.menu.models import MenuItem
from navi_backend.menu.models import MenuItemIngredient


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


class IngredientFactory(
    AuditFactory,
    SlugifiedFactory,
    StatusFactory,
    UpdateRecordFactory,
    factory.django.DjangoModelFactory,
):
    class Meta:
        model = Ingredient

    name = factory.Sequence(lambda n: f"Ingredient {n:03d}")
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

    name = factory.Sequence(lambda n: f"Customization Group {n:03d}")
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

    name = factory.Sequence(lambda n: f"Customization {n:03d}")
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
