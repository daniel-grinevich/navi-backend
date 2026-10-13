"""Register (or refresh) a simulator Raspberry Pi for local development.

Creates a RaspberryPi + a NaviPort linked to it, marks it enabled, issues a
fresh device token and prints it for the navi-pi container's
NAVI_DEVICE_TOKEN. Tokens are stored hashed, so every registration rotates the
token (the old one stops working).

    python manage.py register_sim_pi                 # token + summary
    python manage.py register_sim_pi --env           # KEY=value lines (scripts)
    python manage.py register_sim_pi --test-order    # queue a $0 test order
    python manage.py register_sim_pi --order <id>    # QR token for an order

``--test-order`` and ``--order`` leave the token alone, so they're safe to run
against a sim that's already up.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError

from navi_backend.devices.models import NaviPort
from navi_backend.devices.models import RaspberryPi
from navi_backend.devices.services import fleet
from navi_backend.orders.models import Order
from navi_backend.orders.qr import make_qr_token
from navi_backend.orders.services.device_test_order_service import DeviceNotReadyError
from navi_backend.orders.services.device_test_order_service import create_test_order

SIM_PI_NAME = "Simulator Pi"
SIM_PI_MAC = "00:00:00:00:00:01"
SIM_PORT_NAME = "Simulator NaviPort"

User = get_user_model()


class Command(BaseCommand):
    help = "Register a simulator Raspberry Pi + NaviPort for local development."

    def add_arguments(self, parser):
        parser.add_argument(
            "--env",
            action="store_true",
            help="Print NAVI_SIM_PI_ID / NAVI_DEVICE_TOKEN lines (for scripts).",
        )
        parser.add_argument(
            "--test-order",
            action="store_true",
            help="Queue a $0 test order at the sim's NaviPort (token unchanged).",
        )
        parser.add_argument(
            "--order",
            help="Print the signed QR token for this order id (token unchanged).",
        )

    def handle(self, *args, **options):
        actor = self._system_user()
        pi, created = self._ensure_sim(actor)

        if options["order"]:
            self._print_qr(options["order"])
            return
        if options["test_order"]:
            self._queue_test_order(pi, actor)
            return

        token = fleet.rotate_token(pi, actor=actor)
        if options["env"]:
            self.stdout.write(f"NAVI_SIM_PI_ID={pi.pk}")
            self.stdout.write(f"NAVI_DEVICE_TOKEN={token}")
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"{'Created' if created else 'Reusing'} simulator Pi "
                f"'{pi.name}' on NaviPort '{SIM_PORT_NAME}'."
            )
        )
        self.stdout.write("")
        self.stdout.write("New device token (set NAVI_DEVICE_TOKEN to this):")
        self.stdout.write(self.style.WARNING(token))

    def _ensure_sim(self, actor):
        pi, created = RaspberryPi.objects.get_or_create(
            mac_address=SIM_PI_MAC,
            defaults={
                "name": SIM_PI_NAME,
                "location": "Local simulator",
                "is_simulated": True,
                "created_by": actor,
                "updated_by": actor,
            },
        )
        # Machine auth requires the enabled flag.
        if not pi.is_connected or not pi.is_simulated:
            pi.is_connected = True
            pi.is_simulated = True
            pi.save(update_fields=["is_connected", "is_simulated"])

        port, _ = NaviPort.objects.get_or_create(
            name=SIM_PORT_NAME,
            defaults={
                "raspberry_pi": pi,
                # AddressModel.save() requires (truthy) coordinates; any real
                # spot works for a sim.
                "latitude": Decimal("40.712800"),
                "longitude": Decimal("-74.006000"),
                "created_by": actor,
                "updated_by": actor,
            },
        )
        fleet.attach_navi_port(pi, port, actor=actor)
        return pi, created

    def _queue_test_order(self, pi, actor):
        try:
            order = create_test_order(device=pi, actor=actor)
        except DeviceNotReadyError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(f"Queued test order {order.id}. QR token:")
        self.stdout.write(self.style.WARNING(make_qr_token(order)))

    def _print_qr(self, order_id):
        try:
            order = Order.objects.get(pk=order_id)
        except Order.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"Order {order_id} not found."))
            return
        self.stdout.write("")
        self.stdout.write(
            f"QR token for order {order.id} (status {order.order_status}):"
        )
        self.stdout.write(self.style.WARNING(make_qr_token(order)))

    def _system_user(self):
        actor = User.objects.filter(is_superuser=True).order_by("date_joined").first()
        if actor:
            return actor
        return User.objects.create_superuser(
            email="sim-pi@navi.local",
            password=None,
        )
