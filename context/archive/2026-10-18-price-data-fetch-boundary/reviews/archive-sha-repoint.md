# Archive SHA repoint

- **Date:** 2026-11-13
- **Change:** price-data-fetch-boundary
- **Plan:** `context/changes/price-data-fetch-boundary/plan.md`

## Diagnosis

Every completed `- [x]` row in `## Progress` carried a SHA suffix that resolves to
**no object** in this repository (`git rev-parse --verify '<sha>^{commit}'` →
"unknown revision"). The cited suffixes appear nowhere in local history or on any
remote-tracking ref; they were stale placeholders written when the rows landed.

## Target

- **Remote / branch:** `origin/main` (remote default branch, resolved via `git ls-remote --symref origin HEAD` → `ref: refs/heads/main`).
- **Snapshot OID:** `5dd56babaaafff05f4922cd21175b24e5f00fdd5` (refreshed via `git fetch --no-tags origin +refs/heads/main:refs/remotes/origin/main`).

## Integration evidence

No implementation PR was associated with the change (linear commit history on
`main`, no branch/PR). The four replacement commits are the phase commits on
`origin/main`; each was matched to exactly one phase by its `(pN)` subject and its
diff scope (files touched, `git show --stat`), and each verified as an ancestor of
the target snapshot (`git merge-base --is-ancestor <sha> 5dd56ba` → exit 0):

- `7b54a76` — app + dependency + schema (`marketdata/` scaffold, `pyproject.toml`, `uv.lock`) → Phase 1
- `800cab5` — `marketdata/providers/` → Phase 2
- `b06b917` — `marketdata/services.py` → Phase 3
- `67892f1` — `marketdata/management/commands/fetch_candles.py` → Phase 4

**User decision:** *Update and archive* (explicit approval, 2026-11-13).

## Row mapping

| Row ID | Old suffix (resolved OID) | New SHA |
| ------ | ------------------------- | ------- |
| 1.1 | dfeca81 (object missing) | 7b54a76 |
| 1.2 | dfeca81 (object missing) | 7b54a76 |
| 1.3 | dfeca81 (object missing) | 7b54a76 |
| 1.4 | dfeca81 (object missing) | 7b54a76 |
| 1.5 | dfeca81 (object missing) | 7b54a76 |
| 1.6 | dfeca81 (object missing) | 7b54a76 |
| 2.1 | a604cb7 (object missing) | 800cab5 |
| 2.2 | a604cb7 (object missing) | 800cab5 |
| 2.3 | a604cb7 (object missing) | 800cab5 |
| 3.1 | 406b57b (object missing) | b06b917 |
| 3.2 | 406b57b (object missing) | b06b917 |
| 3.3 | 406b57b (object missing) | b06b917 |
| 3.4 | 406b57b (object missing) | b06b917 |
| 3.5 | 406b57b (object missing) | b06b917 |
| 4.1 | ee7f6ca (object missing) | 67892f1 |
| 4.2 | ee7f6ca (object missing) | 67892f1 |
| 4.3 | ee7f6ca (object missing) | 67892f1 |
| 4.4 | ee7f6ca (object missing) | 67892f1 |
| 4.5 | ee7f6ca (object missing) | 67892f1 |
| 4.6 | ee7f6ca (object missing) | 67892f1 |

**Affected rows:** 20 (all completed `- [x]` rows).
