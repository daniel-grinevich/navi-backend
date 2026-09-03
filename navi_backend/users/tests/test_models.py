from navi_backend.users.models import User  # noqa: TC001


def test_user_get_absolute_url(user: User):
    assert user.get_absolute_url() == f"/api/users/{user.pk}/"
