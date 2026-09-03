from django.contrib import admin

from .models import EspressoMachine
from .models import MachineType
from .models import NaviPort
from .models import RaspberryPi

admin.site.register(NaviPort)
admin.site.register(RaspberryPi)
admin.site.register(EspressoMachine)
admin.site.register(MachineType)
