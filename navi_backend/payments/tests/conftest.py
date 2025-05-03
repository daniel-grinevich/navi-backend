import pytest
import json

# from .factories import PaymentTypeFactory


# @pytest.fixture
# def payment_type():
#     return PaymentTypeFactory(name="Payment_2")


@pytest.fixture
def payment_type_data(admin_user):
    return json.dumps(
        {
            "name": "Payment_Type_1",
            "status": "A",
        }
    )


# @pytest.fixture
# def payment_type():
#     return PaymentTypeFactory(name="Payment_2")
