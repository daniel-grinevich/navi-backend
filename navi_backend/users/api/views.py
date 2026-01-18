import uuid

from django.contrib.auth import get_user_model
from rest_framework import permissions
from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import UserSerializer

User = get_user_model()


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer

    def get_permissions(self):
        if self.action == "me":
            return [permissions.IsAuthenticated()]
        if self.action == "by_email":
            return [permissions.AllowAny()]
        return [permissions.IsAdminUser()]

    @action(detail=False)
    def me(self, request):
        serializer = UserSerializer(request.user, context={"request": request})
        return Response(status=status.HTTP_200_OK, data=serializer.data)

    @action(detail=False, methods=["get"], url_path="by-email")
    def by_email(self, request):
        email = request.query_params.get("email")
        if not email:
            return Response({"error": "Email required"}, status=400)

        user = User.objects.filter(email=email).first()
        if not user:
            return Response({"exists": False}, status=200)

        serializer = UserSerializer(user, context={"request": request})
        return Response(serializer.data)


class SignupView(APIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = UserSerializer

    def post(self, request):
        serializer = UserSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(status=status.HTTP_201_CREATED, data=serializer.data)
        return Response(status=status.HTTP_400_BAD_REQUEST, data=serializer.errors)


class CreateGuestView(APIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = UserSerializer

    def post(self, request):
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
        if created:
            user.set_password(uuid.uuid4().hex)
            user.save()

        refresh = RefreshToken.for_user(user)

        return Response(
            status=status.HTTP_201_CREATED,
            data={
                "user": UserSerializer(user).data,
                "accessToken": str(refresh.access_token),
                "refreshToken": str(refresh),
            },
        )
