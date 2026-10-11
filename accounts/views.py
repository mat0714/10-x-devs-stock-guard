from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import EmailUserCreationForm


def register(request):
    if request.method == "POST":
        form = EmailUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect(settings.LOGIN_REDIRECT_URL)
    else:
        form = EmailUserCreationForm()
    return render(request, "registration/register.html", {"form": form})


@login_required
def home(request):
    return render(request, "accounts/home.html")
