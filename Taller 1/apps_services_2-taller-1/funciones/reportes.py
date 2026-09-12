"""Escritura de evidencias JSON."""

import json


def guardar_json(ruta, contenido):
    """Guarda las evidencias de normalización en UTF-8."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8") as archivo:
        json.dump(contenido, archivo, ensure_ascii=False, indent=2, allow_nan=False)
        archivo.write("\n")
