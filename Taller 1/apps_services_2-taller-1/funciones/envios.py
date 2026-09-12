"""Coordinación de envíos, consulta final y actualización de reportes."""

import requests

from .api import consultar_mediciones, enviar_medicion
from .reportes import guardar_json


def enviar_registros(validos, reporte, directorio_salida, **config_api):
    """
    'enviados' cuenta registros con intento de envío, no solicitudes ni reintentos.
    Se utiliza un bloque try...finally para garantizar el guardado del reporte.
    """
    reporte.update({
        "etapa": "envios_en_curso",
        "equipo": config_api['equipo'],
        "url_base": config_api['url_base'],
        "enviados": 0,
        "aceptados_api": 0,
        "rechazados_api": 0,
        "errores_comunicacion": 0,
    })
    contadores = {
        "aceptado_api": "aceptados_api",
        "rechazado_api": "rechazados_api",
        "error_comunicacion": "errores_comunicacion",
    }
    # Solo guardamos el estado inicial una vez antes de empezar el bucle
    guardar_json(directorio_salida / "reporte.json", reporte)

    with requests.Session() as sesion:
        try:
            for posicion, resultado in enumerate(validos, start=1):
                envio = enviar_medicion(sesion, resultado["datos"], **config_api)
                resultado.update(envio)
                reporte["enviados"] += 1
                reporte[contadores[envio["estado"]]] += 1

                identificador = resultado["id_proveedor"] or resultado["id_interno"]
                codigo = envio["intentos"][-1].get("codigo_http", "sin respuesta")
                print(f"[{posicion}/{len(validos)}] {identificador}: {envio['estado']} (HTTP {codigo})", flush=True)

        finally:
            # Se ejecuta SIEMPRE: ya sea que termine con éxito,
            # ocurra una excepción, o presiones Ctrl+C a mitad de ejecución.
            reporte["etapa"] = "envios_finalizados_consulta_pendiente"
            guardar_json(directorio_salida / "reporte.json", reporte)


def guardar_consulta_final(reporte, directorio_salida, **config_api):
    """Añade la consulta al reporte sin cambiar los resultados de los envíos."""
    if reporte.get("equipo") != config_api['equipo'] or reporte.get("url_base") != config_api['url_base']:
        raise ValueError("El reporte y la configuración deben pertenecer al mismo equipo y API.")
    with requests.Session() as sesion:
        consulta = consultar_mediciones(sesion, **config_api)
    guardar_json(directorio_salida / "consulta.json", consulta)
    reporte["consulta_final"] = consulta
    reporte["etapa"] = "consulta_finalizada" if consulta["exitosa"] else "consulta_fallida"
    guardar_json(directorio_salida / "reporte.json", reporte)
    codigo = consulta["intentos"][-1].get("codigo_http", "sin respuesta")
    print(f"Consulta final del equipo {config_api['equipo']}: HTTP {codigo}.")
    if consulta["exitosa"]:
        print(f"Mediciones almacenadas: {consulta['intentos'][-1]['respuesta_json']['total']}")
    return consulta
