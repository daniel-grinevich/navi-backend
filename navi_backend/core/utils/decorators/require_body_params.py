from functools import wraps

from rest_framework import status
from rest_framework.response import Response


def require_body_params(*params):
    def decorator(func):
        @wraps(func)
        def wrapper(self, request, *args, **kwargs):
            missing = [p for p in params if p not in request.data]
            if missing:
                return Response(
                    {"detail": f"Missing required fields: {', '.join(missing)}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return func(self, request, *args, **kwargs)

        return wrapper

    return decorator
