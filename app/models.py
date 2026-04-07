from django.db import models


class Statement(models.Model):
    account_number = models.CharField(max_length=64)
    statement_date = models.CharField(max_length=16)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["account_number", "statement_date"],
                name="uniq_account_statement_date_non_empty",
            ),
            models.CheckConstraint(
                check=~models.Q(account_number="") & ~models.Q(statement_date=""),
                name="statement_account_and_date_non_empty",
            ),
        ]

    def __str__(self) -> str:
        return self.statement_date or f"Statement #{self.pk}"


class Transaction(models.Model):
    statement = models.ForeignKey(
        Statement, on_delete=models.CASCADE, related_name="transactions"
    )
    date = models.CharField(max_length=10)  # dd/mm/yy
    desc = models.TextField()
    trans = models.FloatField()
    bal = models.FloatField()

    class Meta:
        ordering = ["-id"]

    def __str__(self) -> str:
        return f"{self.date} {self.desc[:40]}"
