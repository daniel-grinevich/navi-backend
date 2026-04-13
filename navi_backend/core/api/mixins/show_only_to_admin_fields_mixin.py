class ShowOnlyToAdminFieldsMixin:
    show_only_to_admin_fields = ()
    default_admin_fields = (
        "status",
        "is_deleted",
        "deleted_at",
        "last_modified_ip",
        "last_modified_user_agent",
    )

    def get_field_names(self, declared_fields, info):
        field_names = list(super().get_field_names(declared_fields, info))

        model = self.Meta.model
        model_field_names = {f.name for f in model._meta.get_fields()}  # NOQA: SLF001

        for field_name in self.default_admin_fields:
            if field_name in model_field_names and field_name not in field_names:
                field_names.append(field_name)

        return field_names

    def get_fields(self):
        fields = super().get_fields()

        request = self.context.get("request")
        is_admin = getattr(getattr(request, "user", None), "is_staff", False)

        if not is_admin:
            admin_fields = self.show_only_to_admin_fields + self.default_admin_fields

            for field in admin_fields:
                fields.pop(field, None)

        return fields
