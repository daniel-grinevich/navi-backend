import json
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from .factories import CategoryFactory
from .factories import CustomizationFactory
from .factories import CustomizationGroupFactory
from .factories import IngredientFactory
from .factories import MenuItemFactory
from .factories import MenuItemIngredientFactory


@pytest.fixture
def menu_item(db):
    return MenuItemFactory(name="Latte")


@pytest.fixture
def ingredient_data():
    return json.dumps(
        {
            "name": "Tomato Sauce",
            "description": "Test",
            "is_allergen": "False",
            "status": "A",
        }
    )


@pytest.fixture
def menu_item_data():
    category = CategoryFactory()
    image_path = Path("navi_backend/media/product_images/Latte.png")

    # Check if image exists, otherwise create a dummy one
    if not image_path.exists():
        image_file = SimpleUploadedFile(
            "Latte.png",
            content=b"dummy image content",
            content_type="image/png",
        )
    else:
        with image_path.open("rb") as f:
            image_file = SimpleUploadedFile(
                "Latte.png",
                content=f.read(),
                content_type="image/png",
            )

    return {
        "name": "Over-Priced Latte",
        "description": "Over-Priced Latte",
        "body": "Over-Priced Latte",
        "price": "12.99",
        "category": category.pk,
        "image": image_file,
        "status": "A",
    }


@pytest.fixture
def ingredient():
    return IngredientFactory(name="Espresso")


@pytest.fixture
def menu_item_ingredient():
    menu_item = MenuItemFactory(name="Latte")
    ingredient = IngredientFactory(name="Milk")
    return MenuItemIngredientFactory(
        menu_item=menu_item, ingredient=ingredient, quantity="200", unit="g"
    )


@pytest.fixture
def menu_item_ingredient_data():
    menu_item = MenuItemFactory(name="Capp")
    ingredient = IngredientFactory(name="espresso")
    return json.dumps(
        {
            "menu_item": menu_item.pk,
            "ingredient": ingredient.pk,
            "quantity": "200",
            "unit": "g",
        }
    )


@pytest.fixture
def customization(db):
    return CustomizationFactory()


@pytest.fixture
def customization_data():
    group = CustomizationGroupFactory()
    return json.dumps(
        {
            "name": "Customization_1",
            "description": "Test",
            "price": 10.00,
            "display_order": 1,
            "group": group.pk,
        }
    )


@pytest.fixture
def customization_group(db):
    return CustomizationGroupFactory()


@pytest.fixture
def customization_group_data():
    category = CategoryFactory()
    return json.dumps(
        {
            "name": "Customization_Group_1",
            "description": "Test",
            "category": category.pk,
            "display_order": 1,
            "is_required": True,
        }
    )


@pytest.fixture
def category(db):
    return CategoryFactory()


@pytest.fixture
def category_data():
    return json.dumps(
        {
            "name": "Category_1",
        }
    )
