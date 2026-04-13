class ViewFilterMixin:
    fields_by_action = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        view = self.context.get("view")
        action = getattr(view, "action", None)
        field_sets = getattr(self.Meta, "field_sets", {})

        if not action or action not in field_sets:
            return

        allowed = set(field_sets[action])

        if action in ("update", "partial_update"):
            for name, field in self.fields.items():
                if name not in allowed:
                    field.read_only = True

        for field_name in list(self.fields.keys()):
            if field_name not in allowed:
                self.fields.pop(field_name)

        for name in list(self.fields.keys()):
            if name not in allowed:
                self.fields.pop(name)
