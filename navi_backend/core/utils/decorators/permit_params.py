def permit_params(params=(), **kwargs):
    kwargs.get("request")

    def decorator(func):
        return func

    return decorator
