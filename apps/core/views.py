from django.shortcuts import render


def soon(request, *args, **kwargs):
    """Временная страница раздела, который появится на следующем этапе."""
    return render(request, "core/soon.html")
