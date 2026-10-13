import factory
from django.utils import timezone

from navi_backend.core.tests.factories import AuditFactory
from navi_backend.core.tests.factories import SlugifiedFactory
from navi_backend.core.tests.factories import StatusFactory
from navi_backend.core.tests.factories import UpdateRecordFactory
from navi_backend.devices.managers import hash_device_token
from navi_backend.devices.models import EspressoMachine
from navi_backend.devices.models import MachineType
from navi_backend.devices.models import NaviPort
from navi_backend.devices.models import RaspberryPi


class RaspberryPiFactory(
    AuditFactory,
    SlugifiedFactory,
    StatusFactory,
    UpdateRecordFactory,
    factory.django.DjangoModelFactory,
):
    class Meta:
        model = RaspberryPi

    name = factory.Sequence(lambda n: f"pi-server-{n:03d}")
    mac_address = factory.Faker("mac_address")
    ip_address = factory.Faker("ipv4")
    location = factory.Faker("address")
    is_connected = factory.Faker("boolean")
    firmware_version = factory.Faker("bothify", text="v#.##")
    last_seen = factory.LazyFunction(timezone.now)

    @factory.post_generation
    def device_token(self, create, extracted, **kwargs):
        # Only the hash is stored; keep the plaintext on the instance so tests
        # can authenticate as this Pi via ``pi.device_token``.
        self.device_token = extracted or self.issue_token()
        if extracted:
            self.token_hash = hash_device_token(extracted)
        if create:
            RaspberryPi.objects.filter(pk=self.pk).update(token_hash=self.token_hash)


class MachineTypeFactory(
    AuditFactory,
    SlugifiedFactory,
    StatusFactory,
    UpdateRecordFactory,
    factory.django.DjangoModelFactory,
):
    class Meta:
        model = MachineType

    name = factory.Sequence(lambda n: f"Machine Type {n:03d}")
    model_number = factory.Faker("bothify", text="MT###")
    maintenance_frequency = factory.Faker("random_int", min=30, max=365)

    @factory.post_generation
    def supported_drinks(self, create, extracted, **kwargs):
        if not create or not extracted:
            # Simple build, or nothing to add, do nothing.
            return

        # Add the iterable of groups using bulk addition
        self.supported_drinks.add(*extracted)


class EspressoMachineFactory(
    AuditFactory,
    SlugifiedFactory,
    StatusFactory,
    UpdateRecordFactory,
    factory.django.DjangoModelFactory,
):
    class Meta:
        model = EspressoMachine

    name = factory.Iterator(["EversysV1", "EversysV2", "Jura"])
    serial_number = factory.Faker("bothify", text="EM###-####")
    machine_type = factory.SubFactory(MachineTypeFactory)
    ip_address = factory.Faker("ipv4")
    port = factory.Faker("random_int", min=3000, max=9000)
    is_online = factory.Faker("boolean")
    last_maintenance_at = factory.LazyFunction(timezone.now)


class NaviPortFactory(
    AuditFactory,
    SlugifiedFactory,
    StatusFactory,
    UpdateRecordFactory,
    factory.django.DjangoModelFactory,
):
    name = factory.Sequence(lambda n: f"NaviPort-{n:03d}")
    espresso_machine = factory.SubFactory(EspressoMachineFactory)
    raspberry_pi = factory.SubFactory(RaspberryPiFactory)
    latitude = factory.Faker(
        "pydecimal",
        left_digits=2,
        right_digits=6,
        positive=False,
        min_value=-90,
        max_value=90,
    )
    longitude = factory.Faker(
        "pydecimal",
        left_digits=3,
        right_digits=6,
        positive=False,
        min_value=-180,
        max_value=180,
    )
    address_line_1 = factory.Faker("street_address")
    city = factory.Faker("city")
    postal_code = factory.Faker("postcode")

    class Meta:
        model = NaviPort
