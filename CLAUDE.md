# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

All commands assume the venv is active: `source venv/bin/activate`.

- Run dev server: `python manage.py runserver`
- Apply migrations: `python manage.py migrate`
- Create migrations after model changes: `python manage.py makemigrations`
- Django shell: `python manage.py shell`
- Install deps: `pip install -r requirements.txt` (the `maybankpdf2json` parser is a separate package pulled in here)

There is no test suite, lint config, or type-check command wired up in this repo.

## Architecture

Single Django project (`config/`) with one app (`app/`). SQLite locally, PostgreSQL on Render via `DATABASE_URL` (dj-database-url + WhiteNoise for static files). Frontend is server-rendered Django templates with HTMX for partial swaps and Bootstrap 5 for styling.

**Request flow for uploads** ([app/views.py](app/views.py)): `upload()` receives a multi-file POST from the HTMX form, reads each PDF into a `BytesIO`, hands it to `MaybankPdf2Json(buf, pwd=...)`, and persists the returned `statement_date` / `account_number` / `transactions[]` as a `Statement` + bulk-created `Transaction` rows. It then re-renders `app/partials/statement_list.html` so HTMX can swap the updated list into the page. The transactions page behaves similarly: if `HX-Request` header is present it returns just `partials/transaction_rows.html`, otherwise the full `transactions.html`.

**Date handling is the main gotcha.** `Statement.statement_date` and `Transaction.date` are stored as `dd/mm/yy` **strings**, not real dates. Any chronological ordering has to go through the `ordered_statements()` / `ordered_transactions()` helpers in [app/views.py](app/views.py#L14-L55), which use a `Case`/`Substr`/`Concat` annotation to build a sortable `20yymmdd` key. If you add new views that list statements or transactions, reuse these helpers rather than ordering by the raw string fields.

**Duplicate handling.** `Statement` has a `UniqueConstraint` on `(account_number, statement_date)` plus a `CheckConstraint` requiring both to be non-empty ([app/models.py](app/models.py#L11-L20)). The upload flow enforces this at the application layer too: if a matching statement exists and the form's `override_existing` checkbox is unset, the new file is skipped; if set, the old `Statement` is deleted first (cascading its transactions) before the new one is created. `IntegrityError` is swallowed as a safety net. Parse failures are also silently skipped — there is currently no per-file error reporting surfaced to the user.

## Deployment

Render is the target ([render.yaml](render.yaml), [DEPLOY.md](DEPLOY.md)). `build.sh` runs `pip install`, `migrate`, and `collectstatic`. `DEBUG`, `SECRET_KEY`, `ALLOWED_HOSTS`, and `CSRF_TRUSTED_ORIGINS` are injected from the Render dashboard; `DATABASE_URL` switches the app to Postgres automatically.
