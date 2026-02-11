class RequestLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.simple_flag = "poop"

        response = self.get_response(request)

        response["X-Simple"] = "pee"
        return response
