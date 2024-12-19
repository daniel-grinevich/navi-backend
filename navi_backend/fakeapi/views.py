from django.http import HttpResponse


# Create your views here.
def welcome_view(request):
    return HttpResponse(content="hi")
