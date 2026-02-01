class ShowOnlyToAdminFieldsMixin:
    show_only_to_admin_fields = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        request = self.context.get("request")
        request_user = getattr(request, "user", None)

        if not (request_user and request_user.is_staff):
            for field in self.show_only_to_admin_fields:
                self.fields.pop(field, None)
