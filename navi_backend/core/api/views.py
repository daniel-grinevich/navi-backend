import hashlib
import json

from django.core.cache import cache
from rest_framework import viewsets
from rest_framework.response import Response


def _stable_params(query_params):
    return tuple(sorted((k, list(v)) for k, v in query_params.lists()))


def _make_key(prefix, payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return f"{prefix}:{hashlib.sha256(raw.encode()).hexdigest()}"


class BaseViewSet(viewsets.GenericViewSet):
    cache_timeout = 60 * 60
    cache_prefix = "api"
    cache_per_user = True
    cache_bypass_query = "refresh"

    def _model_label(self):
        return self.get_queryset().model._meta.label_lower  # noqa: SLF001

    def _user_key(self, request):
        if not self.cache_per_user:
            return None
        return getattr(getattr(request, "user", None), "pk", "anon")

    def _renderer_key(self, request):
        return getattr(request, "accepted_media_type", None)

    def _list_key(self, request):
        payload = {
            "kind": "list",
            "model": self._model_label(),
            "user": self._user_key(request),
            "params": _stable_params(request.query_params),
            "fmt": self._renderer_key(request),
        }
        return _make_key(self.cache_prefix, payload)

    def _detail_key(self, request, pk):
        payload = {
            "kind": "detail",
            "model": self._model_label(),
            "user": self._user_key(request),
            "pk": str(pk),
            "fmt": self._renderer_key(request),
        }
        return _make_key(self.cache_prefix, payload)

    def list(self, request, *args, **kwargs):
        key = self._list_key(request)
        cached = cache.get(key)
        if cached is not None:
            return Response(cached)

        response = super().list(request, *args, **kwargs)
        cache.set(key, response.data, self.cache_timeout)
        return response

    def retrieve(self, request, *args, **kwargs):
        pk = kwargs.get("pk")
        key = self._detail_key(request, pk)
        cached = cache.get(key)
        if cached is not None:
            return Response(cached)

        response = super().retrieve(request, *args, **kwargs)
        cache.set(key, response.data, self.cache_timeout)
        return response
