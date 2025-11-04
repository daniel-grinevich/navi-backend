from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from navi_backend.menu.models import Customization
from navi_backend.menu.models import CustomizationGroup
from navi_backend.menu.models import MenuItem

from .factories import CategoryFactory
from .factories import CustomizationFactory
from .factories import CustomizationGroupFactory
from .factories import IngredientFactory
from .factories import MenuItemFactory
from .factories import MenuItemIngredientFactory


@pytest.mark.django_db
class TestCategory:
    def test_create_category(self, category):
        assert category
        assert category.name
        assert category.slug

    def test_category_string_representation(self):
        category = CategoryFactory(name="Beverages")
        assert str(category) == "Beverages"


@pytest.mark.django_db
class TestMenuItem:
    def test_create_menu_item(self, menu_item):
        assert menu_item
        assert menu_item.name == "Latte"
        assert menu_item.price > 0
        assert menu_item.category
        assert menu_item.version == 1

    def test_menu_item_string_representation(self):
        menu_item = MenuItemFactory(name="Espresso")
        assert str(menu_item) == f"Espresso (v{menu_item.version})"

    def test_menu_item_version_increment_on_save(self):
        menu_item = MenuItemFactory()
        initial_version = menu_item.version
        menu_item.name = "Updated Name"
        menu_item.save()
        assert menu_item.version == initial_version + 1

    def test_menu_item_clean_negative_price(self):
        menu_item = MenuItemFactory.build(price=Decimal("-5.00"))
        with pytest.raises(ValidationError) as exc_info:
            menu_item.clean()
        assert "Price cannot be negative" in str(exc_info.value)

    def test_menu_item_clean_deleted_active_status(self):
        menu_item = MenuItemFactory()
        menu_item.is_deleted = True
        menu_item.status = menu_item.Status.ACTIVE
        with pytest.raises(ValidationError) as exc_info:
            menu_item.clean()
        assert "Deleted menuitem cannot be active" in str(exc_info.value)

    def test_increment_view_count(self):
        menu_item = MenuItemFactory()
        initial_count = menu_item.view_count
        menu_item.increment_view_count()
        menu_item.refresh_from_db()
        assert menu_item.view_count == initial_count + 1

    def test_increment_selected_count(self):
        menu_item = MenuItemFactory()
        initial_count = menu_item.selected_count
        menu_item.increment_selected_count()
        menu_item.refresh_from_db()
        assert menu_item.selected_count == initial_count + 1

    def test_get_related_items(self):
        category = CategoryFactory()
        menu_item = MenuItemFactory(category=category, status=MenuItem.Status.ACTIVE)
        related_item1 = MenuItemFactory(
            category=category, status=MenuItem.Status.ACTIVE
        )
        related_item2 = MenuItemFactory(
            category=category, status=MenuItem.Status.ACTIVE
        )
        MenuItemFactory(category=category, status=MenuItem.Status.INACTIVE)

        related_items = menu_item.get_related_items()
        assert len(related_items) == 2
        assert related_item1 in related_items
        assert related_item2 in related_items
        assert menu_item not in related_items

    def test_get_related_items_no_category(self):
        menu_item = MenuItemFactory(category=None)
        related_items = menu_item.get_related_items()
        assert len(related_items) == 0

    def test_toggle_featured(self):
        menu_item = MenuItemFactory(is_featured=False)
        menu_item.toggle_featured()
        assert menu_item.is_featured is True

        menu_item.toggle_featured()
        assert menu_item.is_featured is False


@pytest.mark.django_db
class TestIngredient:
    def test_create_ingredient(self, ingredient):
        assert ingredient
        assert ingredient.name == "Espresso"

    def test_ingredient_string_representation(self):
        ingredient = IngredientFactory(name="Milk")
        assert str(ingredient) == "Milk"

    def test_ingredient_allergen_flag(self):
        ingredient = IngredientFactory(is_allergen=True)
        assert ingredient.is_allergen is True


@pytest.mark.django_db
class TestMenuItemIngredient:
    def test_create_menu_item_ingredient(self, menu_item_ingredient):
        assert menu_item_ingredient
        assert menu_item_ingredient.menu_item.name == "Latte"
        assert menu_item_ingredient.ingredient.name == "Milk"
        assert menu_item_ingredient.quantity == "200"
        assert menu_item_ingredient.unit == "g"

    def test_menu_item_ingredient_string_representation(self):
        ingredient_relation = MenuItemIngredientFactory(
            quantity=Decimal("150"), unit="ml"
        )
        expected = (
            f"{ingredient_relation.quantity} {ingredient_relation.unit} "
            f"{ingredient_relation.ingredient.name} in {ingredient_relation.menu_item.name}"  # noqa: E501
        )
        assert str(ingredient_relation) == expected

    def test_unique_together_constraint(self):
        menu_item = MenuItemFactory()
        ingredient = IngredientFactory()
        MenuItemIngredientFactory(menu_item=menu_item, ingredient=ingredient)

        with pytest.raises(IntegrityError):
            MenuItemIngredientFactory(menu_item=menu_item, ingredient=ingredient)


@pytest.mark.django_db
class TestCustomizationGroup:
    def test_create_customization_group(self, customization_group):
        assert customization_group
        assert customization_group.name

    def test_customization_group_string_representation(self):
        group = CustomizationGroupFactory(name="Size Options")
        assert str(group) == "Size Options"

    def test_customization_group_ordering(self):
        group1 = CustomizationGroupFactory(display_order=2, name="B Group")
        group2 = CustomizationGroupFactory(display_order=1, name="A Group")

        groups = list(CustomizationGroup.objects.all())
        assert groups[0] == group2  # Lower display_order comes first
        assert groups[1] == group1


@pytest.mark.django_db
class TestCustomization:
    def test_create_customization(self, customization):
        assert customization
        assert customization.name
        assert customization.group
        assert customization.price > 0

    def test_customization_string_representation(self):
        customization = CustomizationFactory(name="Extra Shot")
        assert str(customization) == "Extra Shot"

    def test_customization_ordering(self):
        group = CustomizationGroupFactory()
        custom1 = CustomizationFactory(group=group, display_order=2, name="B Custom")
        custom2 = CustomizationFactory(group=group, display_order=1, name="A Custom")

        customizations = list(Customization.objects.all())
        assert customizations[0] == custom2  # Lower display_order comes first
        assert customizations[1] == custom1
