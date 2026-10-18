# Review Fixes — price-data-fetch-boundary

Queued from the implementation review triage on 2026-10-18.
Report: `context/changes/price-data-fetch-boundary/reviews/impl-review.md`

## Applied (code)

- F1 — `marketdata/providers/twelvedata.py`: map HTTP status on JSON-decode failure.
- F2 — `marketdata/services.py`: prune window floored at `MARKET_DATA_LOOKBACK_BARS`.
- F3 — `marketdata/services.py`: `bars < 1` → `PriceUnavailable(reason="invalid_symbol")`.
- F4 — `marketdata/services.py`: convert unexpected fetch/persistence exceptions to typed `provider_error` results.
- F5 — `marketdata/services.py`: document the single-worker, no-locking assumption.
- F6 — `marketdata/services.py`: document holiday/half-day freshness behaviour.
- F7 — `marketdata/management/commands/fetch_candles.py`: stop writing the raw provider `message` to stdout.
- F8 — `marketdata/providers/twelvedata.py`: skip malformed rows instead of discarding the whole symbol.
- F9 — make intra-app imports relative in `services.py`, `providers/twelvedata.py`, `commands/fetch_candles.py`.

## Plan reconciliation needed before archive

1. **F2** deviates from `plan.md:79` and `:261`: a smaller `--bars` no longer shrinks the stored cache window.
2. **F8** deviates from `plan.md:167`: structurally invalid values are now skipped per row rather than mapped wholesale to `invalid_response`.

## Deferred (not acted on)

- None — all nine findings were fixed in triage.
