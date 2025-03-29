import pytest
import json
from django.db import transaction
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
    OrderItemFactory,
    MenuItemFactory,
    IngredientFactory,
    MenuItemIngredientFactory,
    NaviPortFactory,
    PaymentTypeFactory,
    OrderFactory,
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
    NaviPortViewSet,
    PaymentTypeViewSet,
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
    def test_user_view_access(
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
    def test_admin_view_access(
        self, admin_and_orders, get_response, view_name, method, url
    ):
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

    @pytest.mark.parametrize(
        "view_name, method, url",
        [
            ("create", "POST", "/api/orders/"),
            ("destroy", "DELETE", "/api/orders/{pk}/"),
            ("partial_update", "PATCH", "/api/orders/{pk}/"),
        ],
    )
    def test_write_access(
        self,
        admin_user,
        user_and_orders,
        order_data,
        get_response,
        view_name,
        method,
        url,
    ):
        view = OrderViewSet.as_view({method.lower(): view_name})
        user, own_order, other_order = user_and_orders
        if view_name == "create":
            response = get_response(user, view, method, url, data=order_data)
            assert response.status_code == status.HTTP_201_CREATED
            assert Order.objects.filter(user=user.pk).exists()

        if view_name == "delete":
            response = get_response(
                user,
                view,
                method,
                url.format(pk=own_order.pk),
                pk=own_order.pk,
            )
            assert response.status_code in [
                status.HTTP_403_FORBIDDEN,
                status.HTTP_404_NOT_FOUND,
            ]
            response = get_response(
                admin_user,
                view,
                method,
                url.format(pk=own_order.pk),
                pk=own_order.pk,
            )
            assert response.status_code == status.HTTP_204_NO_CONTENT
            assert not Order.objects.filter(id=own_order.id).exists()

        if view_name == "partial_update":
            payload = json.dumps({"price": "100"})
            response = get_response(
                user,
                view,
                method,
                url.format(pk=other_order.pk),
                data=payload,
                pk=other_order.pk,
            )
            assert response.status_code in [
                status.HTTP_403_FORBIDDEN,
                status.HTTP_404_NOT_FOUND,
            ]
            response = get_response(
                admin_user,
                view,
                method,
                url.format(pk=other_order.pk),
                data=payload,
                pk=other_order.pk,
            )
            other_order.refresh_from_db()
            assert response.status_code == status.HTTP_200_OK
            assert other_order.price == 100.00


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
    def test_write_access(
        self,
        get_response,
        admin_user,
        user,
        ingredient_data,
        view_name,
        method,
        url,
        ingredient,
    ):
        view = IngredientViewSet.as_view({method.lower(): view_name})
        if view_name == "create":
            response = get_response(user, view, method, url, data=ingredient_data)
            assert response.status_code in [
                status.HTTP_403_FORBIDDEN,
                status.HTTP_404_NOT_FOUND,
            ]
            response = get_response(admin_user, view, method, url, data=ingredient_data)
            assert response.status_code == status.HTTP_201_CREATED
            assert Ingredient.objects.filter(name="Tomato Sauce").exists()

        if view_name == "delete":
            response = get_response(
                user,
                view,
                method,
                url.format(pk=ingredient.pk),
                pk=ingredient.pk,
            )
            assert response.status_code in [
                status.HTTP_403_FORBIDDEN,
                status.HTTP_404_NOT_FOUND,
            ]
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
                user,
                view,
                method,
                url.format(pk=ingredient.pk),
                data=payload,
                pk=ingredient.pk,
            )
            assert response.status_code in [
                status.HTTP_403_FORBIDDEN,
                status.HTTP_404_NOT_FOUND,
            ]
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
    def test_view_access(self, admin_user, get_response, view_name, method, url):
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
            ("create", "POST", "/api/menu_items/"),
            ("destroy", "DELETE", "/api/menu_items/{pk}/"),
            ("partial_update", "PATCH", "/api/menu_items/{pk}/"),
        ],
    )
    def test_write_access(
        self,
        get_response,
        admin_user,
        user,
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
            response.user = user
            with transaction.atomic():
                user_response = view(response)
                assert user_response.status_code in [
                    status.HTTP_403_FORBIDDEN,
                    status.HTTP_404_NOT_FOUND,
                ]
            response.user = admin_user
            admin_response = view(response)
            assert admin_response.status_code == status.HTTP_201_CREATED
            assert MenuItem.objects.filter(name="Latte").exists()

        if view_name == "delete":
            response = get_response(
                user,
                view,
                method,
                url.format(pk=menu_item.pk),
                pk=menu_item.pk,
            )
            assert response.status_code in [
                status.HTTP_403_FORBIDDEN,
                status.HTTP_404_NOT_FOUND,
            ]
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
                user,
                view,
                method,
                url.format(pk=menu_item.pk),
                data=payload,
                pk=menu_item.pk,
            )
            assert response.status_code in [
                status.HTTP_403_FORBIDDEN,
                status.HTTP_404_NOT_FOUND,
            ]
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

    @pytest.mark.parametrize(
        "view_name, method, url",
        [
            ("list", "GET", "/api/menu_items/"),
            ("retrieve", "GET", "/api/menu_items/{pk}/"),
        ],
    )
    def test_view_access(self, user, get_response, view_name, method, url):
        menu_items = MenuItemFactory.create_batch(3)
        view = MenuItemViewSet.as_view({method.lower(): view_name})

        if view_name == "list":
            response = get_response(user, view, method, url)
            assert response.status_code == status.HTTP_200_OK
            assert len(response.data) == 3

        if view_name == "retrieve":
            for menu_item in menu_items:
                response = get_response(
                    user,
                    view,
                    method,
                    url.format(pk=menu_item.pk),
                    pk=menu_item.pk,
                )
                assert response.status_code == status.HTTP_200_OK

    def test_get_menu_item_with_ingredients(
        self, menu_item_ingredient, get_response, user
    ):
        view = MenuItemIngredientViewSet.as_view({"get": "list"})
        menu_item = menu_item_ingredient.menu_item
        url = f"/menuitems/{menu_item.pk}/ingredients/"
        response = get_response(user, view, "GET", url)
        assert response.status_code == status.HTTP_200_OK

    def test_add_ingredient_to_menu_item(
        self, menu_item, ingredient, get_response, admin_user, user
    ):
        view = MenuItemViewSet.as_view({"post": "add_ingredient"})
        url = f"/menuitems/{menu_item.pk}/add_ingredient/"
        payload = json.dumps(
            {"ingredient_id": ingredient.id, "quantity": "300", "unit": "g"}
        )
        response = get_response(
            user,
            view,
            "POST",
            url.format(pk=menu_item.pk),
            data=payload,
            pk=menu_item.pk,
        )
        assert response.status_code in [
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        ]
        response = get_response(
            admin_user,
            view,
            "POST",
            url.format(pk=menu_item.pk),
            data=payload,
            pk=menu_item.pk,
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert MenuItemIngredient.objects.filter(
            menu_item=menu_item, ingredient=ingredient
        ).exists()

    def test_fail_add_invalid_ingredient(self, menu_item, get_response, admin_user):
        view = MenuItemViewSet.as_view({"post": "add_ingredient"})
        url = f"/menu_items/{menu_item.pk}/add_ingredient/"
        payload = json.dumps(
            {
                "ingredient_id": 9999,
                "quantity": "300",
                "unit": "g",
            }
        )  # Non-existent ingredient
        response = get_response(
            admin_user,
            view,
            "POST",
            url.format(pk=menu_item.pk),
            data=payload,
            pk=menu_item.pk,
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "Invalid ingredient ID" in response.data["error"]


@pytest.mark.django_db
class TestMenuItemIngredientViewSet:

    @pytest.mark.parametrize(
        "view_name, method, url",
        [
            ("create", "POST", "/api/menu_item_ingredients/"),
            (
                "partial_update",
                "PATCH",
                "/api/menu_item_ingredients/{pk}/",
            ),
            (
                "destroy",
                "DELETE",
                "/api/menu_item_ingredients/{pk}/",
            ),
        ],
    )
    def test_write_access(
        self,
        get_response,
        admin_user,
        user,
        method,
        view_name,
        url,
        menu_item_ingredient_data,
        menu_item_ingredient,
    ):
        view = MenuItemIngredientViewSet.as_view({method.lower(): view_name})
        if view_name == "create":
            response = get_response(
                user,
                view,
                method,
                url,
                data=menu_item_ingredient_data,
            )
            assert response.status_code in [
                status.HTTP_403_FORBIDDEN,
                status.HTTP_404_NOT_FOUND,
            ]
            response = get_response(
                admin_user,
                view,
                method,
                url,
                data=menu_item_ingredient_data,
            )
            assert response.status_code == status.HTTP_201_CREATED
            assert MenuItemIngredient.objects.filter(
                menu_item__name__contains="Capp"
            ).exists()

        if view_name == "delete":
            response = get_response(
                user,
                view,
                method,
                url.format(pk=menu_item_ingredient.pk),
                pk=menu_item_ingredient.pk,
            )
            assert response.status_code in [
                status.HTTP_403_FORBIDDEN,
                status.HTTP_404_NOT_FOUND,
            ]
            response = get_response(
                admin_user,
                view,
                method,
                url.format(pk=menu_item_ingredient.pk),
                pk=menu_item_ingredient.pk,
            )
            assert response.status_code == status.HTTP_204_NO_CONTENT
            assert not MenuItemIngredient.objects.filter(
                id=menu_item_ingredient.id
            ).exists()

        if view_name == "partial_update":
            payload = json.dumps({"quantity": "999"})
            response = get_response(
                user,
                view,
                method,
                url.format(pk=menu_item_ingredient.pk),
                data=payload,
                pk=menu_item_ingredient.pk,
            )
            assert response.status_code in [
                status.HTTP_403_FORBIDDEN,
                status.HTTP_404_NOT_FOUND,
            ]
            response = get_response(
                admin_user,
                view,
                method,
                url.format(pk=menu_item_ingredient.pk),
                data=payload,
                pk=menu_item_ingredient.pk,
            )
            menu_item_ingredient.refresh_from_db()
            assert response.status_code == status.HTTP_200_OK
            assert menu_item_ingredient.quantity == 999.00

    @pytest.mark.parametrize(
        "view_name, method, url",
        [
            ("list", "GET", "/api/menu_item_ingredients/"),
            ("retrieve", "GET", "/api/menu_item_ingredients/{pk}/"),
        ],
    )
    def test_view_access(self, user, get_response, view_name, method, url):
        menu_item_ingredients = MenuItemIngredientFactory.create_batch(3)
        view = MenuItemIngredientViewSet.as_view({method.lower(): view_name})

        if view_name == "list":
            response = get_response(user, view, method, url)
            assert response.status_code == status.HTTP_200_OK
            assert len(response.data) == 3

        if view_name == "retrieve":
            for menu_item_ingredient in menu_item_ingredients:
                response = get_response(
                    user,
                    view,
                    method,
                    url.format(pk=menu_item_ingredient.pk),
                    pk=menu_item_ingredient.pk,
                )
                assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestNaviPortViewSet:

    @pytest.mark.parametrize(
        "view_name, method, url",
        [
            ("create", "POST", "/api/navi_ports/"),
            (
                "partial_update",
                "PATCH",
                "/api/navi_ports/{pk}/",
            ),
            (
                "destroy",
                "DELETE",
                "/api/navi_ports/{pk}/",
            ),
        ],
    )
    def test_write_access(
        self,
        get_response,
        admin_user,
        user,
        method,
        view_name,
        url,
        navi_port_data,
        navi_port,
    ):
        view = NaviPortViewSet.as_view({method.lower(): view_name})
        if view_name == "create":
            response = get_response(
                user,
                view,
                method,
                url,
                data=navi_port_data,
            )
            assert response.status_code in [
                status.HTTP_403_FORBIDDEN,
                status.HTTP_404_NOT_FOUND,
            ]
            response = get_response(
                admin_user,
                view,
                method,
                url,
                data=navi_port_data,
            )
            assert response.status_code == status.HTTP_201_CREATED
            assert NaviPort.objects.filter(name="Navi_Port_1").exists()

        if view_name == "delete":
            response = get_response(
                user,
                view,
                method,
                url.format(pk=navi_port.pk),
                pk=navi_port.pk,
            )
            assert response.status_code in [
                status.HTTP_403_FORBIDDEN,
                status.HTTP_404_NOT_FOUND,
            ]
            response = get_response(
                admin_user,
                view,
                method,
                url.format(pk=navi_port.pk),
                pk=navi_port.pk,
            )
            assert response.status_code == status.HTTP_204_NO_CONTENT
            assert not NaviPort.objects.filter(id=navi_port.id).exists()

        if view_name == "partial_update":
            payload = json.dumps({"name": "DanielSucks"})
            response = get_response(
                user,
                view,
                method,
                url.format(pk=navi_port.pk),
                data=payload,
                pk=navi_port.pk,
            )
            assert response.status_code in [
                status.HTTP_403_FORBIDDEN,
                status.HTTP_404_NOT_FOUND,
            ]
            response = get_response(
                admin_user,
                view,
                method,
                url.format(pk=navi_port.pk),
                data=payload,
                pk=navi_port.pk,
            )
            navi_port.refresh_from_db()
            assert response.status_code == status.HTTP_200_OK
            assert navi_port.name == "DanielSucks"

    @pytest.mark.parametrize(
        "view_name, method, url",
        [
            ("list", "GET", "/api/api/navi_ports/"),
            ("retrieve", "GET", "/api/navi_ports/{pk}/"),
        ],
    )
    def test_view_access(self, user, get_response, view_name, method, url):
        navi_ports = NaviPortFactory.create_batch(3)
        view = NaviPortViewSet.as_view({method.lower(): view_name})

        if view_name == "list":
            response = get_response(user, view, method, url)
            assert response.status_code == status.HTTP_200_OK
            assert len(response.data) == 3

        if view_name == "retrieve":
            for navi_port in navi_ports:
                response = get_response(
                    user,
                    view,
                    method,
                    url.format(pk=navi_port.pk),
                    pk=navi_port.pk,
                )
                assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestPaymentTypeViewSet:

    @pytest.mark.parametrize(
        "view_name, method, url",
        [
            ("create", "POST", "/api/payment_types/"),
            (
                "partial_update",
                "PATCH",
                "/api/payment_types/{pk}/",
            ),
            (
                "destroy",
                "DELETE",
                "/api/payment_types/{pk}/",
            ),
        ],
    )
    def test_write_access(
        self,
        get_response,
        admin_user,
        user,
        method,
        view_name,
        url,
        payment_type_data,
        payment_type,
    ):
        view = PaymentTypeViewSet.as_view({method.lower(): view_name})
        if view_name == "create":
            response = get_response(
                user,
                view,
                method,
                url,
                data=payment_type_data,
            )
            assert response.status_code in [
                status.HTTP_403_FORBIDDEN,
                status.HTTP_404_NOT_FOUND,
            ]
            response = get_response(
                admin_user,
                view,
                method,
                url,
                data=payment_type_data,
            )
            assert response.status_code == status.HTTP_201_CREATED
            assert PaymentType.objects.filter(name="Payment_Type_1").exists()

        if view_name == "delete":
            response = get_response(
                user,
                view,
                method,
                url.format(pk=payment_type.pk),
                pk=payment_type.pk,
            )
            assert response.status_code in [
                status.HTTP_403_FORBIDDEN,
                status.HTTP_404_NOT_FOUND,
            ]
            response = get_response(
                admin_user,
                view,
                method,
                url.format(pk=payment_type.pk),
                pk=payment_type.pk,
            )
            assert response.status_code == status.HTTP_204_NO_CONTENT
            assert not PaymentType.objects.filter(id=payment_type.id).exists()

        if view_name == "partial_update":
            payload = json.dumps({"name": "Payment_Type_Update"})
            response = get_response(
                user,
                view,
                method,
                url.format(pk=payment_type.pk),
                data=payload,
                pk=payment_type.pk,
            )
            assert response.status_code in [
                status.HTTP_403_FORBIDDEN,
                status.HTTP_404_NOT_FOUND,
            ]
            response = get_response(
                admin_user,
                view,
                method,
                url.format(pk=payment_type.pk),
                data=payload,
                pk=payment_type.pk,
            )
            payment_type.refresh_from_db()
            assert response.status_code == status.HTTP_200_OK
            assert payment_type.name == "Payment_Type_Update"

    @pytest.mark.parametrize(
        "view_name, method, url",
        [
            ("list", "GET", "/api/payment_types/"),
            ("retrieve", "GET", "/api/payment_types/{pk}/"),
        ],
    )
    def test_view_access(self, user, get_response, view_name, method, url):
        payment_types = PaymentTypeFactory.create_batch(3)
        view = PaymentTypeViewSet.as_view({method.lower(): view_name})

        if view_name == "list":
            response = get_response(user, view, method, url)
            assert response.status_code == status.HTTP_200_OK
            assert len(response.data) == 3

        if view_name == "retrieve":
            for payment_type in payment_types:
                response = get_response(
                    user,
                    view,
                    method,
                    url.format(pk=payment_type.pk),
                    pk=payment_type.pk,
                )
                assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestOrderItemViewSet:
    @pytest.mark.parametrize(
        "view_name, method, url",
        [
            ("list", "GET", "/api/orders/{order_pk}/items/"),
            ("retrieve", "GET", "/api/orders/{order_pk}/items/{pk}/"),
        ],
    )
    def test_view_access(
        self, admin_user, get_response, view_name, method, url, order_and_order_items
    ):
        order = OrderFactory()
        order_item_1 = OrderItemFactory(order=order)
        order_item_2 = OrderItemFactory(order=order)
        order_item_3 = OrderItemFactory(order=order)
        view = OrderItemViewSet.as_view({method.lower(): view_name})

        if view_name == "list":
            response = get_response(
                admin_user, view, method, url.format(order_pk=order.pk)
            )
            assert response.status_code == status.HTTP_200_OK
            assert len(response.data) == 3

        if view_name == "retrieve":
            for order_item in [order_item_1, order_item_2, order_item_3]:
                response = get_response(
                    admin_user,
                    view,
                    method,
                    url.format(pk=order_item.pk, order_pk=order.pk),
                    pk=order_item.pk,
                )
                print(url.format(pk=order_item.pk, order_pk=order.pk))
                print(order_item.pk)
                print(order.pk)
                assert response.status_code == status.HTTP_200_OK
