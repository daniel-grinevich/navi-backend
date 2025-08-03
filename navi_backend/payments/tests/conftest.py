import json

import pytest


@pytest.fixture
def payment_type_data(admin_user):
    return json.dumps(
        {
            "name": "Payment_Type_1",
            "status": "A",
        }
    )
