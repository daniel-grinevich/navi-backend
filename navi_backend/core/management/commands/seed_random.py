"""Seed the local database with a large, realistic demo dataset.

Creates a curated coffee menu, a handful of physical NaviPort locations, a big
pool of customers, and a rich order history (orders + items + customizations +
payments + invoices) spread over the last few months.

Usage::

    python manage.py seed_random                 # 1,000 users, 5,000 orders
    python manage.py seed_random --users 2000 --orders 15000
    python manage.py seed_random --no-clear      # add on top of existing data
    python manage.py seed_random --seed 42       # reproducible run

Everything is created with bulk_create for speed, which intentionally bypasses
model save() hooks and signals (so we don't spam the Celery email queue or pay
the per-row password-hashing / geocoding costs). Because of that we set every
derived field (slug, unit_price, device_token, ...) explicitly.
"""

from __future__ import annotations

import random
import secrets
import uuid
from collections import Counter
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from navi_backend.devices.models import EspressoMachine
from navi_backend.devices.models import MachineType
from navi_backend.devices.models import NaviPort
from navi_backend.devices.models import RaspberryPi
from navi_backend.menu.models import Category
from navi_backend.menu.models import Customization
from navi_backend.menu.models import CustomizationGroup
from navi_backend.menu.models import Ingredient
from navi_backend.menu.models import MenuItem
from navi_backend.menu.models import MenuItemIngredient
from navi_backend.orders.models import MachineErrorLog
from navi_backend.orders.models import Order
from navi_backend.orders.models import OrderCustomization
from navi_backend.orders.models import OrderItem
from navi_backend.orders.models import Status as OrderStatus
from navi_backend.payments.models import Invoice
from navi_backend.payments.models import Payment
from navi_backend.users.models import User

try:
    from faker import Faker
except ImportError:  # pragma: no cover - faker ships with factory-boy
    Faker = None

# ---------------------------------------------------------------------------
# Static, curated catalog data. Prices/descriptions are hand-written so the
# local menu reads like a real coffee shop rather than lorem-ipsum noise.
# ---------------------------------------------------------------------------

DEMO_PASSWORD = "navi1234"  # every seeded user shares this password  # noqa: S105

# category name -> list of (menu item name, price, short description)
MENU = {
    "Espresso Drinks": [
        ("Espresso", "3.00", "A rich, concentrated single shot."),
        ("Doppio", "3.50", "Two shots of pure espresso."),
        ("Americano", "3.75", "Espresso cut with hot water."),
        ("Latte", "4.75", "Espresso with steamed milk and light foam."),
        ("Cappuccino", "4.50", "Equal parts espresso, steamed milk, and foam."),
        ("Flat White", "4.75", "Ristretto shots with velvety microfoam."),
        ("Cortado", "4.25", "Espresso balanced with a splash of warm milk."),
        ("Macchiato", "3.75", "Espresso marked with a dollop of foam."),
        ("Mocha", "5.25", "Espresso, steamed milk, and rich chocolate."),
        ("Cortado Ristretto", "4.50", "Short, sweet shots with a touch of milk."),
    ],
    "Cold Brew & Iced Coffee": [
        ("Cold Brew", "4.50", "Slow-steeped for 18 hours, smooth and bold."),
        ("Nitro Cold Brew", "5.25", "Cold brew on nitro for a creamy cascade."),
        ("Iced Americano", "3.95", "Espresso over ice and cold water."),
        ("Iced Latte", "4.95", "Chilled espresso and milk over ice."),
        ("Iced Mocha", "5.45", "Iced espresso, milk, and chocolate."),
        ("Vanilla Cold Brew", "5.25", "Cold brew with sweet vanilla cream."),
    ],
    "Specialty Lattes": [
        ("Vanilla Latte", "5.25", "House latte with Madagascar vanilla."),
        ("Caramel Latte", "5.25", "Buttery caramel folded into steamed milk."),
        ("Hazelnut Latte", "5.25", "Toasted hazelnut and espresso."),
        ("Pumpkin Spice Latte", "5.75", "Seasonal spices, espresso, and cream."),
        ("Lavender Latte", "5.50", "Floral lavender with a clean espresso finish."),
        ("White Chocolate Mocha", "5.75", "White chocolate, espresso, and milk."),
        ("Caramel Macchiato", "5.50", "Vanilla, milk, espresso, and caramel drizzle."),
    ],
    "Drip Coffee": [
        ("House Drip", "2.75", "Our daily rotating single-origin drip."),
        ("Pour Over", "4.75", "Hand-poured, brewed to order."),
        ("French Press", "4.25", "Full-bodied and pressed at the bar."),
        ("Vietnamese Coffee", "4.95", "Strong drip over sweetened condensed milk."),
        ("Turkish Coffee", "4.50", "Finely ground and simmered, unfiltered."),
    ],
    "Tea & Chai": [
        ("Chai Latte", "4.75", "Spiced black tea with steamed milk."),
        ("Matcha Latte", "5.25", "Stone-ground matcha with steamed milk."),
        ("London Fog", "4.75", "Earl grey, vanilla, and steamed milk."),
        ("Hibiscus Iced Tea", "3.95", "Tart, bright, and refreshing over ice."),
        ("Green Tea", "3.25", "Delicate steeped sencha."),
    ],
}

