from django.urls import path

# from .views import user_detail_view
# from .views import user_redirect_view
from .views import welcome_view

app_name = "fakeapi"

urlpatterns = [
    # path("~redirect/", view=user_redirect_view, name="rediarect"),
    # path("~update/", view=user_update_view, name="update"),
    # path("<int:pk>/", view=user_detail_view, name="detail"),
    path("welcome", view=welcome_view, name="welcome"),
]
