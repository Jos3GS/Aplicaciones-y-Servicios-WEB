"""Validación local y clasificación de las mediciones."""

import math
from datetime import datetime


def validar_medicion(medicion):
    """Devuelve todas las infracciones del contrato, sin modificar la medición.

    Una lista vacía significa que el registro es válido localmente. Esto no
    garantiza que el servidor lo acepte cuando implementemos el envío HTTP.
    """
    if not isinstance(medicion, dict):
        return ["La medición debe ser un objeto."]

    errores = []
    for campo in ("ciudad", "pais"):
        valor = medicion.get(campo)
        if not isinstance(valor, str) or not valor.strip():
            errores.append(f"{campo}: debe ser un texto no vacío.")

    # Los límites son inclusivos. La temperatura no tiene un rango en el contrato.
    limites = {
        "latitud": (-90, 90),
        "longitud": (-180, 180),
        "temperatura_c": (None, None),
        "humedad": (0, 100),
        "viento_kmh": (0, None),
    }
    for campo, (minimo, maximo) in limites.items():
        valor = medicion.get(campo)
        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            errores.append(f"{campo}: debe ser un número.")
            continue
        if isinstance(valor, float) and not math.isfinite(valor):
            errores.append(f"{campo}: debe ser un número finito.")
            continue
        if minimo is not None and valor < minimo:
            errores.append(f"{campo}: {valor} es menor que {minimo}.")
        if maximo is not None and valor > maximo:
            errores.append(f"{campo}: {valor} es mayor que {maximo}.")

    fecha = medicion.get("fecha_hora")
    try:
        if not isinstance(fecha, str) or "T" not in fecha:
            raise ValueError("Se requiere fecha y hora.")
        datetime.fromisoformat(fecha)
    except ValueError:
        errores.append("fecha_hora: debe ser una fecha y hora válida en ISO 8601.")

    if medicion.get("origen") not in ("proveedor_a", "proveedor_b"):
        errores.append("origen: debe ser proveedor_a o proveedor_b.")
    return errores


def validar_resultados(resultados):
    """Clasifica los normalizados y devuelve los registros aptos para futuro envío."""
    validos = []
    rechazados = []
    for resultado in resultados:
        if resultado["estado"] == "error_normalizacion":
            continue
        errores = validar_medicion(resultado["datos"])
        resultado["errores_validacion"] = errores
        if errores:
            resultado["estado"] = "rechazado_localmente"
            rechazados.append(resultado)
        else:
            resultado["estado"] = "valido_localmente"
            validos.append(resultado)
    return validos, rechazados
