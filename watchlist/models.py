from django.conf import settings
from django.db import models


class WatchlistItem(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='watchlist_items',
    )
    symbol = models.CharField(max_length=16)
    name = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'symbol'],
                name='uniq_watchlist_item_user_symbol',
            ),
        ]
        ordering = ['symbol', 'id']

    def __str__(self) -> str:
        if self.name:
            return f'{self.symbol} ({self.name})'
        return self.symbol
