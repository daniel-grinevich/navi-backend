import contextlib
import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.middleware.csrf import get_token
from django.middleware.csrf import rotate_token
from rest_framework import permissions
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.views import TokenRefreshView

from navi_backend.core.api import BaseModelViewSet
from navi_backend.core.permissions import IsOwner
from navi_backend.users.jwt import delete_token_cookies
from navi_backend.users.jwt import set_token_cookies

from .serializers import UserSerializer

User = get_user_model()


class UserViewSet(BaseModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer

    action_permissions = {
        "default": [IsOwner, IsAuthenticated],
    }

    def get_queryset(self):
        request_user_id = getattr(self.request.user, "id", None)

        if request_user_id is None:
            error_txt = "No request user id set."
            raise ValueError(error_txt)

        self.queryset = User.objects.filter(id=request_user_id)
        return super().get_queryset()

    @action(detail=False)
    def me(self, request):
        serializer = self.get_serializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)


class SignupView(APIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = UserSerializer
    throttle_scope = "auth-signup"

    def post(self, request):
        serializer = UserSerializer(data=request.data, context={"request": request})
        if serializer.is_valid():
            serializer.save()
            return Response(status=status.HTTP_201_CREATED, data=serializer.data)
        return Response(status=status.HTTP_400_BAD_REQUEST, data=serializer.errors)


class LoginView(TokenObtainPairView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth-login"

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        access_token = response.data["access"]
        refresh_token = response.data["refresh"]
        response.data = {}

        set_token_cookies(response, str(access_token), str(refresh_token))
        rotate_token(request)

        return response


class RefreshTokenAPIView(TokenRefreshView):
    throttle_scope = "auth-refresh"

    def post(self, request, *args, **kwargs):
        try:
            serializer = self.get_serializer(
                data={"refresh": self.get_refresh_token_from_cookie()}
            )
            serializer.is_valid(raise_exception=True)
        except TokenError as e:
            raise InvalidToken(e.args[0]) from e

        response = Response({}, status=status.HTTP_200_OK)

        # Set auth cookies
        access_token = serializer.validated_data.get("access")
        refresh_token = serializer.validated_data.get("refresh")
        set_token_cookies(response, access_token, refresh_token)

        return response

    def get_refresh_token_from_cookie(self):
        refresh = self.request.COOKIES.get(settings.SIMPLE_JWT["AUTH_COOKIE_REFRESH"])
        if not refresh:
            raise PermissionDenied

        return refresh


class LogoutAPIView(APIView):
    # No auth/permissions: logout must still work with an expired access
    # token, and it only ever clears the caller's own cookies.
    authentication_classes = ()
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        refresh = request.COOKIES.get(settings.SIMPLE_JWT["AUTH_COOKIE_REFRESH"])
        if refresh:
            # An expired or already-blacklisted token still gets its cookies
            # cleared below.
            with contextlib.suppress(TokenError):
                RefreshToken(refresh).blacklist()

        response = Response({}, status=status.HTTP_200_OK)
        delete_token_cookies(response)
        return response


class CSRFAPIView(APIView):
    permission_classes = ()
    authentication_classes = ()

    def get(self, request):
        return Response({"token": get_token(request)})


class CreateGuestView(APIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = UserSerializer
    throttle_scope = "auth-guest"

    def post(self, request, *args, **kwargs):
        guest_email = request.data.get("guestUser")

        if not guest_email or not isinstance(guest_email, str):
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data="Guest email needs to be passed in as type string",
            )

        user, created = User.objects.get_or_create(
            email=guest_email,
            defaults={
                "is_guest": True,
            },
        )
        if not created:
            # Never hand out a session for an existing account: knowing an
            # email must not be enough to take over its orders/history.
            return Response(status=status.HTTP_200_OK, data={"redirect": "login"})

        user.set_password(str(uuid.uuid4()))
        user.save()

        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        response = Response({}, status=status.HTTP_201_CREATED)
        set_token_cookies(response, access_token, refresh_token)
        rotate_token(request)

        return response
