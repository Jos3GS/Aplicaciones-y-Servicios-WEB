# Análisis del taller: Integración de datos meteorológicos

**Equipo:** `EQUIPO-08-APPSWEB`  
**API:** `https://appsweb.quantaiot.co`  
**Ejecución documentada:** 12 de septiembre de 2026; consulta final a las 11:43:50 (Hora local Colombia).

## 1. Análisis y diferencias entre los contratos

Al contrastar las fuentes de datos con el contrato institucional, se evidenciaron diferencias arquitectónicas y de formato significativas. El **Proveedor A** entrega la información mediante un JSON jerárquico (anidado) con tipos de datos nativos, mientras que el **Proveedor B** suministra un archivo CSV plano donde todos los valores se leen inicialmente como cadenas de texto. Cada fuente procesada contiene 200 registros.

| Campo Institucional (Tipo) | Proveedor A | Proveedor B | Transformación Aplicada |
| :--- | :--- | :--- | :--- |
| `ciudad` (string) | `station.city_name` (texto) | `municipality` (texto) | Renombrar llave/columna y eliminar espacios en blanco (strip). |
| `pais` (string) | `station.country_code` (texto) | `country` (texto) | Extracción directa conservando el código `CO`. |
| `latitud` (number, grados) | `location.lat` (número) | `latitude_deg` (texto) | A: Extracción. B: Casting a `float`. |
| `longitud` (number, grados) | `location.lon` (número) | `longitude_deg` (texto) | A: Extracción. B: Casting a `float`. |
| `temperatura_c` (number, °C) | `measurements.temperature_f` (°F) | `temp_celsius` (texto, °C) | A: Aplicar fórmula $C = (F - 32) \times 5/9$. B: Casting a numérico. |
| `humedad` (number, %) | `measurements.relative_humidity` (número) | `humidity_pct` (texto) | A: Extracción. B: Casting a numérico. |
| `viento_kmh` (number, km/h)| `measurements.wind_speed_ms` (m/s) | `wind_kmh` (texto, km/h) | A: Multiplicar por 3.6. B: Casting a numérico. |
| `fecha_hora` (string, ISO 8601)| `observed_at` (ISO 8601 con offset) | `measurement_time` (DD/MM/AAAA HH:MM) | A: Conservar offset. B: Parsear e inyectar zona horaria local (`-05:00`). |
| `origen` (string) | `source` (`weather_provider_a`) | `origin_code` (`PB`) | Asignación estricta de `proveedor_a` o `proveedor_b` según el origen. |

## 2. Transformaciones y decisiones sobre los datos

El proceso de normalización actúa como un pipeline o tubería (`ETL` simplificado) que construye nuevos diccionarios de Python sin alterar las fuentes. Las conversiones matemáticas se realizan con precisión flotante estándar (por ejemplo, `66.1 °F` se normaliza a `18.9444 °C`) sin aplicar redondeos prematuros, respetando el contrato que no exige un límite de decimales.

Para la gestión del tiempo, **se asumió explícitamente que los registros del Proveedor B corresponden a la zona horaria de Colombia (`UTC-5`)**. En lugar de alterar la hora del reloj, el programa inyecta el offset de la zona (`2026-09-01T06:00:00-05:00`), garantizando que la API institucional reciba una marca de tiempo inequívoca y estandarizada en ISO 8601.

## 3. Errores encontrados antes del envío

Durante la fase de validación, el cliente diferenció estrictamente entre un **error de normalización** (datos irrecuperables por estructura o tipos incompatibles) y un **rechazo local** (datos estructuralmente sanos, pero que violan las reglas de negocio del contrato). No se utilizaron técnicas de imputación (ej. rellenar nulos con ceros) para garantizar la integridad de las mediciones reales.

| Trazabilidad | Problema Detectado | Clasificación del Integrador |
| :--- | :--- | :--- |
| **A-0082** | Temperatura reportada como string `"N/A"` | Error de normalización (Incompatibilidad de tipo). |
| **A-0150** | Clave `country_code` ausente | Error de normalización (Estructura incompleta). |
| **A-0173** | Temperatura con valor `null` | Error de normalización (Falta de datos). |
| **B-0171** | Fecha incoherente: `31/13/2026 28:75` | Error de normalización (Fallo de parseo `datetime`). |
| **A-0015** | Humedad relativa de `108.4%` | Rechazado localmente (Excede límite 100%). |
| **B-0115** | Velocidad de viento de `-7.4 km/h` | Rechazado localmente (Valor negativo). |
| **B-0128** | Nombre de ciudad vacío | Rechazado localmente (Campo requerido). |

## 4. Validación local vs. validación del servidor

El ejercicio demostró que **la validación local es estructural y sin estado (*stateless*)**, mientras que **la validación del servidor posee contexto de negocio (*stateful*)**.

La validación local garantiza que los atributos existan, tengan el tipo correcto y respeten umbrales matemáticos (ej. latitud entre -90 y 90). Sin embargo, el servidor aplica restricciones adicionales de integridad. En esta ejecución documentada, los 190 registros enviados del Proveedor A eran impecables a nivel local, pero fueron rechazados por el servidor con un código **HTTP 409 (Conflict)**, ya que la base de datos detectó que esas mediciones específicas ya habían sido registradas en una ejecución anterior, evitando su duplicación.

Asimismo, el Proveedor B superó las validaciones iniciales en pruebas tempranas, pero el servidor devolvió **HTTP 422 (Unprocessable Entity)** hasta que se configuró la inyección de la zona horaria (`-05:00`), una validación estricta de la API que no estaba explícita a nivel local.

## 5. Decisión de implementación más importante

La decisión arquitectónica más crítica fue implementar un patrón modular (separando Lector, Normalizador, Validador y Cliente HTTP) combinado con una **optimización de operaciones de entrada/salida (I/O)**.

En el módulo de envíos, en lugar de abrir, reescribir y cerrar el archivo `reporte.json` por cada petición HTTP individual, se utilizó un bloque de control `try...finally`. Esto permite acumular el estado de las peticiones en la memoria RAM y escribir el reporte consolidado en el disco duro una sola vez al finalizar el bucle, o de forma segura si el programa es interrumpido abruptamente (ej. pérdida súbita de red). Esto reduce el desgaste del disco, previene cuellos de botella en sistemas con alta concurrencia y acelera dramáticamente los tiempos de ejecución HTTP. Además, la lógica de reintentos se diseñó meticulosamente: las respuestas `4xx` se descartan de inmediato, reservando los intentos de recuperación exclusivamente para interrupciones transitorias (`5xx` y timeouts).

---

## 6. Evidencia resumida de la ejecución real

Datos tomados de `salida/reporte.json`. El campo *Enviados* hace referencia a los registros que iniciaron el intento de comunicación, independientemente de los reintentos internos.

| Resultado del Flujo | Cantidad |
| :--- | ---: |
| Total de registros procesados | 400 |
| Registros normalizados exitosamente | 391 |
| Errores de normalización atrapados | 9 |
| **Registros válidos localmente (Aptos para POST)** | **380** |
| Registros rechazados localmente | 11 |
| Medición de envíos intentados | 380 |
| **Aceptados por la API (HTTP 201 - Proveedor B)** | **190** |
| **Rechazados por la API (HTTP 409 - Proveedor A duplicados)** | **190** |
| Fallos críticos de comunicación | 0 |

### Respuesta real para registro B-0001 (HTTP 201)
```json
{"id":960,"estado":"aceptada","mensaje":"Medición registrada correctamente"}