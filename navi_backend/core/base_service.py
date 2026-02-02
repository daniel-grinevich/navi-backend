import logging

logger = logging.getLogger(__name__)


class BaseService:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.run()

    def return_result(self, success, result=None):
        if success:
            return {"success": True, "ctx": result}
        return {"success": False, "ctx": result}

    def log_service_error(self, error, method):
        logger.exception(
            "Failed in service %s, in method %s, with error: %s",
            self.__class__.__name__,
            method.__name__,
            error,
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
                except Exception as error:
                    success = False
                    self.log_service_error(error, method)
                    raise

        self.result = self.return_result(success, ctx)
        return self.result