FEATURED_ITEMS = {
    "Latte",
    "Nitro Cold Brew",
    "Caramel Macchiato",
    "Pumpkin Spice Latte",
    "Cold Brew",
    "Matcha Latte",
}

# ingredient name -> is_allergen
INGREDIENTS = {
    "Espresso Shot": False,
    "Whole Milk": True,
    "2% Milk": True,
    "Oat Milk": False,
    "Almond Milk": True,
    "Coconut Milk": False,
    "Soy Milk": True,
    "Heavy Cream": True,
    "Half & Half": True,
    "Steamed Milk": True,
    "Milk Foam": True,
    "Whipped Cream": True,
    "Vanilla Syrup": False,
    "Caramel Syrup": False,
    "Hazelnut Syrup": True,
    "Lavender Syrup": False,
    "Mocha Sauce": False,
    "White Chocolate Sauce": True,
    "Caramel Drizzle": False,
    "Chocolate Drizzle": False,
    "Sugar": False,
    "Honey": False,
    "Cinnamon": False,
    "Cocoa Powder": False,
    "Pumpkin Spice Mix": False,
    "Chai Concentrate": False,
    "Cold Brew Concentrate": False,
    "Ice": False,
    "Hot Water": False,
    "Matcha Powder": False,
}

INGREDIENT_UNITS = ["oz", "ml", "pump", "shot", "packet", "tsp", "dash"]

