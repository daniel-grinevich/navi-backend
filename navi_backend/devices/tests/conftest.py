import json

import pytest

from navi_backend.menu.tests.factories import MenuItemFactory

from .factories import EspressoMachineFactory
from .factories import MachineTypeFactory
from .factories import NaviPortFactory
from .factories import RaspberryPiFactory


@pytest.fixture
def raspberry_pi(db):
    return RaspberryPiFactory()


@pytest.fixture
def raspberry_pi_data():
    return json.dumps(
        {
            "name": "Raspberry_Pi_1",
            "mac_address": "01:23:45:67:89:AB",
            "ip_address": "192.168.1.1",
            "location": "test",
            "is_connected": True,
            "firmware_version": "v1",
        }
    )


@pytest.fixture
def espresso_machine(db):
    return EspressoMachineFactory()


@pytest.fixture
def espresso_machine_data():
    machine_type = MachineTypeFactory()
    return json.dumps(
        {
            "name": "Espresso_Machine_1",
            "machine_type": machine_type.pk,
            "serial_number": "12345",
            "ip_address": "192.168.1.1",
            "port": 1,
            "is_online": True,
            "last_maintenance_at": "2012-04-23T18:25:43.511Z",
        }
    )


@pytest.fixture
def machine_type(db):
    return MachineTypeFactory()


@pytest.fixture
def machine_type_data():
    menu_item = MenuItemFactory()

    return json.dumps(
        {
            "name": "Machine_Type_1",
            "model_number": "1",
            "maintenance_frequency": 30,
            "supported_drinks": [menu_item.pk],
        }
    )


@pytest.fixture
def navi_port_data():
    espresso_machine = EspressoMachineFactory(name="navi1")
    raspberry_pi = RaspberryPiFactory(name="razz")
    return json.dumps(
        {
            "name": "Navi_Port_1",
            "status": "A",
            "raspberry_pi": raspberry_pi.pk,
            "espresso_machine": espresso_machine.pk,
        }
    )


@pytest.fixture
def navi_port():
    return NaviPortFactory(name="Navi_Port_2")
