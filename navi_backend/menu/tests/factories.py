import factory
from django.utils.text import slugify
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

# List of coffee names for MenuItemFactory
coffees = [
    "Espresso",
    "Americano",
    "Latte",
    "Cappuccino",
    "Macchiato",
    "Mocha",
    "Flat White",
    "Cortado",
    "Ristretto",
    "Lungo",
    "Affogato",
    "Cold Brew",
    "Nitro Cold Brew",
    "Pour Over",
    "French Press",
    "Vanilla Latte",
    "Caramel Latte",
    "Hazelnut Latte",
    "Pumpkin Spice Latte",
    "Lavender Latte",
    "Iced Latte",
    "Iced Americano",
    "Iced Mocha",
    "White Chocolate Mocha",
    "Caramel Macchiato",
    "Vanilla Cold Brew",
    "Irish Coffee",
    "Turkish Coffee",
    "Vietnamese Coffee",
    "Chai Latte",
]

# Coffee categories
categories = [
    "Espresso Drinks",
    "Cold Brew & Iced Coffee",
    "Specialty Lattes",
    "Drip Coffee",
    "Tea & Chai",
]

# Coffee ingredients
ingredients = [
    "Espresso Shot",
    "Whole Milk",
    "2% Milk",
    "Oat Milk",
    "Almond Milk",
    "Coconut Milk",
    "Soy Milk",
    "Vanilla Syrup",
    "Caramel Syrup",
    "Hazelnut Syrup",
    "Mocha Sauce",
    "White Chocolate Sauce",
    "Sugar",
    "Honey",
    "Cinnamon",
    "Cocoa Powder",
    "Whipped Cream",
    "Ice",
    "Cold Brew Concentrate",
    "Steamed Milk",
    "Milk Foam",
    "Caramel Drizzle",
    "Chocolate Drizzle",
    "Pumpkin Spice Mix",
    "Lavender Syrup",
    "Chai Concentrate",
    "Hot Water",
    "Cold Water",
    "Heavy Cream",
    "Half & Half",
]

# Customization groups
customization_groups = [
    "Milk Options",
    "Size",
    "Sweeteners",
    "Espresso Shots",
    "Toppings",
    "Flavor Shots",
    "Temperature",
]

# Customizations by group
customizations = {
    "Milk Options": [
        "Whole Milk",
        "2% Milk",
        "Oat Milk",
        "Almond Milk",
        "Coconut Milk",
        "Soy Milk",
        "Heavy Cream",
        "Half & Half",
        "No Milk",
    ],
    "Size": ["Small (12oz)", "Medium (16oz)", "Large (20oz)", "Extra Large (24oz)"],
    "Sweeteners": [
        "Sugar (1 packet)",
        "Sugar (2 packets)",
        "Honey",
        "Stevia",
        "Agave",
        "No Sweetener",
    ],
    "Espresso Shots": [
        "Single Shot",
        "Double Shot",
        "Triple Shot",
        "Quad Shot",
        "Decaf Shot",
        "Half-Caf",
    ],
    "Toppings": [
        "Whipped Cream",
        "Caramel Drizzle",
        "Chocolate Drizzle",
        "Cinnamon Powder",
        "Cocoa Powder",
        "Vanilla Powder",
    ],
    "Flavor Shots": [
        "Vanilla",
        "Caramel",
        "Hazelnut",
        "Mocha",
        "White Chocolate",
        "Pumpkin Spice",
        "Lavender",
        "Peppermint",
    ],
    "Temperature": ["Extra Hot", "Hot", "Warm", "Iced", "Blended"],
}

# Units for ingredients
units = ["oz", "ml", "pump", "shot", "packet", "tsp", "tbsp", "dash"]

# Flatten customizations for easier use in factory
all_customizations = [item for sublist in customizations.values() for item in sublist]


class CategoryFactory(
    AuditFactory,
    SlugifiedFactory,
    StatusFactory,
    UpdateRecordFactory,
    factory.django.DjangoModelFactory,
):
    class Meta:
        model = Category

    name = factory.Iterator(categories)


class MenuItemFactory(
    AuditFactory,
    SlugifiedFactory,
    StatusFactory,
    UpdateRecordFactory,
    factory.django.DjangoModelFactory,
):
    class Meta:
        model = MenuItem

    name = factory.Iterator(coffees)
    slug = factory.LazyAttribute(lambda obj: slugify(obj.name))
    category = factory.SubFactory(CategoryFactory)
    description = Faker("text", max_nb_chars=100)
    body = Faker("text", max_nb_chars=100)
    price = Faker(
        "pydecimal",
        left_digits=1,
        right_digits=2,
        positive=True,
        min_value=2.50,
        max_value=8.99,
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

    name = factory.Iterator(ingredients)
    description = factory.Faker("sentence")


class MenuItemIngredientFactory(
    factory.django.DjangoModelFactory,
):
    class Meta:
        model = MenuItemIngredient

    menu_item = factory.SubFactory(MenuItemFactory)
    ingredient = factory.SubFactory(IngredientFactory)
    quantity = factory.Faker(
        "pyfloat",
        left_digits=1,
        right_digits=2,
        positive=True,
        min_value=0.5,
        max_value=8.0,
    )
    unit = factory.Iterator(units)


class CustomizationGroupFactory(
    AuditFactory,
    SlugifiedFactory,
    StatusFactory,
    UpdateRecordFactory,
    factory.django.DjangoModelFactory,
):
    class Meta:
        model = CustomizationGroup

    name = factory.Sequence(
        lambda n: customization_groups[n % len(customization_groups)]
        + (
            f" #{(n // len(customization_groups)) + 1}"
            if n >= len(customization_groups)
            else ""
        )
    )
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

    name = factory.Sequence(
        lambda n: all_customizations[n % len(all_customizations)]
        + (
            f" #{(n // len(all_customizations)) + 1}"
            if n >= len(all_customizations)
            else ""
        )
    )
    description = factory.Faker("sentence")
    display_order = factory.Faker("random_int", min=1, max=10)
    price = Faker(
        "pydecimal",
        left_digits=1,
        right_digits=2,
        positive=True,
        min_value=0.25,
        max_value=2.50,
    )
    group = factory.SubFactory(CustomizationGroupFactory)
