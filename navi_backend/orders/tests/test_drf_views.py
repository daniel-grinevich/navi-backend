import pytest
import json
from rest_framework.test import APIRequestFactory
from rest_framework import status
from navi_backend.orders.models import (
    Order,
    OrderItem,
    Category,
    PaymentType,
    NaviPort,
    MenuItem,
    Ingredient,
    MenuItemIngredient,
)
from .factories import (
    OrderFactory,
    MenuItemFactory,
    IngredientFactory,
    MenuItemIngredientFactory,
)
from navi_backend.orders.tests.factories import (
    UserFactory,
)
from navi_backend.users.models import User
from navi_backend.orders.api.views import (
    MenuItemViewSet,
    OrderItemViewSet,
    OrderViewSet,
    IngredientViewSet,
    MenuItemIngredientViewSet,
)

# Potentially switch request setup to generic function


@pytest.mark.django_db
class TestOrderViewSet:

    @pytest.mark.parametrize(
        "view_name, method, url",
        [
            ("list", "GET", "/api/orders/"),
            ("retrieve", "GET", "/api/orders/{pk}/"),
        ],
    )
    def test_not_admin_access(
        self, user_and_orders, get_response, view_name, method, url
    ):
        """Non-admin users should only see their own orders."""
        user, own_order, other_order = user_and_orders
        view = OrderViewSet.as_view({method.lower(): view_name})

        # List View
        if view_name == "list":
            response = get_response(user, view, method, url)
            order_ids = [order["slug"] for order in response.data]
            assert str(own_order.slug) in order_ids
            assert str(other_order.slug) not in order_ids

        # Retrieve View
        if view_name == "retrieve":
            response = get_response(
                user, view, method, url.format(pk=own_order.pk), pk=own_order.pk
            )
            assert response.status_code == status.HTTP_200_OK

            response = get_response(
                user, view, method, url.format(pk=other_order.pk), pk=other_order.pk
            )
            assert response.status_code in [
                status.HTTP_403_FORBIDDEN,
                status.HTTP_404_NOT_FOUND,
            ]

    @pytest.mark.parametrize(
        "view_name, method, url",
        [
            ("list", "GET", "/api/orders/"),
            ("retrieve", "GET", "/api/orders/{pk}/"),
        ],
    )
    def test_admin_access(self, admin_and_orders, get_response, view_name, method, url):
        """Admin users should have access to all orders."""
        admin, orders = admin_and_orders
        view = OrderViewSet.as_view({method.lower(): view_name})

        # List View
        if view_name == "list":
            response = get_response(admin, view, method, url)
            order_ids = [order["slug"] for order in response.data]
            assert len(order_ids) == len(orders)
            assert all(str(order.slug) in order_ids for order in orders)

        # Retrieve View
        if view_name == "retrieve":
            for order in orders:
                response = get_response(
                    admin, view, method, url.format(pk=order.pk), pk=order.pk
                )
                assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestIngredientViewSet:
    @pytest.mark.parametrize(
        "view_name, method, url",
        [
            ("create", "POST", "/api/ingredients/"),
            ("destroy", "DELETE", "/api/ingredients/{pk}/"),
            ("partial_update", "PATCH", "/api/ingredients/{pk}/"),
        ],
    )
    def test_admin_access(
        self,
        get_response,
        admin_user,
        ingredient_data,
        view_name,
        method,
        url,
        ingredient,
    ):
        view = IngredientViewSet.as_view({method.lower(): view_name})
        if view_name == "create":
            response = get_response(admin_user, view, method, url, data=ingredient_data)
            assert response.status_code == status.HTTP_201_CREATED
            assert Ingredient.objects.filter(name="Tomato Sauce").exists()

        if view_name == "delete":
            response = get_response(
                admin_user,
                view,
                method,
                url.format(pk=ingredient.pk),
                pk=ingredient.pk,
            )
            assert response.status_code == status.HTTP_204_NO_CONTENT
            assert not Ingredient.objects.filter(id=ingredient.id).exists()

        if view_name == "partial_update":
            payload = json.dumps({"name": "Latte"})
            response = get_response(
                admin_user,
                view,
                method,
                url.format(pk=ingredient.pk),
                data=payload,
                pk=ingredient.pk,
            )
            ingredient.refresh_from_db()
            assert response.status_code == status.HTTP_200_OK
            assert ingredient.name == "Latte"

    @pytest.mark.parametrize(
        "view_name, method, url",
        [
            ("list", "GET", "/ingredients/"),
            ("retrieve", "GET", "/ingredients/{pk}/"),
        ],
    )
    def test_get_ingredient(self, admin_user, get_response, view_name, method, url):
        ingredients = IngredientFactory.create_batch(3)
        view = IngredientViewSet.as_view({method.lower(): view_name})

        if view_name == "list":
            response = get_response(admin_user, view, method, url)
            assert response.status_code == status.HTTP_200_OK
            assert len(response.data) == 3

        if view_name == "retrieve":
            for ingredient in ingredients:
                response = get_response(
                    admin_user,
                    view,
                    method,
                    url.format(pk=ingredient.pk),
                    pk=ingredient.pk,
                )
                assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestMenuItemViewSets:

    @pytest.mark.parametrize(
        "view_name, method, url",
        [
            ("create", "POST", "/api/menuitems/"),
            ("destroy", "DELETE", "/api/menuitems/{pk}/"),
            ("partial_update", "PATCH", "/api/menuitems/{pk}/"),
        ],
    )
    def test_create_menu_item(
        self,
        get_response,
        admin_user,
        method,
        view_name,
        url,
        menu_item_data,
        menu_item,
        api_rf,
    ):
        view = MenuItemViewSet.as_view({method.lower(): view_name})
        if view_name == "create":
            response = api_rf.post(
                url,
                data=menu_item_data,
            )
            response.user = admin_user
            response = view(response)
            print(response.data)
            assert response.status_code == status.HTTP_201_CREATED
            assert MenuItem.objects.filter(name="Latte").exists()

        if view_name == "delete":
            response = get_response(
                admin_user,
                view,
                method,
                url.format(pk=menu_item.pk),
                pk=menu_item.pk,
            )
            assert response.status_code == status.HTTP_204_NO_CONTENT
            assert not MenuItem.objects.filter(id=menu_item.id).exists()

        if view_name == "partial_update":
            payload = json.dumps({"name": "Capp"})
            response = get_response(
                admin_user,
                view,
                method,
                url.format(pk=menu_item.pk),
                data=payload,
                pk=menu_item.pk,
            )
            menu_item.refresh_from_db()
            assert response.status_code == status.HTTP_200_OK
            assert menu_item.name == "Capp"

    """ def test_get_menu_item_with_ingredients(self, api_rf):
        menu_item = MenuItemFactory(name="Pizza Margherita")
        ingredient = IngredientFactory(name="Mozzarella")
        MenuItemIngredientFactory(
            menu_item=menu_item, ingredient=ingredient, quantity="200", unit="g"
        )

        url = f"/menu-items/{menu_item.id}/ingredients/"
        response = api_rf.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data == [
            {"ingredient": "Mozzarella", "quantity": "200", "unit": "g"}
        ]

    def test_add_ingredient_to_menu_item(self, api_rf):
        menu_item = MenuItemFactory(name="Lasagna")
        ingredient = IngredientFactory(name="Cheese")

        url = f"/menu-items/{menu_item.id}/add_ingredient/"
        payload = {"ingredient_id": ingredient.id, "quantity": "300", "unit": "g"}
        response = api_rf.post(url, payload)

        assert response.status_code == status.HTTP_201_CREATED
        assert MenuItemIngredient.objects.filter(
            menu_item=menu_item, ingredient=ingredient
        ).exists()

    def test_fail_add_invalid_ingredient(self, api_rf):
        menu_item = MenuItemFactory(name="Lasagna")

        url = f"/menu-items/{menu_item.id}/add_ingredient/"
        payload = {
            "ingredient_id": 9999,
            "quantity": "300",
            "unit": "g",
        }  # Non-existent ingredient
        response = api_rf.post(url, payload)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "Invalid ingredient ID" in response.data["error"]


@pytest.mark.django_db
class TestMenuItemIngredientEndpoints:

    def test_update_menu_item_ingredient(self, api_rf):
        menu_item_ingredient = MenuItemIngredientFactory(quantity="200", unit="ml")
        url = f"/menu-item-ingredients/{menu_item_ingredient.id}/"
        payload = {"quantity": "500", "unit": "ml"}
        response = api_rf.put(url, payload)

        menu_item_ingredient.refresh_from_db()
        assert response.status_code == status.HTTP_200_OK
        assert menu_item_ingredient.quantity == "500"

    def test_delete_menu_item_ingredient(self, api_rf):
        menu_item_ingredient = MenuItemIngredientFactory()
        url = f"/menu-item-ingredients/{menu_item_ingredient.id}/"
        response = api_rf.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not MenuItemIngredient.objects.filter(
            id=menu_item_ingredient.id
        ).exists()
 """
