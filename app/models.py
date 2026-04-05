from django.db import models


class Statement(models.Model):
    STATUS_PROCESSING = "processing"
    STATUS_DONE = "done"
    STATUS_ERROR = "error"
    STATUS_CHOICES = [
        (STATUS_PROCESSING, "Processing"),
        (STATUS_DONE, "Done"),
        (STATUS_ERROR, "Error"),
    ]

    filename = models.CharField(max_length=255)
    account_number = models.CharField(max_length=64, null=True, blank=True)
    statement_date = models.CharField(max_length=16, null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default=STATUS_PROCESSING
    )
    error_message = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self) -> str:
        return self.filename


class Transaction(models.Model):
    statement = models.ForeignKey(
        Statement, on_delete=models.CASCADE, related_name="transactions"
    )
    date = models.CharField(max_length=10)  # dd/mm/yy
    desc = models.TextField()
    trans = models.FloatField()
    bal = models.FloatField()

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.date} {self.desc[:40]}"
