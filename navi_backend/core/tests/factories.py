import factory
from factory import Faker
import random
from django.utils import timezone
from django.utils.text import slugify
from navi_backend.users.tests.factories import UserFactory


class AuditFactory(factory.Factory):
    """Base factory for AuditModel."""

    is_deleted = False
    deleted_at = None
    last_modified_ip = factory.Faker("ipv4")
    last_modified_user_agent = factory.Faker("user_agent")

    class Meta:
        abstract = True


class SlugifiedFactory(factory.Factory):
    """Base factory for SlugifiedModel."""

    name = factory.Sequence(lambda n: "Name %03d" % n)
    slug = factory.Sequence(lambda n: "123-555-%04d" % n)

    class Meta:
        abstract = True


class StatusFactory(factory.Factory):
    """Base factory for StatusModel."""

    status = factory.Faker("random_element", elements=["A", "I", "D", "R"])

    class Meta:
        abstract = True


class UpdateRecordFactory(factory.Factory):
    """Base factory for UpdateRecordModel."""

    created_at = factory.LazyFunction(timezone.now)
    updated_at = factory.LazyFunction(timezone.now)
    created_by = factory.SubFactory(UserFactory)
    updated_by = factory.SubFactory(UserFactory)

    class Meta:
        abstract = True
