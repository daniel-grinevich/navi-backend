from django.core.management.base import BaseCommand
from django.db import transaction

from navi_backend.orders.tests.factories import CategoryFactory
from navi_backend.orders.tests.factories import CustomizationFactory
from navi_backend.orders.tests.factories import CustomizationGroupFactory
from navi_backend.orders.tests.factories import EspressoMachineFactory
from navi_backend.orders.tests.factories import IngredientFactory
from navi_backend.orders.tests.factories import MenuItemFactory
from navi_backend.orders.tests.factories import MenuItemIngredientFactory
from navi_backend.orders.tests.factories import NaviPortFactory
from navi_backend.orders.tests.factories import RasberryPiFactory


class Command(BaseCommand):
    help = "seeds local db with temp data for testing"

    def handle(self, *args, **kwargs):
        # TODO create a transaction that cleans the local db then  new seed data

        with transaction.atomic():
            espresso_machine = EspressoMachineFactory.create()
            pi = RasberryPiFactory.create()

            NaviPortFactory.create(espresso_machine=espresso_machine, rasberry_pi=pi)

            categories = []
            for _ in range(15):
                ingredient = IngredientFactory.create()
                category = CategoryFactory.create()
                categories.append(category)

                menu_item = MenuItemFactory.create(category=category)
                MenuItemIngredientFactory(ingredient=ingredient, menu_item=menu_item)

            self.stdout.write(self.style.SUCCESS("✅ Part 1 Seed Complete!"))
            for category in categories:
                for _ in range(3):
                    customization_group = CustomizationGroupFactory.create(
                        category=[category]
                    )
                    for _ in range(3):
                        CustomizationFactory.create(group=customization_group)

        self.stdout.write(self.style.SUCCESS("✅ Seed complete!"))
