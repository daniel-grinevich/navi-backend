from rest_framework import serializers

from navi_backend.users.models import User


class UserSerializer(serializers.ModelSerializer[User]):
    class Meta:
        model = User
        fields = ["name", "email", "url"]

        extra_kwargs = {
            "url": {"view_name": "users-detail", "lookup_field": "pk"},
        }
