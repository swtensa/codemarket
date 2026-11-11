from django.shortcuts import render


def index(request):
    """Главная страница = каталог."""
    return render(request, "catalog/index.html")
