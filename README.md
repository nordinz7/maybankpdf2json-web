# Maybank PDF to JSON Web

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-4.2-092E20?logo=django&logoColor=white)
![HTMX](https://img.shields.io/badge/HTMX-1.9-3366CC?logo=htmx&logoColor=white)
![Bootstrap](https://img.shields.io/badge/Bootstrap-5.3-7952B3?logo=bootstrap&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-Local_DB-003B57?logo=sqlite&logoColor=white)

Small Django web UI for uploading Maybank PDF statements, extracting transactions through the `maybankpdf2json` parser, and browsing the imported data in a searchable interface.

## What It Does

- Upload one or more password-protected or unprotected Maybank PDF statements
- Parse each file with `maybankpdf2json` package
- Store statements and transactions in SQLite
- Show upload status, parser failures, and extracted metadata
- Browse imported transactions with HTMX-powered filters
- Delete statements together with their related transactions

## Stack

- Python
- Django 4.2
- SQLite
- HTMX
- Bootstrap 5
- `python-dotenv`
- `maybankpdf2json`

## Project Layout

```text
.
|-- app/
|   |-- migrations/
|   |-- templates/app/
|   |-- models.py
|   |-- urls.py
|   `-- views.py
|-- config/
|   |-- settings.py
|   `-- urls.py
|-- manage.py
`-- requirements.txt
```

## Quick Start

1. Create and activate a virtual environment.
2. Install the web app requirements.
3. Install the parser package separately in the same environment.
4. Run migrations.
5. Start the Django development server.

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Open `http://127.0.0.1:8000/`.

## Environment Variables

This project loads environment variables from `.env` automatically.

```env
SECRET_KEY=django-insecure-dev-only-change-in-production
DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost
```

Notes:

- `SECRET_KEY` should be replaced outside local development.
- `DEBUG` defaults to `True` when omitted.
- `ALLOWED_HOSTS` is a comma-separated list.

## Main Routes

- `/` - upload page and recent statements list
- `/upload/` - bulk PDF upload endpoint
- `/statements/` - full statements page
- `/transactions/` - searchable transactions page
- `/statements/<id>/delete/` - delete a statement and its transactions

## Data Model

### Statement

- Source filename
- Account number
- Statement date
- Upload timestamp
- Processing status
- Error message when parsing fails

### Transaction

- Statement relationship
- Date
- Description
- Transaction amount
- Balance

## Local Development Notes

- The app uses SQLite by default via `db.sqlite3`.
- Uploaded files are processed in memory; extracted rows are persisted to the database.
- Duplicate statement uploads are currently allowed.
- Failed parses are recorded on the statement row with the exception message.