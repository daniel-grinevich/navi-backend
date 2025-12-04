from django.contrib import admin

from .models import NaviPort
from .models import RaspberryPi
from .models import EspressoMachine
from .models import MachineType

admin.site.register(NaviPort)
admin.site.register(RaspberryPi)
admin.site.register(EspressoMachine)
admin.site.register(MachineType)