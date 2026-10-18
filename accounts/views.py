from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import EmailUserCreationForm


def register(request):
    if request.method == "POST":
        form = EmailUserCreationForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    user = form.save()
            except IntegrityError:
                form.add_error(
                    "email", "An account with this email already exists."
                )
            else:
                login(request, user)
                return redirect(_safe_next(request))
    else:
        form = EmailUserCreationForm()
    return render(request, "registration/register.html", {"form": form})


def _safe_next(request):
    next_url = request.POST.get("next") or request.GET.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}
    ):
        return next_url
    return settings.LOGIN_REDIRECT_URL


@login_required
def home(request):
    return render(request, "accounts/home.html")
