from rest_framework import serializers


class ReadOnlyAuditMixin:
    read_only_fields = ("slug", "created_at", "updated_at", "created_by", "updated_by")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.read_only_fields:
            if field in self.fields:
                self.fields[field].read_only = True


class ShowOnlyToAdminFieldsMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if not hasattr(self, "show_only_to_admin_fields"):
            return

        context = kwargs.get("context", {})
        request = context.get("request")

        if request and hasattr(request, "user"):
            if not (request.user and request.user.is_staff):
                for field in self.show_only_to_admin_fields:
                    self.fields.pop(field, None)


class BaseModelSerializer(
    ShowOnlyToAdminFieldsMixin, ReadOnlyAuditMixin, serializers.ModelSerializer
):
    class Meta:
        abstract = True


class BaseSerializer(serializers.Serializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
