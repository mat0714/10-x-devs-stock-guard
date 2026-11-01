import re

from django import forms
from django.core.exceptions import ValidationError

from .models import WatchlistItem

SYMBOL_PATTERN = re.compile(r'^[A-Z][A-Z0-9.\-]{0,15}$')


class WatchlistItemForm(forms.ModelForm):
    class Meta:
        model = WatchlistItem
        fields = ('symbol', 'name')

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields['name'].required = False
        self.fields['symbol'].widget.attrs['autofocus'] = True

    def clean_symbol(self):
        normalized_symbol = self.cleaned_data['symbol'].strip().upper()
        if not SYMBOL_PATTERN.match(normalized_symbol):
            raise ValidationError(
                'Enter a ticker of 1-16 characters: letters, digits, "." or "-", '
                'starting with a letter.'
            )
        if WatchlistItem.objects.filter(
            user=self.user, symbol=normalized_symbol
        ).exists():
            raise ValidationError('This stock is already on your watchlist.')
        return normalized_symbol

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.user = self.user
        if commit:
            instance.save()
        return instance
