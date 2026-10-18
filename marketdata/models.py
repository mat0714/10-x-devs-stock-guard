from django.db import models


class DailyCandle(models.Model):
    symbol = models.CharField(max_length=16)
    date = models.DateField()
    open = models.DecimalField(max_digits=18, decimal_places=6)
    high = models.DecimalField(max_digits=18, decimal_places=6)
    low = models.DecimalField(max_digits=18, decimal_places=6)
    close = models.DecimalField(max_digits=18, decimal_places=6)
    volume = models.BigIntegerField(null=True)
    fetched_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['symbol', 'date'],
                name='uniq_daily_candle_symbol_date',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.symbol} {self.date}'
