"""Register (or refresh) a simulator Raspberry Pi for local development.

Creates a RaspberryPi + a NaviPort linked to it, marks it connected, and prints
the device token you feed to the `pi` container via NAVI_DEVICE_TOKEN. Optionally
prints the signed QR token for an order so you can paste it into the Pi UI's
scan box (standing in for the customer's phone QR).

    python manage.py register_sim_pi
    python manage.py register_sim_pi --order <order_id>
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from navi_backend.devices.models import NaviPort
from navi_backend.devices.models import RaspberryPi
from navi_backend.orders.models import Order
from navi_backend.orders.qr import make_qr_token

SIM_PI_NAME = "Simulator Pi"
SIM_PI_MAC = "00:00:00:00:00:01"
SIM_PORT_NAME = "Simulator NaviPort"

User = get_user_model()


class Command(BaseCommand):
    help = "Register a simulator Raspberry Pi + NaviPort for local development."

    def add_arguments(self, parser):
        parser.add_argument(
            "--order",
            help="Print the signed QR token for this order id.",
        )

    def handle(self, *args, **options):
        actor = self._system_user()

        pi, created = RaspberryPi.objects.get_or_create(
            mac_address=SIM_PI_MAC,
            defaults={
                "name": SIM_PI_NAME,
                "created_by": actor,
                "updated_by": actor,
            },
        )
        # Ensure it's connected (IsMachineAuthenticated requires is_connected).
        if not pi.is_connected:
            pi.is_connected = True
            pi.save(update_fields=["is_connected"])

        port, _ = NaviPort.objects.get_or_create(
            name=SIM_PORT_NAME,
            defaults={
                "raspberry_pi": pi,
                "created_by": actor,
                "updated_by": actor,
            },
        )
        if port.raspberry_pi_id != pi.id:
            port.raspberry_pi = pi
            port.save(update_fields=["raspberry_pi"])

        self.stdout.write(
            self.style.SUCCESS(
                f"{'Created' if created else 'Reusing'} simulator Pi "
                f"'{pi.name}' on NaviPort '{port.name}'."
            )
        )
        self.stdout.write("")
        self.stdout.write("Device token (set NAVI_DEVICE_TOKEN to this):")
        self.stdout.write(self.style.WARNING(pi.device_token))

        order_id = options.get("order")
        if order_id:
            self._print_qr(order_id)

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
        self.stdout.write(self.style.WARNING(make_qr_token(order.id)))

    def _system_user(self):
        actor = User.objects.filter(is_superuser=True).order_by("date_joined").first()
        if actor:
            return actor
        return User.objects.create_superuser(
            email="sim-pi@navi.local",
            password=None,
        )
