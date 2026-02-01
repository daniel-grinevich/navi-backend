class ReadOnlyAuditMixin:
    read_only_fields = ("slug", "created_at", "updated_at", "created_by", "updated_by")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.read_only_fields:
            if field in self.fields:
                self.fields[field].read_only = True
