"""Verifica la coordinación del programa sin red ni cambios en las evidencias reales."""

import json
from unittest.mock import MagicMock

import integrador


def test_flujo_completo_con_configuracion_y_archivos_temporales(tmp_path, monkeypatch):
    datos = tmp_path / "datos"
    salida = tmp_path / "salida"
    datos.mkdir()
    registro_a = {
        "provider_record_id": "A-TEST",
        "station": {"city_name": "Bogota", "country_code": "CO"},
        "location": {"lat": 4.7, "lon": -74.1},
        "measurements": {"temperature_f": 68, "relative_humidity": 50, "wind_speed_ms": 10},
        "observed_at": "2026-09-01T06:00:00-05:00",
    }
    (datos / "proveedor_a.json").write_text(
        json.dumps({"records": [registro_a, {"provider_record_id": "A-ERROR"}]}),
        encoding="utf-8",
    )
    (datos / "proveedor_b.csv").write_text(
        "record_code;municipality;country;latitude_deg;longitude_deg;temp_celsius;"
        "humidity_pct;wind_kmh;measurement_time;origin_code\n"
        "B-TEST;Cali;CO;3.4;-76.5;25;60;10;01/09/2026 06:00;PB\n"
        "B-INVALIDO;Cali;CO;3.4;-76.5;25;120;10;01/09/2026 07:00;PB\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(integrador, "DIRECTORIO_DATOS", datos)
    monkeypatch.setattr(integrador, "DIRECTORIO_SALIDA", salida)
    monkeypatch.setattr(integrador, "URL_BASE", "https://prueba.example")
    monkeypatch.setattr(integrador, "EQUIPO", "EQUIPO-TEST")
    sesion = MagicMock()
    sesion.__enter__.return_value = sesion
    almacenadas = []

    def respuesta(codigo, contenido):
        resultado = MagicMock(status_code=codigo, text=json.dumps(contenido))
        resultado.json.return_value = contenido
        return resultado

    def post(url, **opciones):
        assert url == "https://prueba.example/api/v1/mediciones"
        assert opciones["headers"]["X-Equipo"] == "EQUIPO-TEST"
        almacenadas.append(opciones["json"])
        return respuesta(201, {"id": len(almacenadas), "estado": "aceptada"})

    def get(url, **opciones):
        assert url == "https://prueba.example/api/v1/mediciones"
        assert opciones["params"] == {"equipo": "EQUIPO-TEST"}
        return respuesta(200, {"equipo": "EQUIPO-TEST", "total": 2, "mediciones": almacenadas})

    sesion.post.side_effect = post
    sesion.get.side_effect = get
    monkeypatch.setattr("funciones.envios.requests.Session", lambda: sesion)

    assert integrador.main() == 0
    reporte = json.loads((salida / "reporte.json").read_text(encoding="utf-8"))
    normalizadas = json.loads((salida / "normalizadas.json").read_text(encoding="utf-8"))
    assert reporte["procesados"] == 4
    assert reporte["normalizados"] == len(normalizadas) == 3
    assert reporte["errores_normalizacion"] == 1
    assert reporte["rechazados_localmente"] == 1
    assert reporte["enviados"] == reporte["aceptados_api"] == 2
    assert reporte["rechazados_api"] == reporte["errores_comunicacion"] == 0
    assert reporte["consulta_final"]["exitosa"]
    assert sesion.post.call_count == 2
    assert sesion.get.call_count == 1
    assert almacenadas[1]["fecha_hora"].endswith("-05:00")
    assert any(m["humedad"] == 120 for m in normalizadas)
