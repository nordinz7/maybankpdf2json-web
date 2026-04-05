from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("upload/", views.upload, name="upload"),
    path("statements/", views.statements, name="statements"),
    path(
        "statements/<int:pk>/delete/", views.delete_statement, name="delete_statement"
    ),
    path("transactions/", views.transactions, name="transactions"),
]
