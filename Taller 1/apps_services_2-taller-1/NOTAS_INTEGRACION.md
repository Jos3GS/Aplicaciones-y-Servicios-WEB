# Decisiones de integración

El proveedor B entrega fechas sin zona horaria. Se asume que representan hora local colombiana (UTC-05:00). Se agrega ese
desplazamiento sin cambiar la hora de la medición. Por ejemplo,
`01/09/2026 06:00` se normaliza como `2026-09-01T06:00:00-05:00`.

Esta suposición se configura en `ZONA_PROVEEDOR_B`, dentro de
`funciones/normalizacion.py`. No se modifica el CSV
original. El proveedor A conserva el desplazamiento incluido en sus datos.

La API real rechazó con HTTP 422 las fechas de B sin zona horaria. El contrato
entregado exige una fecha válida, pero no describe explícitamente este requisito
adicional del servidor. Se conserva esa diferencia como evidencia de validación
local frente a validación del servidor.

El ajuste afecta las próximas normalizaciones. Los archivos de la ejecución
anterior conservan los datos efectivamente enviados y las respuestas recibidas;
no se reescriben para aparentar que aquella ejecución utilizó la nueva zona.

La consulta GET puede incluir mediciones de ejecuciones anteriores del mismo
equipo. Su total no equivale necesariamente a los aceptados en una sola ejecución.

## Organización del código

`integrador.py` conserva `URL_BASE`, `EQUIPO`, los tiempos de espera, las rutas y
la función `main()`. Sigue ejecutándose con `python integrador.py`.

La carpeta `funciones/` separa las responsabilidades:

- `lectura.py`: lectura del JSON y CSV originales.
- `normalizacion.py`: transformaciones, fechas y trazabilidad.
- `validacion.py`: reglas locales del contrato.
- `api.py`: peticiones POST y GET, respuestas y reintentos.
- `envios.py`: coordinación de envíos y consulta, con actualización del reporte.
- `reportes.py`: escritura de archivos JSON.

Los módulos HTTP reciben la configuración por parámetros. No importan
`integrador.py`, de modo que no hay dependencia circular ni otra copia del ID.
