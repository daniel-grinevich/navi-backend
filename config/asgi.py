"""
ASGI config for Navi Backend project.
"""

import os
import sys
from pathlib import Path

from channels.routing import ProtocolTypeRouter
from channels.routing import URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

BASE_DIR = Path(__file__).resolve(strict=True).parent.parent
sys.path.append(str(BASE_DIR / "navi_backend"))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

# get_asgi_application() must be called before any imports that touch the ORM
django_asgi_app = get_asgi_application()

from config.routing import websocket_urlpatterns  # noqa: E402
from navi_backend.core.ws_middleware import JWTCookieAuthMiddlewareStack  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(
            JWTCookieAuthMiddlewareStack(URLRouter(websocket_urlpatterns))
        ),
    }
)
