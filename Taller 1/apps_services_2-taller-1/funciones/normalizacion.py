"""Transformación de los proveedores al contrato institucional."""

import math
from datetime import datetime, timedelta, timezone

ZONA_PROVEEDOR_B = timezone(timedelta(hours=-5))  # Suposición: hora colombiana.


def convertir_numero(valor, campo):
    """Convierte números sin reemplazar datos ausentes o inválidos por cero."""
    if isinstance(valor, bool) or not isinstance(valor, (str, int, float)):
        raise ValueError(f"{campo}: no es un número convertible: {valor!r}.")
    try:
        numero = float(valor)
    except (ValueError, OverflowError) as error:
        raise ValueError(f"{campo}: no se puede convertir {valor!r}.") from error
    if not math.isfinite(numero):
        raise ValueError(f"{campo}: se requiere un número finito.")
    return numero


def convertir_texto(valor, campo):
    """Los textos vacíos quedan pendientes de validación local."""
    if not isinstance(valor, str):
        raise ValueError(f"{campo}: se esperaba texto, se recibió {valor!r}.")
    return valor.strip()


def convertir_fecha(valor, origen):
    """Conserva la zona de A y asume hora colombiana (-05:00) para B."""
    texto = convertir_texto(valor, "fecha_hora")
    try:
        if origen == "proveedor_a":
            if "T" not in texto:
                raise ValueError("Falta la hora en formato ISO 8601.")
            fecha = datetime.fromisoformat(texto)
        else:
            fecha = datetime.strptime(texto, "%d/%m/%Y %H:%M")
            fecha = fecha.replace(tzinfo=ZONA_PROVEEDOR_B)
    except ValueError as error:
        raise ValueError(f"fecha_hora: fecha no interpretable: {valor!r}.") from error
    return fecha.isoformat()


def normalizar_proveedor_a(registro):
    """Aplana el JSON y convierte Fahrenheit a Celsius y m/s a km/h."""
    estacion = registro["station"]
    ubicacion = registro["location"]
    mediciones = registro["measurements"]
    return {
        "ciudad": convertir_texto(estacion["city_name"], "ciudad"),
        "pais": convertir_texto(estacion["country_code"], "pais"),
        "latitud": convertir_numero(ubicacion["lat"], "latitud"),
        "longitud": convertir_numero(ubicacion["lon"], "longitud"),
        "temperatura_c": (convertir_numero(mediciones["temperature_f"], "temperatura_c") - 32) * 5 / 9,
        "humedad": convertir_numero(mediciones["relative_humidity"], "humedad"),
        "viento_kmh": convertir_numero(mediciones["wind_speed_ms"], "viento_kmh") * 3.6,
        "fecha_hora": convertir_fecha(registro["observed_at"], "proveedor_a"),
        "origen": "proveedor_a",
    }


def normalizar_proveedor_b(registro):
    """Renombra las columnas del CSV y convierte sus valores de texto."""
    if None in registro or any(valor is None for valor in registro.values()):
        raise ValueError("Fila CSV con cantidad de columnas incorrecta.")
    return {
        "ciudad": convertir_texto(registro["municipality"], "ciudad"),
        "pais": convertir_texto(registro["country"], "pais"),
        "latitud": convertir_numero(registro["latitude_deg"], "latitud"),
        "longitud": convertir_numero(registro["longitude_deg"], "longitud"),
        "temperatura_c": convertir_numero(registro["temp_celsius"], "temperatura_c"),
        "humedad": convertir_numero(registro["humidity_pct"], "humedad"),
        "viento_kmh": convertir_numero(registro["wind_kmh"], "viento_kmh"),
        "fecha_hora": convertir_fecha(registro["measurement_time"], "proveedor_b"),
        "origen": "proveedor_b",
    }


def normalizar_registros(registros, origen):
    """Normaliza cada registro y conserva su identificador y resultado."""
    normalizador = {
        "proveedor_a": normalizar_proveedor_a,
        "proveedor_b": normalizar_proveedor_b,
    }[origen]
    campo_id = "provider_record_id" if origen == "proveedor_a" else "record_code"
    normalizadas = []
    resultados = []
    for posicion, registro in enumerate(registros, start=1):
        resultado = {
            "id_interno": f"{origen}:{posicion}",
            "id_proveedor": registro.get(campo_id) if isinstance(registro, dict) else None,
            "origen": origen,
            "posicion": posicion,
        }
        try:
            if not isinstance(registro, dict):
                raise ValueError("El registro debe ser un objeto.")
            datos = normalizador(registro)
            for campo in ("temperatura_c", "viento_kmh"):
                convertir_numero(datos[campo], campo)
        except (ValueError, KeyError, TypeError) as error:
            resultado["estado"] = "error_normalizacion"
            resultado["detalle"] = (
                f"Falta el campo {error.args[0]!r}." if isinstance(error, KeyError)
                else str(error)
            )
        else:
            normalizadas.append(datos)
            resultado["estado"] = "normalizado"
            resultado["datos"] = datos
        resultados.append(resultado)
    return normalizadas, resultados
