import pytest
import json
from django.db import transaction
from django.urls import reverse
from rest_framework import status

# from ..api.views import PaymentTypeViewSet

# @pytest.mark.django_db
# class TestPaymentTypeViewSet:

#     @pytest.mark.parametrize(
#         "view_name, method, url",
#         [
#             ("create", "POST", "/api/payment_types/"),
#             (
#                 "partial_update",
#                 "PATCH",
#                 "/api/payment_types/{pk}/",
#             ),
#             (
#                 "destroy",
#                 "DELETE",
#                 "/api/payment_types/{pk}/",
#             ),
#         ],
#     )
#     def test_write_access(
#         self,
#         get_response,
#         admin_user,
#         user,
#         method,
#         view_name,
#         url,
#         payment_type_data,
#         payment_type,
#     ):
#         view = PaymentTypeViewSet.as_view({method.lower(): view_name})
#         if view_name == "create":
#             response = get_response(
#                 user,
#                 view,
#                 method,
#                 url,
#                 data=payment_type_data,
#             )
#             assert response.status_code in [
#                 status.HTTP_403_FORBIDDEN,
#                 status.HTTP_404_NOT_FOUND,
#             ]
#             response = get_response(
#                 admin_user,
#                 view,
#                 method,
#                 url,
#                 data=payment_type_data,
#             )
#             assert response.status_code == status.HTTP_201_CREATED
#             assert PaymentType.objects.filter(name="Payment_Type_1").exists()

#         if view_name == "delete":
#             response = get_response(
#                 user,
#                 view,
#                 method,
#                 url.format(pk=payment_type.pk),
#                 pk=payment_type.pk,
#             )
#             assert response.status_code in [
#                 status.HTTP_403_FORBIDDEN,
#                 status.HTTP_404_NOT_FOUND,
#             ]
#             response = get_response(
#                 admin_user,
#                 view,
#                 method,
#                 url.format(pk=payment_type.pk),
#                 pk=payment_type.pk,
#             )
#             assert response.status_code == status.HTTP_204_NO_CONTENT
#             assert not PaymentType.objects.filter(id=payment_type.id).exists()

#         if view_name == "partial_update":
#             payload = json.dumps({"name": "Payment_Type_Update"})
#             response = get_response(
#                 user,
#                 view,
#                 method,
#                 url.format(pk=payment_type.pk),
#                 data=payload,
#                 pk=payment_type.pk,
#             )
#             assert response.status_code in [
#                 status.HTTP_403_FORBIDDEN,
#                 status.HTTP_404_NOT_FOUND,
#             ]
#             response = get_response(
#                 admin_user,
#                 view,
#                 method,
#                 url.format(pk=payment_type.pk),
#                 data=payload,
#                 pk=payment_type.pk,
#             )
#             payment_type.refresh_from_db()
#             assert response.status_code == status.HTTP_200_OK
#             assert payment_type.name == "Payment_Type_Update"

#     @pytest.mark.parametrize(
#         "view_name, method, url",
#         [
#             ("list", "GET", "/api/payment_types/"),
#             ("retrieve", "GET", "/api/payment_types/{pk}/"),
#         ],
#     )
#     def test_view_access(self, user, get_response, view_name, method, url):
#         payment_types = PaymentTypeFactory.create_batch(3)
#         view = PaymentTypeViewSet.as_view({method.lower(): view_name})

#         if view_name == "list":
#             response = get_response(user, view, method, url)
#             assert response.status_code == status.HTTP_200_OK
#             assert len(response.data) == 3

#         if view_name == "retrieve":
#             for payment_type in payment_types:
#                 response = get_response(
#                     user,
#                     view,
#                     method,
#                     url.format(pk=payment_type.pk),
#                     pk=payment_type.pk,
#                 )
#                 assert response.status_code == status.HTTP_200_OK
