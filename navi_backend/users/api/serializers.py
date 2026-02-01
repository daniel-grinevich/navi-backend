from django.contrib.auth import authenticate
from django.contrib.auth import get_user_model
from rest_framework import serializers

from navi_backend.core.api import BaseModelSerializer

User = get_user_model()


class UserSerializer(BaseModelSerializer):
    password = serializers.CharField(
        write_only=True, min_length=8, required=False, allow_null=True
    )
    email = serializers.EmailField()
    is_admin = serializers.SerializerMethodField()

    show_only_to_admin_fields = [
        "name",
        "created_at",
        "password",
        "stripe_customer_id",
        "date_joined",
    ]

    class Meta:
        model = User
        fields = [
            "id",
            "name",
            "email",
            "password",
            "stripe_customer_id",
            "date_joined",
            "is_guest",
            "is_admin",
        ]
        read_only_fields = ["id", "stripe_customer_id", "date_joined"]

    def get_is_admin(self, obj):
        return obj.is_staff or obj.is_superuser

    def validate(self, attrs):
        is_guest = attrs.get("is_guest", False)
        password = attrs.get("password")

        if not is_guest and not password:
            raise serializers.ValidationError(
                {"password": "This field is required for non-guest users."}
            )

        return attrs

    def create(self, validated_data):
        email = validated_data["email"].lower()

        user = User.objects.filter(email=email).first()

        if user:
            if not user.is_guest:
                raise serializers.ValidationError(
                    {"email": "An account with this email already exists."}
                )

            # Upgrade guest user
            user.email = email
            user.is_guest = False
            user.set_password(validated_data["password"])
            user.save()

            return user

        return User.objects.create_user(**validated_data)

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class AuthSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(
        style={"input_type": "password"}, trim_whitespace=False
    )

    def validate(self, attrs):
        email = attrs.get("email")
        password = attrs.get("password")

        user = authenticate(
            request=self.context.get("request"), username=email, password=password
        )

        if not user:
            msg = "Unable to authenticate with provided credentials"
            raise serializers.ValidationError(msg, code="authentication")

        attrs["user"] = user
        return attrs
