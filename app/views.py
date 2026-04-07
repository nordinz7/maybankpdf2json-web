import io

from django.db import IntegrityError
from django.db.models import Case, CharField, Value, When
from django.db.models.functions import Concat, Substr
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render, get_object_or_404

from maybankpdf2json import MaybankPdf2Json

from .models import Statement, Transaction


def ordered_statements():
    """Return statements sorted by latest statement_date first.

    statement_date is stored as dd/mm/yy, so compute a sortable yymmdd key.
    """
    return Statement.objects.annotate(
        sort_date=Case(
            When(
                statement_date__contains="/",
                then=Concat(
                    Value("20"),
                    Substr("statement_date", 7, 2),
                    Substr("statement_date", 4, 2),
                    Substr("statement_date", 1, 2),
                ),
            ),
            default=Value(""),
            output_field=CharField(),
        )
    ).order_by("-sort_date", "-uploaded_at")


def ordered_transactions(queryset):
    """Return transactions sorted by latest transaction date first.

    date is stored as dd/mm/yy, so compute a sortable yymmdd key.
    """
    return queryset.annotate(
        sort_date=Case(
            When(
                date__contains="/",
                then=Concat(
                    Value("20"),
                    Substr("date", 7, 2),
                    Substr("date", 4, 2),
                    Substr("date", 1, 2),
                ),
            ),
            default=Value(""),
            output_field=CharField(),
        )
    ).order_by("-sort_date", "-id")


# ---------------------------------------------------------------------------
# Upload page (GET + POST)
# ---------------------------------------------------------------------------


def index(request: HttpRequest) -> HttpResponse:
    """Main upload page."""
    statements = ordered_statements()
    return render(request, "app/index.html", {"statements": statements})


def upload(request: HttpRequest) -> HttpResponse:
    """Handle bulk PDF upload via HTMX POST.

    Returns the updated statement list partial so HTMX can swap it in.
    """
    if request.method != "POST":
        return HttpResponse(status=405)

    files = request.FILES.getlist("pdfs")
    password: str = request.POST.get("password", "")
    override_existing = request.POST.get("override_existing") in {"1", "true", "on"}

    # Accept only PDFs even if a full folder is selected client-side.
    pdf_files = [f for f in files if f.name.lower().endswith(".pdf")]

    if not pdf_files:
        statements = ordered_statements()
        return render(
            request, "app/partials/statement_list.html", {"statements": statements}
        )

    for f in pdf_files:
        try:
            buf = io.BytesIO(f.read())
            extractor = MaybankPdf2Json(buf, pwd=password or None)
            result = extractor.json()

            statement_date = (result.get("statement_date") or "").strip()
            account_number = (result.get("account_number") or "").strip()

            if not statement_date or not account_number:
                continue

            existing_stmt = None
            if statement_date and account_number:
                existing_stmt = Statement.objects.filter(
                    statement_date=statement_date,
                    account_number=account_number,
                ).first()

            if existing_stmt and not override_existing:
                continue

            if existing_stmt and override_existing:
                existing_stmt.delete()

            statement = Statement.objects.create(
                statement_date=statement_date,
                account_number=account_number,
            )

            transactions = [
                Transaction(
                    statement=statement,
                    date=tx["date"],
                    desc=tx["desc"],
                    trans=tx["trans"],
                    bal=tx["bal"],
                )
                for tx in result.get("transactions", [])
            ]
            Transaction.objects.bulk_create(transactions)

        except IntegrityError:
            continue

        except Exception:  # noqa: BLE001
            continue

    statements = ordered_statements()
    return render(
        request, "app/partials/statement_list.html", {"statements": statements}
    )


# ---------------------------------------------------------------------------
# Statements list page
# ---------------------------------------------------------------------------


def statements(request: HttpRequest) -> HttpResponse:
    """Full statements list page."""
    all_statements = ordered_statements()
    return render(request, "app/statements.html", {"statements": all_statements})


# ---------------------------------------------------------------------------
# Transactions page with search
# ---------------------------------------------------------------------------


def transactions(request: HttpRequest) -> HttpResponse:
    """Transactions page with optional search/filter.

    When requested via HTMX (hx-get), returns only the table rows partial.
    """
    q = request.GET.get("q", "").strip()
    account = request.GET.get("account", "").strip()
    stmt_id = request.GET.get("statement", "").strip()

    qs = Transaction.objects.select_related("statement").all()

    if q:
        qs = qs.filter(desc__icontains=q)
    if account:
        qs = qs.filter(statement__account_number__icontains=account)
    if stmt_id:
        qs = qs.filter(statement_id=stmt_id)

    qs = ordered_transactions(qs)

    accounts = Statement.objects.values_list("account_number", flat=True).distinct()

    context = {
        "transactions": qs,
        "q": q,
        "account": account,
        "stmt_id": stmt_id,
        "accounts": accounts,
        "all_statements": ordered_statements(),
    }

    # If HTMX request, return only the rows partial
    if request.headers.get("HX-Request"):
        return render(request, "app/partials/transaction_rows.html", context)

    return render(request, "app/transactions.html", context)


# ---------------------------------------------------------------------------
# Delete statement
# ---------------------------------------------------------------------------


def delete_statement(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete a statement and all its transactions, return updated list."""
    if request.method != "DELETE":
        return HttpResponse(status=405)
    stmt = get_object_or_404(Statement, pk=pk)
    stmt.delete()
    statements_qs = ordered_statements()
    return render(
        request, "app/partials/statement_list.html", {"statements": statements_qs}
    )