# customization group -> (applies to these categories, [(name, price), ...])
CUSTOMIZATION_GROUPS = {
    "Milk Options": (
        [
            "Espresso Drinks",
            "Cold Brew & Iced Coffee",
            "Specialty Lattes",
            "Tea & Chai",
        ],
        [
            ("Whole Milk", "0.00"),
            ("2% Milk", "0.00"),
            ("Oat Milk", "0.75"),
            ("Almond Milk", "0.75"),
            ("Coconut Milk", "0.75"),
            ("Soy Milk", "0.65"),
            ("Heavy Cream", "0.50"),
            ("Half & Half", "0.50"),
            ("No Milk", "0.00"),
        ],
    ),
    "Size": (
        [
            "Espresso Drinks",
            "Cold Brew & Iced Coffee",
            "Specialty Lattes",
            "Drip Coffee",
            "Tea & Chai",
        ],
        [
            ("Small (12oz)", "0.00"),
            ("Medium (16oz)", "0.60"),
            ("Large (20oz)", "1.10"),
            ("Extra Large (24oz)", "1.60"),
        ],
    ),
    "Sweeteners": (
        [
            "Espresso Drinks",
            "Cold Brew & Iced Coffee",
            "Specialty Lattes",
            "Drip Coffee",
            "Tea & Chai",
        ],
        [
            ("Sugar (1 packet)", "0.00"),
            ("Sugar (2 packets)", "0.00"),
            ("Honey", "0.35"),
            ("Stevia", "0.00"),
            ("Agave", "0.35"),
            ("No Sweetener", "0.00"),
        ],
    ),
    "Espresso Shots": (
        ["Espresso Drinks", "Cold Brew & Iced Coffee", "Specialty Lattes"],
        [
            ("Single Shot", "0.00"),
            ("Double Shot", "0.90"),
            ("Triple Shot", "1.80"),
            ("Decaf Shot", "0.00"),
            ("Half-Caf", "0.00"),
        ],
    ),
    "Toppings": (
        ["Espresso Drinks", "Specialty Lattes"],
        [
            ("Whipped Cream", "0.50"),
            ("Caramel Drizzle", "0.50"),
            ("Chocolate Drizzle", "0.50"),
            ("Cinnamon Powder", "0.25"),
            ("Cocoa Powder", "0.25"),
        ],
    ),
    "Flavor Shots": (
        [
            "Espresso Drinks",
            "Cold Brew & Iced Coffee",
            "Specialty Lattes",
            "Tea & Chai",
        ],
        [
            ("Vanilla", "0.75"),
            ("Caramel", "0.75"),
            ("Hazelnut", "0.75"),
            ("Mocha", "0.75"),
            ("White Chocolate", "0.75"),
            ("Pumpkin Spice", "0.75"),
            ("Lavender", "0.75"),
            ("Peppermint", "0.75"),
        ],
    ),
    "Temperature": (
        [
            "Espresso Drinks",
            "Cold Brew & Iced Coffee",
            "Specialty Lattes",
            "Tea & Chai",
        ],
        [
            ("Extra Hot", "0.00"),
            ("Hot", "0.00"),
            ("Iced", "0.00"),
            ("Blended", "0.75"),
        ],
    ),
}

# NaviPort demo locations: (name, city, state, postal, lat, long)
LOCATIONS = [
    (
        "Navi Downtown",
        "525 Market St",
        "San Francisco",
        "CA",
        "94105",
        "37.789624",
        "-122.400714",
    ),
    (
        "Navi Mission",
        "2801 Mission St",
        "San Francisco",
        "CA",
        "94110",
        "37.751976",
        "-122.418557",
    ),
    (
        "Navi SoMa",
        "845 Folsom St",
        "San Francisco",
        "CA",
        "94107",
        "37.782560",
        "-122.402100",
    ),
    (
        "Navi Berkeley",
        "2118 Shattuck Ave",
        "Berkeley",
        "CA",
        "94704",
        "37.870200",
        "-122.268300",
    ),
    (
        "Navi Palo Alto",
        "429 University Ave",
        "Palo Alto",
        "CA",
        "94301",
        "37.447700",
        "-122.160600",
    ),
    (
        "Navi Oakland",
        "1440 Broadway",
        "Oakland",
        "CA",
        "94612",
        "37.804400",
        "-122.271100",
    ),
    (
        "Navi San Jose",
        "150 S 1st St",
        "San Jose",
        "CA",
        "95113",
        "37.334900",
        "-121.888700",
    ),
    (
        "Navi Santa Clara",
        "2788 El Camino Real",
        "Santa Clara",
        "CA",
        "95051",
        "37.352200",
        "-121.955200",
    ),
]

# order status -> (weight, payment status)
ORDER_STATUS_PLAN = {
    OrderStatus.DONE: (70, "succeeded"),
    OrderStatus.CANCELLED: (12, "canceled"),
    OrderStatus.SENT: (8, "requires_capture"),
    OrderStatus.ORDERED: (10, "requires_capture"),
}

SEED_DAYS = 120  # spread history over the last ~4 months


