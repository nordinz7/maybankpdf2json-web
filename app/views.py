import io

from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render, get_object_or_404

from maybankpdf2json import MaybankPdf2Json

from .models import Statement, Transaction


# ---------------------------------------------------------------------------
# Upload page (GET + POST)
# ---------------------------------------------------------------------------


def index(request: HttpRequest) -> HttpResponse:
    """Main upload page."""
    statements = Statement.objects.all()
    return render(request, "app/index.html", {"statements": statements})


def upload(request: HttpRequest) -> HttpResponse:
    """Handle bulk PDF upload via HTMX POST.

    Returns the updated statement list partial so HTMX can swap it in.
    """
    if request.method != "POST":
        return HttpResponse(status=405)

    files = request.FILES.getlist("pdfs")
    password: str = request.POST.get("password", "")

    for f in files:
        statement = Statement.objects.create(
            filename=f.name,
            status=Statement.STATUS_PROCESSING,
        )
        try:
            buf = io.BytesIO(f.read())
            extractor = MaybankPdf2Json(buf, pwd=password or None)
            result = extractor.json()

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

            statement.account_number = result.get("account_number")
            statement.statement_date = result.get("statement_date")
            statement.status = Statement.STATUS_DONE
            statement.save()

        except Exception as exc:  # noqa: BLE001
            statement.status = Statement.STATUS_ERROR
            statement.error_message = str(exc)
            statement.save()

    statements = Statement.objects.all()
    return render(
        request, "app/partials/statement_list.html", {"statements": statements}
    )


# ---------------------------------------------------------------------------
# Statements list page
# ---------------------------------------------------------------------------


def statements(request: HttpRequest) -> HttpResponse:
    """Full statements list page."""
    all_statements = Statement.objects.all()
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

    accounts = (
        Statement.objects.filter(status=Statement.STATUS_DONE)
        .exclude(account_number=None)
        .values_list("account_number", flat=True)
        .distinct()
    )

    context = {
        "transactions": qs,
        "q": q,
        "account": account,
        "stmt_id": stmt_id,
        "accounts": accounts,
        "all_statements": Statement.objects.filter(status=Statement.STATUS_DONE),
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
    statements_qs = Statement.objects.all()
    return render(
        request, "app/partials/statement_list.html", {"statements": statements_qs}
    )
