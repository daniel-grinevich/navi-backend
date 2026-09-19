from navi_backend.core.logging import get_logger

logger = get_logger(__name__)


class BaseService:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.run()

    def return_result(self, success, result=None):
        if success:
            return {"success": True, "ctx": result}
        return {"success": False, "ctx": result}

    def log_service_error(self, method):
        logger.exception(
            "service_error",
            service=self.__class__.__name__,
            method=method.__name__,
        )

    def execute(self):
        error = "Execute method must be defined."
        raise RuntimeError(error)

    def run(self):
        success = True
        ctx = {}
        with self.execute() as methods:
            for method in methods:
                try:
                    ctx = method(ctx)
                except Exception:
                    success = False
                    self.log_service_error(method)
                    raise

        self.result = self.return_result(success, ctx)
        return self.result
