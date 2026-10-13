import hashlib
from datetime import timedelta

from django.db import models
from django.db.models import Q
from django.utils import timezone

# A Pi is "online" if it has checked in (HTTP poll or websocket ping) within
# this window. Pis ping every ~15s and poll every ~3-30s, so 60s is generous.
ONLINE_WINDOW_SECONDS = 60


def hash_device_token(token: str) -> str:
    """SHA-256 of a plaintext device token -- the only form we store.

    Tokens are 256-bit random strings, so a fast unsalted hash is enough: there
    is nothing to brute-force, we just don't want a DB leak to hand out
    working credentials.
    """
    return hashlib.sha256(token.encode()).hexdigest()


def online_cutoff():
    return timezone.now() - timedelta(seconds=ONLINE_WINDOW_SECONDS)


class RaspberryPiQuerySet(models.QuerySet):
    def authenticate(self, token: str | None):
        """The enabled Pi that owns ``token``, or None."""
        if not token:
            return None
        return self.filter(
            token_hash=hash_device_token(token), is_connected=True
        ).first()

    def online(self):
        return self.filter(last_seen__gte=online_cutoff())

    def offline(self):
        return self.filter(Q(last_seen__lt=online_cutoff()) | Q(last_seen__isnull=True))

    def search(self, term: str):
        return self.filter(
            Q(name__icontains=term)
            | Q(slug__icontains=term)
            | Q(mac_address__icontains=term)
            | Q(location__icontains=term)
            | Q(navi_port__name__icontains=term)
        ).distinct()


class DeviceEventQuerySet(models.QuerySet):
    def older_than(self, days: int):
        return self.filter(created_at__lt=timezone.now() - timedelta(days=days))
