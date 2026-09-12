"""Punto de entrada: configura y coordina las etapas del taller."""

import csv
from pathlib import Path

from funciones.envios import enviar_registros, guardar_consulta_final
from funciones.lectura import leer_proveedor_a, leer_proveedor_b
from funciones.normalizacion import normalizar_registros
from funciones.reportes import guardar_json
from funciones.validacion import validar_resultados

URL_BASE = "https://appsweb.quantaiot.co"
EQUIPO = "EQUIPO-08-APPSWEB"
TIMEOUT_HTTP = (5, 20)  # Segundos máximos de conexión y de espera de datos.
MAX_INTENTOS = 3

DIRECTORIO_BASE = Path(__file__).resolve().parent
DIRECTORIO_DATOS = DIRECTORIO_BASE / "datos"
DIRECTORIO_SALIDA = DIRECTORIO_BASE / "salida"


def main():
    """Lee las fuentes, normaliza, valida y guarda la evidencia."""
    config_api = dict(url_base=URL_BASE, equipo=EQUIPO, timeout=TIMEOUT_HTTP, max_intentos=MAX_INTENTOS)

    # Definición dinámica de fuentes. Si llega un nuevo proveedor, solo se añade aquí.
    fuentes = [
        ("proveedor_a", DIRECTORIO_DATOS / "proveedor_a.json", leer_proveedor_a),
        ("proveedor_b", DIRECTORIO_DATOS / "proveedor_b.csv", leer_proveedor_b),
    ]

    normalizadas = []
    resultados = []
    errores_lectura = []
    total_identificados = 0

    # 1. Extracción y Normalización unificadas
    for origen, ruta, funcion_lectura in fuentes:
        try:
            registros, errores_fuente = funcion_lectura(ruta)
            total_identificados += len(registros)

            # Recolectar errores estructurales devueltos por el lector (ej. CSV mal formado)
            for error in errores_fuente:
                errores_lectura.append(f"{origen} (Línea {error.get('linea', '?')}): {error.get('detalle', '')}")

            # Normalizar de inmediato
            norm_fuente, res_fuente = normalizar_registros(registros, origen)
            normalizadas.extend(norm_fuente)
            resultados.extend(res_fuente)

        except (OSError, UnicodeError, ValueError, csv.Error) as error:
            errores_lectura.append(f"{origen}: {error}")

    print(f"Total de registros identificados: {total_identificados}")

    if errores_lectura:
        print("Se encontraron errores de lectura; el conteo puede ser parcial:")
        for error in errores_lectura:
            print(f"- {error}")
        return 1

    # 2. Validación Local
    validos, rechazados = validar_resultados(resultados)
    errores_normalizacion = [r for r in resultados if r["estado"] == "error_normalizacion"]

    reporte = {
        "etapa": "validacion_local",
        "procesados": total_identificados,
        "normalizados": len(normalizadas),
        "errores_normalizacion": len(errores_normalizacion),
        "validos_localmente": len(validos),
        "rechazados_localmente": len(rechazados),
        "resultados": resultados,
    }

    # 3. Guardado de Evidencias Iniciales
    try:
        guardar_json(DIRECTORIO_SALIDA / "normalizadas.json", normalizadas)
        guardar_json(DIRECTORIO_SALIDA / "reporte.json", reporte)
    except (OSError, ValueError) as error:
        print(f"No se pudo guardar la evidencia: {error}")
        return 1

    print(f"Registros normalizados: {len(normalizadas)}")
    print(f"Errores de normalización: {len(errores_normalizacion)}")
    for resultado in errores_normalizacion:
        identificador = resultado["id_proveedor"] or resultado["id_interno"]
        print(f"- {identificador}: {resultado['detalle']}")

    print(f"Registros válidos localmente: {len(validos)}")
    print(f"Registros rechazados localmente: {len(rechazados)}")
    for resultado in rechazados:
        identificador = resultado["id_proveedor"] or resultado["id_interno"]
        print(f"- {identificador}: {'; '.join(resultado['errores_validacion'])}")

    # 4. Integración HTTP
    if not EQUIPO.strip():
        print("Configura EQUIPO antes de realizar los envíos.")
        return 1

    print(f"\nIniciando envíos con el equipo {EQUIPO}.", flush=True)
    try:
        enviar_registros(validos, reporte, DIRECTORIO_SALIDA, **config_api)
    except (OSError, ValueError) as error:
        print(f"Se detuvieron los envíos porque no se pudo guardar la evidencia: {error}")
        return 1

    print(f"Enviados: {reporte['enviados']}")
    print(f"Aceptados por la API: {reporte['aceptados_api']}")
    print(f"Rechazados por la API: {reporte['rechazados_api']}")
    print(f"Errores de comunicación: {reporte['errores_comunicacion']}")

    # 5. Consulta Final
    try:
        consulta = guardar_consulta_final(reporte, DIRECTORIO_SALIDA, **config_api)
    except (OSError, ValueError) as error:
        print(f"No se pudo guardar la consulta final: {error}")
        return 1

    print("Respuestas y consulta final guardadas en salida/reporte.json.")
    return 1 if reporte["errores_comunicacion"] or not consulta["exitosa"] else 0


if __name__ == "__main__":
    raise SystemExit(main())