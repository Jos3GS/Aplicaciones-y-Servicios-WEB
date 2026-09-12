"""Impide que una prueba haga solicitudes HTTP reales por accidente."""

import pytest
import requests


@pytest.fixture(autouse=True)
def bloquear_http_real(monkeypatch):
    def solicitud_prohibida(*args, **kwargs):
        raise AssertionError("Las pruebas deben usar respuestas HTTP simuladas.")

    monkeypatch.setattr(requests.sessions.Session, "request", solicitud_prohibida)
