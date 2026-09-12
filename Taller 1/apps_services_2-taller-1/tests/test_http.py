"""Pruebas HTTP sin conexión con la API real; compatibles con pytest."""

import unittest
import json
from unittest.mock import Mock, patch

import requests

from integrador import EQUIPO, enviar_medicion, consultar_mediciones, convertir_fecha


def respuesta(codigo, cuerpo='{"mensaje": "resultado simulado"}'):
    resultado = requests.Response()
    resultado.status_code = codigo
    resultado._content = cuerpo.encode("utf-8")
    resultado.encoding = "utf-8"
    return resultado


class PruebasHTTP(unittest.TestCase):
    def setUp(self):
        self.medicion = {
            "ciudad": "Bogota", "pais": "CO", "latitud": 4.7,
            "longitud": -74.1, "temperatura_c": 20, "humedad": 50,
            "viento_kmh": 0, "fecha_hora": "2026-09-01T06:00:00",
            "origen": "proveedor_a", "id_interno": "no-enviar",
        }
        self.sesion = Mock()

    def test_201_envia_solo_contrato_y_equipo(self):
        self.sesion.post.return_value = respuesta(201)
        resultado = enviar_medicion(self.sesion, self.medicion)
        self.assertEqual(resultado["estado"], "aceptado_api")
        argumentos = self.sesion.post.call_args.kwargs
        self.assertNotIn("id_interno", argumentos["json"])
        self.assertEqual(len(argumentos["json"]), 9)
        self.assertEqual(argumentos["headers"]["X-Equipo"], EQUIPO)
        self.assertFalse(argumentos["allow_redirects"])

    def test_4xx_no_se_reintentan(self):
        for codigo in (400, 409, 422, 429):
            with self.subTest(codigo=codigo):
                self.sesion.reset_mock()
                self.sesion.post.return_value = respuesta(codigo)
                resultado = enviar_medicion(self.sesion, self.medicion)
                self.assertEqual(resultado["estado"], "rechazado_api")
                self.assertEqual(self.sesion.post.call_count, 1)

    @patch("integrador.time.sleep")
    def test_5xx_se_recupera_en_tercer_intento(self, dormir):
        self.sesion.post.side_effect = [respuesta(500), respuesta(503), respuesta(201)]
        resultado = enviar_medicion(self.sesion, self.medicion)
        self.assertEqual(resultado["estado"], "aceptado_api")
        self.assertEqual(len(resultado["intentos"]), 3)
        self.assertEqual(dormir.call_count, 2)

    @patch("integrador.time.sleep")
    def test_fallos_transitorios_se_limitan_a_tres(self, dormir):
        for fallo in (requests.Timeout("timeout"), requests.ConnectionError("sin conexión"), respuesta(503)):
            with self.subTest(fallo=str(fallo)):
                self.sesion.reset_mock()
                self.sesion.post.side_effect = [fallo, fallo, fallo]
                resultado = enviar_medicion(self.sesion, self.medicion)
                self.assertEqual(resultado["estado"], "error_comunicacion")
                self.assertEqual(self.sesion.post.call_count, 3)

    def test_respuesta_no_json_se_conserva_sin_reintento(self):
        self.sesion.post.return_value = respuesta(201, '<html>Error</html>')
        resultado = enviar_medicion(self.sesion, self.medicion)
        self.assertEqual(resultado["estado"], "error_comunicacion")
        self.assertEqual(resultado["intentos"][0]["respuesta_texto"], '<html>Error</html>')
        self.assertEqual(self.sesion.post.call_count, 1)

    def test_codigo_inesperado_no_interrumpe_el_programa(self):
        self.sesion.post.return_value = respuesta(302)
        resultado = enviar_medicion(self.sesion, self.medicion)
        self.assertEqual(resultado["estado"], "error_comunicacion")
        self.assertEqual(self.sesion.post.call_count, 1)

    def test_get_usa_parametro_equipo_sin_post(self):
        cuerpo = {"equipo": EQUIPO, "total": 0, "mediciones": []}
        self.sesion.get.return_value = respuesta(200, json.dumps(cuerpo))
        consulta = consultar_mediciones(self.sesion)
        self.assertTrue(consulta["exitosa"])
        self.assertEqual(self.sesion.get.call_args.kwargs["params"], {"equipo": EQUIPO})
        self.sesion.post.assert_not_called()

    def test_get_rechaza_equipo_o_total_inconsistentes(self):
        for cuerpo in ({"equipo": "OTRO", "total": 0, "mediciones": []},
                       {"equipo": EQUIPO, "total": 1, "mediciones": []}):
            self.sesion.get.return_value = respuesta(200, json.dumps(cuerpo))
            self.assertFalse(consultar_mediciones(self.sesion)["exitosa"])

    @patch("integrador.time.sleep")
    def test_get_reintenta_503_pero_no_400(self, dormir):
        self.sesion.get.side_effect = [respuesta(503), respuesta(400)]
        consulta = consultar_mediciones(self.sesion)
        self.assertFalse(consulta["exitosa"])
        self.assertEqual(self.sesion.get.call_count, 2)

    def test_get_no_json_no_produce_traceback(self):
        self.sesion.get.return_value = respuesta(200, '<html>Error</html>')
        self.assertFalse(consultar_mediciones(self.sesion)["exitosa"])

    def test_fecha_b_asume_zona_y_a_la_conserva(self):
        self.assertEqual(convertir_fecha("01/09/2026 06:00", "proveedor_b"),
                         "2026-09-01T06:00:00-05:00")
        self.assertEqual(convertir_fecha("2026-09-01T06:00:00+02:00", "proveedor_a"),
                         "2026-09-01T06:00:00+02:00")


if __name__ == "__main__":
    unittest.main()
