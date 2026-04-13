class PermissionFilterMixin:
    fields_by_action = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        view = self.context.get("view")
        action = getattr(view, "action", None)

        if action and action in self.fields_by_action:
            allowed = set(self.fields_by_action[action])

        for field_name in list(self.fields.keys()):
            if field_name not in allowed:
                self.fields.pop(field_name)
