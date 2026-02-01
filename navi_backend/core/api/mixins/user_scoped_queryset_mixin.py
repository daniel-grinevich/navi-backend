class UserScopedQuerySetMixin:
    user_field = "user"

    def get_queryset(self):
        if hasattr(self, "queryset") and self.queryset is not None:
            qs = self.queryset.all()
        else:
            qs = self.serializer_class.Meta.model.objects.all()

        if self.request.user.is_staff:
            return qs
        if self.request.user.is_authenticated:
            return qs.filter(**{self.user_field: self.request.user})
        return qs.none()