class Command(BaseCommand):
    help = "Seed the local db with a large, realistic demo dataset."

    def add_arguments(self, parser):
        parser.add_argument(
            "--users", type=int, default=1000, help="Number of customers to create."
        )
        parser.add_argument(
            "--orders", type=int, default=5000, help="Number of orders to create."
        )
        parser.add_argument(
            "--no-clear",
            action="store_true",
            help="Append to existing data instead of wiping it first.",
        )
        parser.add_argument(
            "--seed", type=int, default=None, help="Random seed for reproducible runs."
        )

    def handle(self, *args, **options):
        if Faker is None:
            self.stderr.write(
                self.style.ERROR("Faker is required. Install requirements/local.txt.")
            )
            return

        if options["seed"] is not None:
            random.seed(options["seed"])
            self.fake = Faker()
            self.fake.seed_instance(options["seed"])
        else:
            self.fake = Faker()

        n_users = options["users"]
        n_orders = options["orders"]
        self.now = timezone.now()

        with transaction.atomic():
            if not options["no_clear"]:
                self._clear()

            admin, users = self._seed_users(n_users)
            categories = self._seed_menu(admin)
            self._seed_devices(admin)
            self._seed_orders(users, categories, n_orders)

        self._print_summary(n_users)

    # ------------------------------------------------------------------ clear
    def _clear(self):
        self.stdout.write("Clearing existing data...")
        # child -> parent order so FKs never block a delete
        for model in (
            OrderCustomization,
            OrderItem,
            MachineErrorLog,
            Invoice,
            Order,
            Payment,
            MenuItemIngredient,
            Customization,
            CustomizationGroup,
            MenuItem,
            Ingredient,
            Category,
            NaviPort,
            EspressoMachine,
            MachineType,
            RaspberryPi,
        ):
            model.objects.all().delete()
        # created_by is CASCADE, so users go last to avoid nuking rows early
        User.objects.all().delete()
        self.stdout.write(self.style.SUCCESS("✅ Cleared existing data"))

    # ------------------------------------------------------------------ users
    def _seed_users(self, n_users):
        self.stdout.write(f"Creating {n_users} users...")
        password_hash = make_password(DEMO_PASSWORD)

        # A few well-known logins so the local app is easy to poke at.
        known = [
            ("admin@navi.test", "Ada Admin", True, True),
            ("barista@navi.test", "Bea Barista", True, False),
            ("demo@navi.test", "Dee Demo", False, False),
        ]
        users = []
        for email, name, is_staff, is_super in known:
            users.append(
                User(
                    email=email,
                    name=name,
                    password=password_hash,
                    is_staff=is_staff,
                    is_superuser=is_super,
                    is_active=True,
                    email_confirmed=True,
                    stripe_customer_id=f"cus_{uuid.uuid4().hex[:14]}",
                    date_joined=self.now - timedelta(days=SEED_DAYS),
                )
            )

        seen_emails = {u.email for u in users}
        for i in range(max(0, n_users - len(known))):
            name = self.fake.name()
            handle = name.lower().replace(".", "").replace("'", "").replace(" ", ".")
            email = f"{handle}.{i}@example.com"
            if email in seen_emails:
                email = f"{handle}.{i}.{uuid.uuid4().hex[:6]}@example.com"
            seen_emails.add(email)

            is_guest = random.random() < 0.15
            confirmed = (not is_guest) and random.random() < 0.9
            joined = self.now - timedelta(
                days=random.randint(0, SEED_DAYS),
                hours=random.randint(0, 23),
            )
            users.append(
                User(
                    email=email,
                    name=name,
                    password=password_hash,
                    is_active=True,
                    is_guest=is_guest,
                    email_confirmed=confirmed,
                    stripe_customer_id=(
                        f"cus_{uuid.uuid4().hex[:14]}" if confirmed else None
                    ),
                    date_joined=joined,
                    last_login=(
                        joined + timedelta(days=random.randint(0, 30))
                        if random.random() < 0.6
                        else None
                    ),
                )
            )

        User.objects.bulk_create(users, batch_size=1000)
        # Re-fetch to guarantee every instance carries a PK for downstream FKs.
        users = list(User.objects.all())
        admin = next(u for u in users if u.email == "admin@navi.test")
        self.stdout.write(self.style.SUCCESS(f"✅ Created {len(users)} users"))
        return admin, users

    # ------------------------------------------------------------------- menu
    def _seed_menu(self, admin):
        self.stdout.write("Building coffee menu...")
        audit = {"created_by": admin, "updated_by": admin}

        categories = {}
        for name in MENU:
            categories[name] = Category.objects.create(name=name, **audit)

        ingredients = {}
        for name, is_allergen in INGREDIENTS.items():
            ingredients[name] = Ingredient.objects.create(
                name=name,
                is_allergen=is_allergen,
                description=self.fake.sentence(nb_words=8),
                **audit,
            )

        ingredient_pool = list(ingredients.values())
        menu_items = []
        for category_name, items in MENU.items():
            category = categories[category_name]
            for name, price, description in items:
                item = MenuItem.objects.create(
                    name=name,
                    price=Decimal(price),
                    description=description,
                    body=self._menu_body(name, description),
                    category=category,
                    is_featured=name in FEATURED_ITEMS,
                    **audit,
                )
                menu_items.append(item)

                # 2-4 realistic ingredients per drink
                chosen = random.sample(
                    ingredient_pool,
                    random.randint(2, 4),
                )
                MenuItemIngredient.objects.bulk_create(
                    [
                        MenuItemIngredient(
                            menu_item=item,
                            ingredient=ing,
                            quantity=Decimal(str(round(random.uniform(0.5, 6.0), 2))),
                            unit=random.choice(INGREDIENT_UNITS),
                        )
                        for ing in chosen
                    ]
                )

        # Customization groups + customizations, wired to their categories.
        for group_name, (cat_names, options) in CUSTOMIZATION_GROUPS.items():
            group = CustomizationGroup.objects.create(
                name=group_name,
                description=self.fake.sentence(nb_words=6),
                display_order=random.randint(1, 10),
                is_required=group_name in {"Size", "Milk Options"},
                allow_multiple=group_name in {"Flavor Shots", "Toppings"},
                **audit,
            )
            group.category.set([categories[c] for c in cat_names])
            for order_idx, (opt_name, opt_price) in enumerate(options):
                Customization.objects.create(
                    name=opt_name,
                    description=self.fake.sentence(nb_words=5),
                    display_order=order_idx,
                    price=Decimal(opt_price),
                    group=group,
                    **audit,
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"✅ Menu: {len(categories)} categories, {len(menu_items)} drinks, "
                f"{Customization.objects.count()} customizations"
            )
        )
        return categories

    def _menu_body(self, name, description):
        return (
            f"{description} Our {name} is crafted to order by a Navi barista "
            f"using freshly pulled shots and locally roasted beans."
        )

    # ---------------------------------------------------------------- devices
    def _seed_devices(self, admin):
        self.stdout.write("Provisioning NaviPort locations...")
        audit = {"created_by": admin, "updated_by": admin}
        drinks = list(MenuItem.objects.all())

        machine_types = []
        for i, tname in enumerate(["Eversys Cameo", "Eversys Shotmaster", "Jura Giga"]):
            mt = MachineType.objects.create(
                name=tname,
                model_number=f"MT-{100 + i}",
                maintenance_frequency=random.randint(30, 180),
                **audit,
            )
            mt.supported_drinks.set(random.sample(drinks, min(len(drinks), 20)))
            machine_types.append(mt)

        for i, (name, line1, city, state, postal, lat, lon) in enumerate(LOCATIONS):
            pi = RaspberryPi.objects.create(
                name=f"pi-{name.lower().replace(' ', '-')}",
                mac_address=self.fake.mac_address(),
                ip_address=self.fake.ipv4_private(),
                location=f"{city}, {state}",
                is_connected=random.random() < 0.85,
                firmware_version=f"v{random.randint(1, 4)}.{random.randint(0, 9)}",
                device_token=secrets.token_urlsafe(32),
                **audit,
            )
            machine = EspressoMachine.objects.create(
                name=f"machine-{name.lower().replace(' ', '-')}",
                serial_number=f"EM-{1000 + i}",
                machine_type=random.choice(machine_types),
                ip_address=self.fake.ipv4_private(),
                port=random.randint(3000, 9000),
                is_online=random.random() < 0.85,
                last_maintenance_at=self.now - timedelta(days=random.randint(1, 90)),
                **audit,
            )
            NaviPort.objects.create(
                name=name,
                espresso_machine=machine,
                raspberry_pi=pi,
                latitude=Decimal(lat),
                longitude=Decimal(lon),
                address_line_1=line1,
                city=city,
                state_or_region=state,
                postal_code=postal,
                country="US",
                **audit,
            )

        self.stdout.write(
            self.style.SUCCESS(f"✅ Provisioned {len(LOCATIONS)} NaviPort locations")
        )

    # ----------------------------------------------------------------- orders
    def _seed_orders(self, users, categories, n_orders):
        self.stdout.write(f"Generating {n_orders} orders (this is the big one)...")

        ports = list(NaviPort.objects.all())
        menu_items = list(MenuItem.objects.all())
        # menu item -> customizations valid for its category
        cust_by_category = {}
        for cat in categories.values():
            cust_by_category[cat.id] = list(
                Customization.objects.filter(group__category=cat).distinct()
            )
        # weighted, non-guest customers place most orders
        customers = [u for u in users if not u.is_superuser]

        statuses = list(ORDER_STATUS_PLAN)
        status_weights = [ORDER_STATUS_PLAN[s][0] for s in statuses]

        payments, orders, items, order_custs = [], [], [], []
        error_logs, invoices = [], []
        # parallel backdate lists so bulk_update can fix auto_now_add created_at
        pay_dates, order_dates, item_dates, cust_dates = [], [], [], []
        invoice_ref = Invoice.last_reference_number()
        next_ref = (invoice_ref.reference_number + 1) if invoice_ref else 1

        for _ in range(n_orders):
            user = random.choice(customers)
            port = random.choice(ports)
            status = random.choices(statuses, weights=status_weights)[0]
            pay_status = ORDER_STATUS_PLAN[status][1]
            # a few cancelled orders represent failed payments
            if status == OrderStatus.CANCELLED and random.random() < 0.3:
                pay_status = "failed"
            created = self.now - timedelta(
                days=random.randint(0, SEED_DAYS),
                hours=random.randint(0, 23),
                minutes=random.randint(0, 59),
            )
            audit = {"created_by": user, "updated_by": user}

            payment = Payment(
                stripe_payment_intent_id=f"pi_{uuid.uuid4().hex[:24]}",
                amount_received=Decimal("0.00"),  # set once items are priced
                currency="usd",
                status=pay_status,
                **audit,
            )
            order = Order(
                user=user,
                navi_port=port,
                payment=payment,
                cart_token=uuid.uuid4().hex,
                slug=f"ord-{uuid.uuid4().hex[:16]}",
                order_status=status,
                **audit,
            )

            order_total = Decimal("0.00")
            # 1-4 drinks, skewed toward small orders
            n_items = random.choices([1, 2, 3, 4], weights=[45, 32, 15, 8])[0]
            for menu_item in random.choices(menu_items, k=n_items):
                qty = random.choices([1, 2, 3], weights=[75, 20, 5])[0]
                item = OrderItem(
                    order=order,
                    menu_item=menu_item,
                    quantity=qty,
                    unit_price=menu_item.price,
                    slug=f"oi-{uuid.uuid4().hex[:16]}",
                    **audit,
                )
                items.append(item)
                item_dates.append(created)
                line_total = menu_item.price * qty

                available = cust_by_category.get(
                    menu_item.category_id if menu_item.category_id else None, []
                )
                if available:
                    n_cust = random.choices([0, 1, 2, 3], weights=[30, 40, 20, 10])[0]
                    for cust in random.sample(available, min(n_cust, len(available))):
                        oc = OrderCustomization(
                            order_item=item,
                            customization=cust,
                            quantity=1,
                            unit_price=cust.price,
                            slug=f"oc-{uuid.uuid4().hex[:16]}",
                            **audit,
                        )
                        order_custs.append(oc)
                        cust_dates.append(created)
                        line_total += cust.price
                order_total += line_total

            payment.amount_received = order_total
            payments.append(payment)
            pay_dates.append(created)
            orders.append(order)
            order_dates.append(created)

            # invoice completed & paid orders
            if status == OrderStatus.DONE:
                invoices.append(
                    Invoice(order=order, reference_number=next_ref, **audit)
                )
                next_ref += 1

            # occasional machine hiccup for realism
            if random.random() < 0.015:
                error_logs.append(
                    MachineErrorLog(
                        order=order,
                        raspberry_pi=port.raspberry_pi,
                        error_message=random.choice(
                            [
                                "Grinder jam detected on hopper 2.",
                                "Steam wand pressure below threshold.",
                                "Water reservoir low.",
                                "Milk line temperature out of range.",
                                "Portafilter not seated correctly.",
                            ]
                        ),
                        is_recoverable=random.random() < 0.7,
                        **audit,
                    )
                )

        # Insert in FK dependency order.
        Payment.objects.bulk_create(payments, batch_size=1000)
        Order.objects.bulk_create(orders, batch_size=1000)
        OrderItem.objects.bulk_create(items, batch_size=2000)
        OrderCustomization.objects.bulk_create(order_custs, batch_size=2000)
        Invoice.objects.bulk_create(invoices, batch_size=1000)
        MachineErrorLog.objects.bulk_create(error_logs, batch_size=1000)

        # Backdate created_at (auto_now_add ignored it on insert).
        self._backdate(Payment, payments, pay_dates)
        self._backdate(Order, orders, order_dates)
        self._backdate(OrderItem, items, item_dates)
        self._backdate(OrderCustomization, order_custs, cust_dates)

        self._update_menu_popularity(items)

        self.stdout.write(
            self.style.SUCCESS(
                f"✅ Orders: {len(orders)} orders, {len(items)} items, "
                f"{len(order_custs)} customizations, {len(invoices)} invoices, "
                f"{len(error_logs)} error logs"
            )
        )

    def _backdate(self, model, objs, dates):
        """Push created_at into the past. bulk_update leaves auto_now_add alone."""
        for obj, created in zip(objs, dates, strict=True):
            obj.created_at = created
        model.objects.bulk_update(objs, ["created_at"], batch_size=1000)

    def _update_menu_popularity(self, items):
        counts = Counter(i.menu_item_id for i in items)
        menu_items = list(MenuItem.objects.all())
        for item in menu_items:
            sold = counts.get(item.id, 0)
            item.selected_count = sold
            item.view_count = sold * random.randint(4, 12) + random.randint(0, 50)
        MenuItem.objects.bulk_update(
            menu_items, ["selected_count", "view_count"], batch_size=1000
        )

    # ---------------------------------------------------------------- summary
    def _print_summary(self, n_users):
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("🌱 Seed complete!"))
        self.stdout.write(
            f"   Users: {User.objects.count()}   "
            f"Orders: {Order.objects.count()}   "
            f"Order items: {OrderItem.objects.count()}"
        )
        self.stdout.write("")
        self.stdout.write("   Log in with any seeded account:")
        self.stdout.write(f"     admin@navi.test    / {DEMO_PASSWORD}  (superuser)")
        self.stdout.write(f"     barista@navi.test  / {DEMO_PASSWORD}  (staff)")
        self.stdout.write(f"     demo@navi.test     / {DEMO_PASSWORD}  (customer)")
        self.stdout.write(
            f"   ...and {n_users - 3} more customers, all with password "
            f"'{DEMO_PASSWORD}'."
        )
