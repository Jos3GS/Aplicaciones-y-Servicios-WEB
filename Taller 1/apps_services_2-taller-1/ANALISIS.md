# Análisis del taller: integración de datos meteorológicos

**Equipo:** `EQUIPO-08-APPSWEB`  
**API:** `https://appsweb.quantaiot.co`  
**Ejecución documentada:** 12 de septiembre de 2026; consulta final a las 11:43:50, hora colombiana.

## 1. Diferencias entre los contratos

El proveedor A entrega un JSON con una lista `records` y objetos anidados para
estación, ubicación y mediciones. Sus valores numéricos normalmente ya tienen
tipo numérico. El proveedor B entrega un CSV separado por punto y coma; sus
columnas se leen como texto. Cada fuente contiene 200 registros.

Además de los nombres y la estructura, cambian las unidades de temperatura y
viento, el formato de fecha y la representación del origen. El contrato
institucional exige un objeto plano con nueve campos obligatorios.

| Campo institucional y tipo | Proveedor A | Proveedor B | Transformación necesaria |
|---|---|---|---|
| `ciudad`: string | `station.city_name`: texto | `municipality`: texto | Renombrar y quitar espacios exteriores. |
| `pais`: string | `station.country_code`: texto | `country`: texto | Conservar el código `CO`; el contrato no exige el nombre completo. |
| `latitud`: number, grados | `location.lat`: número | `latitude_deg`: texto | Extraer de A; convertir a número en B. |
| `longitud`: number, grados | `location.lon`: número | `longitude_deg`: texto | Extraer de A; convertir a número en B. |
| `temperatura_c`: number, °C | `measurements.temperature_f`: número, °F | `temp_celsius`: texto, °C | A: `(°F - 32) × 5 / 9`; B: conversión numérica. |
| `humedad`: number, % | `measurements.relative_humidity`: número, % | `humidity_pct`: texto, % | Conservar unidad; convertir el texto de B a número. |
| `viento_kmh`: number, km/h | `measurements.wind_speed_ms`: número, m/s | `wind_kmh`: texto, km/h | A: multiplicar por `3.6`; B: conversión numérica. |
| `fecha_hora`: string, ISO 8601 | `observed_at`: ISO 8601 con desplazamiento | `measurement_time`: `DD/MM/AAAA HH:MM`, sin zona | Conservar la zona de A; interpretar B y asignar `-05:00`. |
| `origen`: string | `source`: `weather_provider_a` | `origin_code`: `PB` | Asignar `proveedor_a` o `proveedor_b` según el archivo de procedencia. |

## 2. Transformaciones y decisiones sobre los datos

Las funciones de normalización construyen un nuevo objeto sin modificar los
archivos originales. Por ejemplo, `66.1 °F` se convierte aproximadamente en
`18.9444 °C` y `8.47 m/s` en `30.492 km/h`. No se redondean los resultados para
enviarlos porque el contrato no establece una precisión obligatoria.

Para B se asume que las horas corresponden a Colombia (`UTC-05:00`), ya que el
archivo no informa zona horaria. Es una suposición explícita, configurable en
`ZONA_PROVEEDOR_B`: `01/09/2026 06:00` pasa a
`2026-09-01T06:00:00-05:00`. No se cambia la hora del reloj ni se interpreta como
UTC. Los metadatos del proveedor y los identificadores de trazabilidad no se
incluyen en el body HTTP.

## 3. Errores encontrados antes del envío

Se distinguen errores de conversión de infracciones de las reglas del contrato.
Los campos ausentes, las temperaturas no convertibles y las fechas imposibles
producen errores de normalización. Un texto vacío o un número fuera de rango
puede normalizarse, pero se rechaza localmente. No se inventan valores para
completar los registros.

| Registro | Problema observado | Clasificación |
|---|---|---|
| A-0082 | Temperatura `"N/A"` | Error de normalización. |
| A-0150 | Falta `country_code` | Error de normalización. |
| A-0173 | Temperatura `null` | Error de normalización. |
| B-0171 | Fecha `31/13/2026 28:75` | Error de normalización. |
| A-0015 | Humedad `108.4 %` | Rechazo local. |
| B-0115 | Viento `-7.4 km/h` | Rechazo local. |
| B-0128 | Ciudad vacía | Rechazo local. |

