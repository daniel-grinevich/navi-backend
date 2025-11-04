import pytest
from django.db import IntegrityError
from django.core.exceptions import ValidationError

from navi_backend.menu.tests.factories import MenuItemFactory

from .factories import EspressoMachineFactory
from .factories import MachineTypeFactory
from .factories import NaviPortFactory
from .factories import RaspberryPiFactory

@pytest.mark.django_db
class TestRaspberryPi:
    def test_create_raspberry_pi(self, raspberry_pi):
        assert raspberry_pi
        assert raspberry_pi.name
        assert raspberry_pi.mac_address
        assert raspberry_pi.slug

    def test_raspberry_pi_string_representation(self):
        pi = RaspberryPiFactory(name="Test Pi")
        assert str(pi) == "Test Pi"

    def test_raspberry_pi_unique_mac_address(self):
        mac = "01:23:45:67:89:AB"
        RaspberryPiFactory(mac_address=mac)

        with pytest.raises(ValidationError):
            RaspberryPiFactory(mac_address=mac)

    def test_raspberry_pi_connection_status(self):
        pi = RaspberryPiFactory(is_connected=True)
        assert pi.is_connected is True

        pi.is_connected = False
        pi.save()
        assert pi.is_connected is False

    def test_raspberry_pi_last_seen_auto_update(self):
        pi = RaspberryPiFactory()
        original_time = pi.last_seen

        # Update to trigger last_seen change
        pi.location = "New Location"
        pi.save()
        pi.refresh_from_db()

        assert pi.last_seen >= original_time

@pytest.mark.django_db
class TestMachineType:
    def test_create_machine_type(self, machine_type):
        assert machine_type
        assert machine_type.name
        assert machine_type.model_number
        assert machine_type.maintenance_frequency > 0

    def test_machine_type_string_representation(self):
        machine_type = MachineTypeFactory(name="Espresso Master 3000")
        assert str(machine_type) == "Espresso Master 3000"

    def test_machine_type_supported_drinks(self):
        menu_item1 = MenuItemFactory(name="Espresso")
        menu_item2 = MenuItemFactory(name="Cappuccino")

        machine_type = MachineTypeFactory()
        machine_type.supported_drinks.add(menu_item1, menu_item2)

        assert machine_type.supported_drinks.count() == 2
        assert menu_item1 in machine_type.supported_drinks.all()
        assert menu_item2 in machine_type.supported_drinks.all()

    def test_machine_type_maintenance_frequency(self):
        machine_type = MachineTypeFactory(maintenance_frequency=30)
        assert machine_type.maintenance_frequency == 30

@pytest.mark.django_db
class TestEspressoMachine:
    def test_create_espresso_machine(self, espresso_machine):
        assert espresso_machine
        assert espresso_machine.name
        assert espresso_machine.serial_number
        assert espresso_machine.machine_type

    def test_espresso_machine_string_representation(self):
        machine = EspressoMachineFactory(name="Barista Pro")
        assert str(machine) == "Barista Pro"

    def test_espresso_machine_unique_serial_number(self):
        serial = "EM001-2024"
        EspressoMachineFactory(serial_number=serial)

        with pytest.raises(ValidationError):
            EspressoMachineFactory(serial_number=serial)

    def test_espresso_machine_online_status(self):
        machine = EspressoMachineFactory(is_online=True)
        assert machine.is_online is True

        machine.is_online = False
        machine.save()
        assert machine.is_online is False

    def test_espresso_machine_with_machine_type(self):
        machine_type = MachineTypeFactory(name="Premium Type")
        machine = EspressoMachineFactory(machine_type=machine_type)

        assert machine.machine_type == machine_type
        assert machine.machine_type.name == "Premium Type"

    def test_espresso_machine_network_settings(self):
        machine = EspressoMachineFactory(ip_address="192.168.1.100", port=8080)
        assert machine.ip_address == "192.168.1.100"
        assert machine.port == 8080

@pytest.mark.django_db
class TestNaviPort:
    def test_create_navi_port(self, navi_port):
        assert navi_port
        assert navi_port.name
        assert navi_port.espresso_machine
        assert navi_port.raspberry_pi

    def test_navi_port_string_representation(self):
        navi_port = NaviPortFactory(name="Port Alpha")
        assert str(navi_port) == "Port Alpha"

    def test_navi_port_with_devices(self):
        pi = RaspberryPiFactory(name="Pi Device")
        machine = EspressoMachineFactory(name="Machine Device")

        port = NaviPortFactory(
            name="Test Port", raspberry_pi=pi, espresso_machine=machine
        )

        assert port.raspberry_pi == pi
        assert port.espresso_machine == machine

    def test_navi_port_optional_devices(self):
        # Test that devices can be None
        port = NaviPortFactory(raspberry_pi=None, espresso_machine=None)

        assert port.raspberry_pi is None
        assert port.espresso_machine is None

    def test_navi_port_device_relationships(self):
        pi = RaspberryPiFactory()
        machine = EspressoMachineFactory()
        port = NaviPortFactory(raspberry_pi=pi, espresso_machine=machine)

        # Test reverse relationships
        assert port in pi.navi_port.all()
        assert port in machine.navi_port.all()

    def test_navi_port_cascade_behavior(self):
        """Test that deleting devices sets NaviPort fields to null"""
        pi = RaspberryPiFactory()
        machine = EspressoMachineFactory()
        port = NaviPortFactory(raspberry_pi=pi, espresso_machine=machine)

        # Delete the pi and machine
        pi.delete()
        machine.delete()

        # Refresh port from database
        port.refresh_from_db()

        # Check that the foreign keys are now null
        assert port.raspberry_pi is None
        assert port.espresso_machine is None
