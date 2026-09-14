import pytest
from django.core.exceptions import ValidationError

from .factories import EspressoMachineFactory
from .factories import MachineTypeFactory
from .factories import NaviPortFactory
from .factories import RaspberryPiFactory


@pytest.mark.django_db
class TestRaspberryPi:
    def test_raspberry_pi_string_representation(self):
        pi = RaspberryPiFactory(name="Test Pi")
        assert str(pi) == "Test Pi"

    def test_raspberry_pi_unique_mac_address(self):
        mac = "01:23:45:67:89:AB"
        RaspberryPiFactory(mac_address=mac)

        with pytest.raises(ValidationError):
            RaspberryPiFactory(mac_address=mac)


@pytest.mark.django_db
class TestMachineType:
    def test_machine_type_string_representation(self):
        machine_type = MachineTypeFactory(name="Espresso Master 3000")
        assert str(machine_type) == "Espresso Master 3000"


@pytest.mark.django_db
class TestEspressoMachine:
    def test_espresso_machine_string_representation(self):
        machine = EspressoMachineFactory(name="Barista Pro")
        assert str(machine) == "Barista Pro"

    def test_espresso_machine_unique_serial_number(self):
        serial = "EM001-2024"
        EspressoMachineFactory(serial_number=serial)

        with pytest.raises(ValidationError):
            EspressoMachineFactory(serial_number=serial)


@pytest.mark.django_db
class TestNaviPort:
    def test_navi_port_string_representation(self):
        navi_port = NaviPortFactory(name="Port Alpha")
        assert str(navi_port) == "Port Alpha"
