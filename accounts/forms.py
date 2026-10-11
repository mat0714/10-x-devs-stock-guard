from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError


class EmailUserCreationForm(UserCreationForm):
    email = forms.EmailField(label="Email", max_length=150)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget = forms.HiddenInput()
        self.fields["username"].required = False
        self.fields["username"].label = ""
        self.fields["email"].widget.attrs["autofocus"] = True
        self.order_fields(["username", "email", "password1", "password2"])

    def clean_email(self):
        normalized_email = self.cleaned_data["email"].strip().lower()
        if len(normalized_email) > 150:
            raise ValidationError("Email address must be 150 characters or fewer.")
        if User.objects.filter(username__iexact=normalized_email).exists():
            raise ValidationError("An account with this email already exists.")
        self.cleaned_data["username"] = normalized_email
        return normalized_email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data["email"]
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
            self.save_m2m()
        return user


class EmailAuthenticationForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Email"

    def clean_username(self):
        return self.cleaned_data["username"].strip().lower()
