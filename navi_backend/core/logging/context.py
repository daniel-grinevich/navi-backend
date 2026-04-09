import contextvars

_log_ctx: contextvars.ContextVar = contextvars.ContextVar(
    "log_context",
    default=None,
)


def init_log_ctx():
    _log_ctx.set({})


def get_log_ctx():
    return _log_ctx.get() or {}


def set_log_ctx(context):
    _log_ctx.set(context)


def set_log_ctx_key(key, value):
    ctx = _log_ctx.get()
    if ctx is None:
        ctx = {}
        _log_ctx.set(ctx)
    ctx[key] = value


def pop_log_ctx_key(key):
    ctx = _log_ctx.get()
    if ctx is None:
        return
    ctx.pop(key, None)


def clear_log_ctx():
    _log_ctx.set(None)
