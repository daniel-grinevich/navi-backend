import random

from django.core.management.base import BaseCommand
from django.db import transaction

from navi_backend.devices.models import EspressoMachine
from navi_backend.devices.models import MachineType
from navi_backend.devices.models import NaviPort
from navi_backend.devices.models import RaspberryPi
from navi_backend.devices.tests.factories import EspressoMachineFactory
from navi_backend.devices.tests.factories import NaviPortFactory
from navi_backend.devices.tests.factories import RaspberryPiFactory
from navi_backend.menu.models import Category
from navi_backend.menu.models import Customization
from navi_backend.menu.models import CustomizationGroup
from navi_backend.menu.models import Ingredient
from navi_backend.menu.models import MenuItem
from navi_backend.menu.models import MenuItemIngredient
from navi_backend.menu.tests.factories import CategoryFactory
from navi_backend.menu.tests.factories import CustomizationFactory
from navi_backend.menu.tests.factories import CustomizationGroupFactory
from navi_backend.menu.tests.factories import IngredientFactory
from navi_backend.menu.tests.factories import MenuItemFactory
from navi_backend.menu.tests.factories import MenuItemIngredientFactory


class Command(BaseCommand):
    help = "seeds local db with temp data for testing"

    def handle(self, *args, **kwargs):  # noqa: C901
        with transaction.atomic():
            # Clear existing data
            self.stdout.write("Clearing existing data...")
            MenuItemIngredient.objects.all().delete()
            Customization.objects.all().delete()
            CustomizationGroup.objects.all().delete()
            MenuItem.objects.all().delete()
            Ingredient.objects.all().delete()
            Category.objects.all().delete()
            NaviPort.objects.all().delete()
            EspressoMachine.objects.all().delete()
            MachineType.objects.all().delete()
            RaspberryPi.objects.all().delete()
            self.stdout.write(self.style.SUCCESS("✅ Cleared existing data!"))
            espresso_machines = []
            pis = []
            for _ in range(3):
                espresso_machine = EspressoMachineFactory.create()
                espresso_machines.append(espresso_machine)

                pi = RaspberryPiFactory.create()
                pis.append(pi)

            for espresso_machine, pi in zip(espresso_machines, pis, strict=False):
                NaviPortFactory.create(
                    espresso_machine=espresso_machine, raspberry_pi=pi
                )

            categories = []
            ingredients = []
            for _ in range(30):
                ingredient = IngredientFactory.create()
                ingredients.append(ingredient)

            for _ in range(5):
                category = CategoryFactory.create()
                categories.append(category)

            for category in categories:
                for _ in range(5):
                    menu_item = MenuItemFactory.create(category=category)

                    rand = random.randint(1, 4)  # noqa: S311
                    for _ in range(rand):
                        i = random.choice(ingredients)  # noqa: S311
                        MenuItemIngredientFactory.create(
                            ingredient=i, menu_item=menu_item
                        )

            self.stdout.write(self.style.SUCCESS("✅ Part 1 Seed Complete!"))
            for category in categories:
                for _ in range(3):
                    customization_group = CustomizationGroupFactory.create(
                        category=[category]
                    )

                    rand = random.randint(1, 10)  # noqa: S311
                    for _ in range(rand):
                        CustomizationFactory.create(group=customization_group)

        self.stdout.write(self.style.SUCCESS("✅ Seed complete!"))
