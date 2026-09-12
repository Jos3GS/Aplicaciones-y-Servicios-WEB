"""Casos de normalización y validación independientes de los datasets y la API."""

from copy import deepcopy

import pytest

from funciones.normalizacion import (
    normalizar_proveedor_a,
    normalizar_proveedor_b,
    normalizar_registros,
)
from funciones.validacion import validar_medicion, validar_resultados


@pytest.fixture
def registro_a():
    return {
        "provider_record_id": "A-PRUEBA",
        "station": {"city_name": "Bogota", "country_code": "CO"},
        "location": {"lat": 4.7, "lon": -74.1},
        "measurements": {
            "temperature_f": 68, "relative_humidity": 50, "wind_speed_ms": 10,
        },
        "observed_at": "2026-09-01T06:00:00-05:00",
        "source": "weather_provider_a",
    }


@pytest.fixture
def medicion():
    return {
        "ciudad": "Bogota", "pais": "CO", "latitud": 4.7, "longitud": -74.1,
        "temperatura_c": 20, "humedad": 50, "viento_kmh": 36,
        "fecha_hora": "2026-09-01T06:00:00-05:00", "origen": "proveedor_a",
    }


def test_transformacion_a_al_contrato_sin_modificar_original(registro_a, medicion):
    original = deepcopy(registro_a)
    assert normalizar_proveedor_a(registro_a) == medicion
    assert registro_a == original


def test_conversion_fahrenheit_a_celsius(registro_a):
    registro_a["measurements"]["temperature_f"] = 212
    assert normalizar_proveedor_a(registro_a)["temperatura_c"] == pytest.approx(100)


def test_conversion_metros_por_segundo_a_kilometros_por_hora(registro_a):
    registro_a["measurements"]["wind_speed_ms"] = 8.47
    assert normalizar_proveedor_a(registro_a)["viento_kmh"] == pytest.approx(30.492)


def test_transformacion_b_convierte_textos_y_fecha(medicion):
    registro = {
        "record_code": "B-PRUEBA", "municipality": "Bogota", "country": "CO",
        "latitude_deg": "4.7", "longitude_deg": "-74.1", "temp_celsius": "20",
        "humidity_pct": "50", "wind_kmh": "36",
        "measurement_time": "01/09/2026 06:00", "origin_code": "PB",
    }
    assert normalizar_proveedor_b(registro) == medicion | {"origen": "proveedor_b"}


def test_registro_valido(medicion):
    assert validar_medicion(medicion) == []


def test_registro_invalido_por_humedad(medicion):
    medicion["humedad"] = 108.4
    errores = validar_medicion(medicion)
    assert len(errores) == 1
    assert "humedad" in errores[0]


@pytest.mark.parametrize("cambios", [
    {"latitud": -90, "longitud": -180, "humedad": 0, "viento_kmh": 0},
    {"latitud": 90, "longitud": 180, "humedad": 100},
])
def test_limites_inclusivos_son_validos(medicion, cambios):
    assert validar_medicion(medicion | cambios) == []


@pytest.mark.parametrize("campo, valor", [
    ("latitud", 90.01), ("longitud", -180.01), ("viento_kmh", -0.01),
    ("ciudad", "  "), ("pais", ""), ("origen", "PB"),
    ("temperatura_c", True), ("humedad", float("nan")),
])
def test_rechaza_infracciones_del_contrato(medicion, campo, valor):
    assert any(campo in error for error in validar_medicion(medicion | {campo: valor}))


def test_fecha_imposible_es_error_de_normalizacion(registro_a):
    registro_a["observed_at"] = "2026-02-30T06:00:00-05:00"
    normalizadas, resultados = normalizar_registros([registro_a], "proveedor_a")
    assert normalizadas == []
    assert resultados[0]["estado"] == "error_normalizacion"
    assert "fecha_hora" in resultados[0]["detalle"]


def test_error_de_normalizacion_no_impide_procesar_los_siguientes(registro_a):
    defectuoso = deepcopy(registro_a)
    defectuoso["measurements"]["temperature_f"] = "N/A"
    normalizadas, resultados = normalizar_registros([defectuoso, registro_a], "proveedor_a")
    assert len(normalizadas) == 1
    assert [r["estado"] for r in resultados] == ["error_normalizacion", "normalizado"]
    assert resultados[0]["id_interno"] != resultados[1]["id_interno"]
    assert resultados[0]["id_proveedor"] == "A-PRUEBA"


def test_rechazado_local_permanece_normalizado(registro_a):
    registro_a["measurements"]["relative_humidity"] = 108.4
    normalizadas, resultados = normalizar_registros([registro_a], "proveedor_a")
    validos, rechazados = validar_resultados(resultados)
    assert validos == []
    assert len(rechazados) == len(normalizadas) == 1
    assert rechazados[0]["estado"] == "rechazado_localmente"
    assert rechazados[0]["datos"] == normalizadas[0]
    assert normalizadas[0]["humedad"] == 108.4
