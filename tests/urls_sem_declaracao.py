from django.urls import path

from tests.app_teste import views

urlpatterns = [
    path("", views.inicio),
    path("esquecida/", views.esquecida),
]
