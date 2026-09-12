"""Cliente integrador meteorológico: lectura, normalización y validación local."""

import csv
import json
import math
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests


URL_BASE = "https://appsweb.quantaiot.co"
EQUIPO = "EQUIPO-08-APPSWEB"
ZONA_PROVEEDOR_B = timezone(timedelta(hours=-5))  # Suposición: hora local colombiana.
TIMEOUT_HTTP = (5, 20)  # Segundos máximos de conexión y de espera de datos.
MAX_INTENTOS = 3

DIRECTORIO_BASE = Path(__file__).resolve().parent
DIRECTORIO_DATOS = DIRECTORIO_BASE / "datos"
DIRECTORIO_SALIDA = DIRECTORIO_BASE / "salida"


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


def enviar_medicion(sesion, medicion):
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
    for numero in range(1, MAX_INTENTOS + 1):
        intento = {"numero": numero}
        reintentar = False
        try:
            respuesta = sesion.post(
                f"{URL_BASE.rstrip('/')}/api/v1/mediciones",
                headers={"Content-Type": "application/json", "X-Equipo": EQUIPO},
                json=body,
                timeout=TIMEOUT_HTTP,
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
                intento["significado"] = {
                    400: "Solicitud incorrecta",
                    409: "Conflicto",
                    422: "Datos no aceptados",
                }.get(codigo, "Rechazo HTTP del cliente")
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
        if not reintentar or numero == MAX_INTENTOS:
            break
        time.sleep(numero)  # Esperas de 1 y 2 segundos entre intentos.

    return {"estado": estado, "intentos": historial}


def enviar_registros(validos, reporte):
    """Envía los válidos y guarda el avance tras cada registro.

    'enviados' cuenta registros con intento de envío, no solicitudes ni reintentos.
    """
    reporte.update({
        "etapa": "envios_en_curso",
        "equipo": EQUIPO,
        "url_base": URL_BASE,
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
    guardar_json(DIRECTORIO_SALIDA / "reporte.json", reporte)
    with requests.Session() as sesion:
        for posicion, resultado in enumerate(validos, start=1):
            envio = enviar_medicion(sesion, resultado["datos"])
            resultado.update(envio)
            reporte["enviados"] += 1
            reporte[contadores[envio["estado"]]] += 1
            guardar_json(DIRECTORIO_SALIDA / "reporte.json", reporte)
            identificador = resultado["id_proveedor"] or resultado["id_interno"]
            codigo = envio["intentos"][-1].get("codigo_http", "sin respuesta")
            print(f"[{posicion}/{len(validos)}] {identificador}: {envio['estado']} (HTTP {codigo})", flush=True)
    reporte["etapa"] = "envios_finalizados_consulta_pendiente"
    guardar_json(DIRECTORIO_SALIDA / "reporte.json", reporte)


def consultar_mediciones(sesion):
    """Consulta las mediciones del equipo y conserva la respuesta sin alterarla."""
    historial = []
    for numero in range(1, MAX_INTENTOS + 1):
        intento = {"numero": numero}
        reintentar = False
        exito = False
        try:
            respuesta = sesion.get(
                f"{URL_BASE.rstrip('/')}/api/v1/mediciones",
                params={"equipo": EQUIPO},
                timeout=TIMEOUT_HTTP,
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
                        contenido.get("equipo") == EQUIPO
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
        if not reintentar or numero == MAX_INTENTOS:
            return {
                "equipo": EQUIPO,
                "url_base": URL_BASE,
                "fecha_consulta": datetime.now(timezone.utc).isoformat(),
                "exitosa": exito,
                "intentos": historial,
            }
        time.sleep(numero)


def guardar_consulta_final(reporte):
    """Añade la consulta al reporte sin cambiar los resultados de los envíos."""
    if reporte.get("equipo") != EQUIPO or reporte.get("url_base") != URL_BASE:
        raise ValueError("El reporte y la configuración deben pertenecer al mismo equipo y API.")
    with requests.Session() as sesion:
        consulta = consultar_mediciones(sesion)
    guardar_json(DIRECTORIO_SALIDA / "consulta.json", consulta)
    reporte["consulta_final"] = consulta
    reporte["etapa"] = "consulta_finalizada" if consulta["exitosa"] else "consulta_fallida"
    guardar_json(DIRECTORIO_SALIDA / "reporte.json", reporte)
    codigo = consulta["intentos"][-1].get("codigo_http", "sin respuesta")
    print(f"Consulta final del equipo {EQUIPO}: HTTP {codigo}.")
    if consulta["exitosa"]:
        print(f"Mediciones almacenadas: {consulta['intentos'][-1]['respuesta_json']['total']}")
    return consulta


def guardar_json(ruta, contenido):
    """Guarda las evidencias de normalización en UTF-8."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8") as archivo:
        json.dump(contenido, archivo, ensure_ascii=False, indent=2, allow_nan=False)
        archivo.write("\n")


def leer_proveedor_a(ruta):
    """
    Lee la lista records del JSON sin transformar sus valores.
    :param ruta: Ruta del archivo con los registros en formato JSON
    :return:
    """

    with ruta.open(encoding="utf-8-sig") as archivo:
        contenido = json.load(archivo)

    if not isinstance(contenido, dict) or not isinstance(
        contenido.get("records"), list
    ):
        raise ValueError("El JSON debe contener una lista llamada 'records'.")

    return contenido["records"]


def leer_proveedor_b(ruta):
    """
    Lee el CSV separado por ; y conserva las filas con columnas defectuosas.
    Devuelve los registros y los errores de estructura detectados. Los valores
    vacíos o no numéricos se revisarán en los pasos posteriores del taller.

    :param ruta: Ruta del archivo con la información en formato CSV
    :return:
    """
    registros = []
    errores = []
    with ruta.open(encoding="utf-8-sig", newline="") as archivo:
        lector = csv.DictReader(archivo, delimiter=";", strict=True)
        if not lector.fieldnames:
            raise ValueError("El CSV no contiene un encabezado.")
        if len(set(lector.fieldnames)) != len(lector.fieldnames):
            raise ValueError("El CSV contiene nombres de columnas repetidos.")

        try:
            for posicion, fila in enumerate(lector, start=1):
                registros.append(fila)
                if None in fila or any(valor is None for valor in fila.values()):
                    errores.append({
                        "registro": posicion,
                        "linea": lector.line_num,
                        "detalle": "La cantidad de columnas no coincide con el encabezado.",
                    })
        except csv.Error as error:
            # Una comilla mal cerrada puede impedir delimitar las filas restantes.
            errores.append({
                "linea": lector.line_num,
                "detalle": f"Lectura CSV incompleta: {error}",
            })

    return registros, errores


def main():
    """
        Lee ambas fuentes, normaliza, valida y guarda la evidencia.
    """
    registros_a = []
    registros_b = []
    errores = []

    try:
        registros_a = leer_proveedor_a(DIRECTORIO_DATOS / "proveedor_a.json")
    except (OSError, UnicodeError, ValueError) as error:
        errores.append(f"Proveedor A: {error}")

    try:
        registros_b, errores_b = leer_proveedor_b(
            DIRECTORIO_DATOS / "proveedor_b.csv"
        )
        for error in errores_b:
            errores.append(f"Proveedor B, línea {error['linea']}: {error['detalle']}")
    except (OSError, UnicodeError, ValueError, csv.Error) as error:
        errores.append(f"Proveedor B: {error}")

    print(f"Registros del proveedor A: {len(registros_a)}")
    print(f"Registros del proveedor B: {len(registros_b)}")
    print(f"Total de registros identificados: {len(registros_a) + len(registros_b)}")

    if errores:
        print("Se encontraron errores de lectura; el conteo puede ser parcial:")
        for error in errores:
            print(f"- {error}")
        return 1

    normalizadas_a, resultados_a = normalizar_registros(registros_a, "proveedor_a")
    normalizadas_b, resultados_b = normalizar_registros(registros_b, "proveedor_b")
    normalizadas = normalizadas_a + normalizadas_b
    resultados = resultados_a + resultados_b
    errores_normalizacion = [
        resultado for resultado in resultados
        if resultado["estado"] == "error_normalizacion"
    ]
    reporte = {
        "etapa": "normalizacion",
        "procesados": len(registros_a) + len(registros_b),
        "normalizados": len(normalizadas),
        "errores_normalizacion": len(errores_normalizacion),
        "resultados": resultados,
    }
    try:
        guardar_json(DIRECTORIO_SALIDA / "normalizadas.json", normalizadas)
        guardar_json(DIRECTORIO_SALIDA / "reporte_normalizacion.json", reporte)
        validos, rechazados = validar_resultados(resultados)
        reporte.update({
            "etapa": "validacion_local",
            "validos_localmente": len(validos),
            "rechazados_localmente": len(rechazados),
        })
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
    if not EQUIPO.strip():
        print("Configura EQUIPO antes de realizar los envíos.")
        return 1
    print(f"Iniciando envíos con el equipo {EQUIPO}.", flush=True)
    try:
        enviar_registros(validos, reporte)
    except (OSError, ValueError) as error:
        print(f"Se detuvieron los envíos porque no se pudo guardar la evidencia: {error}")
        return 1
    print(f"Enviados: {reporte['enviados']}")
    print(f"Aceptados por la API: {reporte['aceptados_api']}")
    print(f"Rechazados por la API: {reporte['rechazados_api']}")
    print(f"Errores de comunicación: {reporte['errores_comunicacion']}")
    try:
        consulta = guardar_consulta_final(reporte)
    except (OSError, ValueError) as error:
        print(f"No se pudo guardar la consulta final: {error}")
        return 1
    print("Respuestas y consulta final guardadas en salida/reporte.json.")
    return 1 if reporte["errores_comunicacion"] or not consulta["exitosa"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
