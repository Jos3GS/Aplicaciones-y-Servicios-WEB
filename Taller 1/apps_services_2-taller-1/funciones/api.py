"""Peticiones HTTP, respuestas y reintentos; configuración recibida por parámetros."""

import json
import time
from datetime import datetime, timezone

import requests

SIGNIFICADOS_HTTP = {
    400: "Solicitud incorrecta",
    409: "Conflicto",
    422: "Datos no aceptados"
}


def enviar_medicion(sesion, medicion, *, url_base, equipo, timeout=(5, 20), max_intentos=3):
    """Envía únicamente el body institucional y conserva cada intento HTTP.

    Solo reintenta 5xx, timeout y pérdida de conexión. Un 409 es un conflicto,
    incluso si aparece después de un timeout; no prueba que este envío se aceptó.
    """
    campos = (
        "ciudad", "pais", "latitud", "longitud", "temperatura_c",
        "humedad", "viento_kmh", "fecha_hora", "origen",
    )
    body = {campo: medicion[campo] for campo in campos}
    historial = []
    estado = "error_comunicacion"
    for numero in range(1, max_intentos + 1):
        intento = {"numero": numero}
        reintentar = False
        try:
            respuesta = sesion.post(
                f"{url_base.rstrip('/')}/api/v1/mediciones",
                headers={"Content-Type": "application/json", "X-Equipo": equipo},
                json=body,
                timeout=timeout,
                allow_redirects=False,
            )
            codigo = respuesta.status_code
            intento["codigo_http"] = codigo
            intento["respuesta_texto"] = respuesta.text
            try:
                contenido = respuesta.json()
                # Comprobar que se podrá guardar como JSON estricto en el reporte.
                json.dumps(contenido, allow_nan=False)
                intento["respuesta_json"] = contenido
                objeto_json = isinstance(contenido, dict)
            except ValueError:
                objeto_json = False
            if not objeto_json:
                intento["advertencia"] = "La respuesta no es un objeto JSON válido."

            if codigo == 201:
                estado = "aceptado_api" if objeto_json else "error_comunicacion"
            elif 400 <= codigo < 500:
                estado = "rechazado_api"
                intento["significado"] = SIGNIFICADOS_HTTP.get(codigo, "Rechazo HTTP del cliente")
            elif 500 <= codigo < 600:
                reintentar = True
            else:
                intento["advertencia"] = f"Código HTTP inesperado: {codigo}."
        except (requests.Timeout, requests.ConnectionError) as error:
            intento["error"] = str(error)
            reintentar = True
        except requests.RequestException as error:
            intento["error"] = str(error)

        historial.append(intento)
        if not reintentar or numero == max_intentos:
            break
        time.sleep(numero)  # Esperas de 1 y 2 segundos entre intentos.

    return {"estado": estado, "intentos": historial}


def consultar_mediciones(sesion, *, url_base, equipo, timeout=(5, 20), max_intentos=3):
    """Consulta las mediciones del equipo y conserva la respuesta sin alterarla."""
    historial = []
    for numero in range(1, max_intentos + 1):
        intento = {"numero": numero}
        reintentar = False
        exito = False
        try:
            respuesta = sesion.get(
                f"{url_base.rstrip('/')}/api/v1/mediciones",
                params={"equipo": equipo},
                timeout=timeout,
                allow_redirects=False,
            )
            intento["codigo_http"] = respuesta.status_code
            intento["respuesta_texto"] = respuesta.text
            try:
                contenido = respuesta.json()
                json.dumps(contenido, allow_nan=False)
                intento["respuesta_json"] = contenido
                exito = respuesta.status_code == 200 and isinstance(contenido, dict)
                if not isinstance(contenido, dict):
                    intento["error"] = "La respuesta no es un objeto JSON."
                elif respuesta.status_code == 200:
                    mediciones = contenido.get("mediciones")
                    total = contenido.get("total")
                    exito = (
                        contenido.get("equipo") == equipo
                        and isinstance(mediciones, list)
                        and all(isinstance(medicion, dict) for medicion in mediciones)
                        and type(total) is int
                        and total == len(mediciones)
                    )
                    if not exito:
                        intento["error"] = "Equipo, total o mediciones inconsistentes en la consulta."
            except ValueError:
                intento["error"] = "La respuesta no contiene JSON válido."
            reintentar = 500 <= respuesta.status_code < 600
        except (requests.Timeout, requests.ConnectionError) as error:
            intento["error"] = str(error)
            reintentar = True
        except requests.RequestException as error:
            intento["error"] = str(error)
        historial.append(intento)
        if not reintentar or numero == max_intentos:
            return {
                "equipo": equipo,
                "url_base": url_base,
                "fecha_consulta": datetime.now(timezone.utc).isoformat(),
                "exitosa": exito,
                "intentos": historial,
            }
        time.sleep(numero)
