from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path

from .forms import EmailAuthenticationForm
from .views import home, register

urlpatterns = [
    path(
        "login/",
        LoginView.as_view(authentication_form=EmailAuthenticationForm),
        name="login",
    ),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("register/", register, name="register"),
    path("", home, name="home"),
]