Los nueve errores de normalización quedan identificados en el reporte y se
excluyen de `normalizadas.json`. Los once rechazados localmente permanecen en
ese archivo, pero no se envían.

## 4. Validación local frente a validación del servidor

La validación local revisa tipos, textos obligatorios, rangos de coordenadas,
humedad, viento, fecha y origen. No impone un rango de temperatura que el
contrato no define. El servidor también comprueba condiciones que dependen de
su estado, como la autorización del equipo y la existencia de duplicados.

En una ejecución anterior, B superó la validación local con fechas ISO 8601 sin
zona, pero recibió HTTP 422: el servidor exigía incluirla. Ese requisito no
aparece explícitamente en el contrato suministrado. Después de documentar y
aplicar la suposición `-05:00`, sus 190 registros válidos fueron aceptados.
La evidencia anterior se conserva en
[`salida/historial/20260912-114251-393/`](salida/historial/20260912-114251-393/).

## 5. Decisión de implementación más importante

Separar lectura, normalización, validación y comunicación permite explicar qué
ocurrió con cada registro. Estas responsabilidades están en módulos de la carpeta
`funciones/`; `integrador.py` conserva la configuración y coordina el flujo.
El reporte conserva el identificador del proveedor,
un identificador interno basado en fuente y posición, los datos normalizados y
el historial HTTP cuando hubo envío. Así, un rechazo no se confunde con una
pérdida de información.

Los `4xx` no se reintentan. Los `5xx`, timeout y pérdidas de conexión permiten
hasta tres intentos, con esperas de uno y dos segundos. Cada respuesta conserva
su código y contenido. Un `409` se registra como rechazo por conflicto, incluso
si sigue a un timeout; no se supone que el intento anterior fue aceptado.

## Evidencia resumida de la ejecución real

Fuente: [`salida/reporte.json`](salida/reporte.json). `enviados` cuenta registros
con intento de envío, no el número de solicitudes o reintentos.

| Resultado | Cantidad |
|---|---:|
| Procesados | 400 |
| Normalizados | 391 |
| Errores de normalización | 9 |
| Válidos localmente | 380 |
| Rechazados localmente | 11 |
| Enviados | 380 |
| Aceptados por la API, HTTP 201 (B) | 190 |
| Rechazados por la API, HTTP 409 (A) | 190 |
| Errores de comunicación | 0 |

Respuesta real para B-0001, **HTTP 201**:

```json
{"id":960,"estado":"aceptada","mensaje":"Medición registrada correctamente"}
```

Respuesta real para A-0001, **HTTP 409**:

```json
{"detail":"La medición ya existe"}
```

La consulta `GET /api/v1/mediciones?equipo=EQUIPO-08-APPSWEB` respondió
**HTTP 200**. La respuesta completa está en
[`salida/consulta.json`](salida/consulta.json) y dentro del reporte. Sus campos
de resumen son:

```json
{"equipo":"EQUIPO-08-APPSWEB","total":380}
```

La lista `mediciones`, omitida aquí por extensión, contiene 190 registros de A
y 190 de B. Los de A ya estaban almacenados antes de esta ejecución; por eso
el total consultado es 380, aunque solo hubo 190 nuevas aceptaciones.

## Pruebas automatizadas

La suite se ejecutó con `python -m pytest -q`: **31 pruebas y 7 subpruebas
aprobadas**. Incluye transformación de ambos proveedores, conversión de
unidades, registros válidos e inválidos, límites inclusivos, trazabilidad y
conservación de rechazados. Las pruebas HTTP simulan respuestas, reintentos y
consultas; `tests/conftest.py` bloquea solicitudes reales durante `pytest`.
Una prueba adicional del flujo completo utiliza archivos temporales y una API
simulada para comprobar la conexión entre módulos después de la refactorización.

Para reproducirlas con el entorno del proyecto activo: instalar
`requirements.txt` y ejecutar `pytest` desde la carpeta del taller.
