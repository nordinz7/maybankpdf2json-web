import io
import json
from datetime import datetime

from django.db import IntegrityError
from django.db.models import Case, CharField, Q, Value, When
from django.db.models.functions import Concat, Substr
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render, get_object_or_404

from maybankpdf2json import MaybankPdf2Json

from .models import Statement, Transaction


def parse_date_to_sort_key(value: str) -> str:
    """Convert supported date input formats to YYYYMMDD sort key."""
    if not value:
        return ""

    raw = value.strip()
    if not raw:
        return ""

    for fmt in ("%Y-%m-%d", "%d/%m/%y", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y%m%d")
        except ValueError:
            continue
    return ""


def parse_numeric_query(value: str):
    """Return a float for numeric-only queries, otherwise None."""
    if not value:
        return None
    cleaned = value.replace(",", "").strip()
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def annotate_transaction_sort_date(queryset):
    """Annotate transaction queryset with a sortable YYYYMMDD date key."""
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
    )


def with_hx_toast(response: HttpResponse, message: str, level: str = "success") -> HttpResponse:
    """Attach an HTMX trigger event for showing Bootstrap toast feedback."""
    payload = {"showToast": {"message": message, "level": level}}
    response["HX-Trigger"] = json.dumps(payload)
    return response


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
    return annotate_transaction_sort_date(queryset).order_by("-sort_date", "-id")


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
    upload_results = []

    # Accept only PDFs even if a full folder is selected client-side.
    pdf_files = [f for f in files if f.name.lower().endswith(".pdf")]

    if not pdf_files:
        statements = ordered_statements()
        upload_results.append(
            {
                "file": "No valid PDF selected",
                "status": "warning",
                "message": "Please choose at least one .pdf file.",
            }
        )
        response = render(
            request,
            "app/partials/statement_list.html",
            {"statements": statements, "upload_results": upload_results},
        )
        return with_hx_toast(response, "No valid PDF selected.", "warning")

    for f in pdf_files:
        try:
            buf = io.BytesIO(f.read())
            extractor = MaybankPdf2Json(buf, pwd=password or None)
            result = extractor.json()

            statement_date = (result.get("statement_date") or "").strip()
            account_number = (result.get("account_number") or "").strip()

            if not statement_date or not account_number:
                upload_results.append(
                    {
                        "file": f.name,
                        "status": "error",
                        "message": "Missing statement date/account number in PDF.",
                    }
                )
                continue

            existing_stmt = None
            if statement_date and account_number:
                existing_stmt = Statement.objects.filter(
                    statement_date=statement_date,
                    account_number=account_number,
                ).first()

            if existing_stmt and not override_existing:
                upload_results.append(
                    {
                        "file": f.name,
                        "status": "warning",
                        "message": f"Skipped duplicate ({statement_date}, {account_number}).",
                    }
                )
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
            upload_results.append(
                {
                    "file": f.name,
                    "status": "success",
                    "message": (
                        f"Uploaded {statement_date} ({account_number}) with "
                        f"{len(transactions)} transaction(s)."
                    ),
                }
            )

        except IntegrityError:
            upload_results.append(
                {
                    "file": f.name,
                    "status": "error",
                    "message": "Skipped due to duplicate/integrity rule.",
                }
            )
            continue

        except Exception:  # noqa: BLE001
            upload_results.append(
                {
                    "file": f.name,
                    "status": "error",
                    "message": "Failed to parse or process this file.",
                }
            )
            continue

    statements = ordered_statements()
    success_count = sum(1 for r in upload_results if r["status"] == "success")
    warning_count = sum(1 for r in upload_results if r["status"] == "warning")
    error_count = sum(1 for r in upload_results if r["status"] == "error")

    response = render(
        request,
        "app/partials/statement_list.html",
        {"statements": statements, "upload_results": upload_results},
    )
    return with_hx_toast(
        response,
        (
            f"Upload complete: {success_count} success, "
            f"{warning_count} skipped, {error_count} error."
        ),
        "success" if success_count > 0 else "warning",
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
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()
    page_number = request.GET.get("page", "1").strip() or "1"

    qs = annotate_transaction_sort_date(Transaction.objects.select_related("statement"))

    if q:
        amount = parse_numeric_query(q)
        if amount is None:
            qs = qs.filter(desc__icontains=q)
        else:
            epsilon = 0.005
            qs = qs.filter(
                Q(desc__icontains=q)
                | Q(trans__gte=amount - epsilon, trans__lte=amount + epsilon)
                | Q(bal__gte=amount - epsilon, bal__lte=amount + epsilon)
            )
    if account:
        qs = qs.filter(statement__account_number__icontains=account)
    if stmt_id:
        qs = qs.filter(statement_id=stmt_id)

    date_from_key = parse_date_to_sort_key(date_from)
    date_to_key = parse_date_to_sort_key(date_to)
    if date_from_key:
        qs = qs.filter(sort_date__gte=date_from_key)
    if date_to_key:
        qs = qs.filter(sort_date__lte=date_to_key)

    qs = qs.order_by("-sort_date", "-id")
    paginator = Paginator(qs, 50)
    page_obj = paginator.get_page(page_number)

    accounts = Statement.objects.values_list("account_number", flat=True).distinct()

    context = {
        "transactions": page_obj.object_list,
        "page_obj": page_obj,
        "total_transactions": paginator.count,
        "q": q,
        "account": account,
        "stmt_id": stmt_id,
        "date_from": date_from,
        "date_to": date_to,
        "accounts": accounts,
        "all_statements": ordered_statements(),
    }

    query_without_page = request.GET.copy()
    query_without_page.pop("page", None)
    context["query_without_page"] = query_without_page.urlencode()
    context["page_sep"] = "&" if context["query_without_page"] else ""

    # If HTMX request, return only the rows partial
    if request.headers.get("HX-Request"):
        return render(request, "app/partials/transaction_rows.html", context)

    return render(request, "app/transactions.html", context)


# ---------------------------------------------------------------------------
# Delete statement
# ---------------------------------------------------------------------------


def delete_statement(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete a statement and all its transactions, return updated list."""
    if request.method not in {"DELETE", "POST"}:
        return HttpResponse(status=405)
    stmt = get_object_or_404(Statement, pk=pk)
    deleted_label = f"{stmt.statement_date} ({stmt.account_number})"
    stmt.delete()
    statements_qs = ordered_statements()
    response = render(
        request, "app/partials/statement_list.html", {"statements": statements_qs}
    )
    return with_hx_toast(response, f"Deleted statement {deleted_label}.", "success")
