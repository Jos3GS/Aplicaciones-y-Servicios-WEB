"""Lectura de los archivos originales JSON y CSV."""

import csv
import json


def leer_proveedor_a(ruta):
    """Lee la lista records del JSON sin transformar sus valores."""
    with ruta.open(encoding="utf-8-sig") as archivo:
        contenido = json.load(archivo)

    if not isinstance(contenido, dict) or not isinstance(
        contenido.get("records"), list
    ):
        raise ValueError("El JSON debe contener una lista llamada 'records'.")

    # Retornamos los registros y una lista vacía de errores para estandarizar
    return contenido["records"], []


def leer_proveedor_b(ruta):
    """Lee el CSV separado por ; y conserva las filas con columnas defectuosas."""
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
                # Optimización sintáctica: búsqueda directa, más limpia y rápida
                if None in fila or None in fila.values():
                    errores.append({
                        "registro": posicion,
                        "linea": lector.line_num,
                        "detalle": "La cantidad de columnas no coincide con el encabezado.",
                    })
                else:
                    registros.append(fila)
        except csv.Error as error:
            errores.append({
                "linea": lector.line_num,
                "detalle": f"Lectura CSV incompleta: {error}",
            })

    return registros, errores