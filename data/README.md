# Datos

> El CSV **no está versionado**. Pesa ~75 MB y `.gitignore` excluye `data/*.csv`.
> Este archivo explica de dónde sale y cómo regenerarlo en un comando.

## Origen

| | |
|---|---|
| **Fuente** | CONASET — Comisión Nacional de Seguridad de Tránsito (Chile) |
| **Conjunto** | Base SINIESTROS, microdato de siniestros de tránsito |
| **Acceso** | ArcGIS REST FeatureServer, capa 0 |
| **Endpoint** | `https://services3.arcgis.com/vaJl1B5HEzZj7154/arcgis/rest/services/Base_SINIESTROS_2020_2025/FeatureServer/0/query` |
| **Período usado** | 2023, 2024 y 2025 |
| **Volumen** | 216.340 siniestros × 36 columnas |
| **Licencia** | Datos abiertos de Gobierno de Chile |

Es **microdato**: una fila por siniestro. No confundir con los Excel del
Observatorio de CONASET, que publican agregados ya resumidos por región y año y
no sirven para entrenar un modelo a nivel de evento.

## Cómo obtenerlo

```bash
pip install requests
python data/descargar_datos.py                  # todo el período disponible
python data/descargar_datos.py --desde-anio 2023  # solo 2023 en adelante
python data/descargar_datos.py --solo-contar    # cuántas filas hay, sin bajar
```

El archivo queda en `data/siniestros.csv`.

### Por qué hace falta un script y no basta un link

El endpoint `/query` de ArcGIS devuelve como máximo `maxRecordCount` filas por
llamada (2.000 en este servicio). Un link sin paginación o bien responde
**Bad Request**, o bien entrega solo las primeras 2.000 filas sin avisar, que es
peor porque nadie lo nota. El script pagina con `resultOffset` /
`resultRecordCount` sobre `f=json`, ordenando por `FID` para que ninguna fila se
repita ni se pierda entre llamadas, y arma el CSV completo.

## Columnas del archivo crudo

36 columnas. Las que usa el proyecto:

| Columna | Uso |
|---|---|
| `REGION` | predictora `region` |
| `ZONA` | predictora `zona` (URBANA / RURAL) |
| `TIPO__CONA` | predictora `tipo_siniestro` (tipo agrupado, 7 categorías) |
| `CAUSA_NUEV` | predictora `causa` (16 categorías, normalizadas sin tilde) |
| `UBICACION` | predictora `ubicacion_via` (207 valores → 6 grupos viales) |
| `Dia_semana`, `Mes` | predictoras de calendario |
| `Hora_aprox` | predictora `hora` (entero 0–23) |
| `Atropello`, `Motociclet`, `Bicicleta` | banderas 0/1 → predictora `modo` |
| `FALLECIDOS`, `GRAVES` | **construyen el target**, no son predictoras |

## Advertencia de fuga de información

Estas columnas describen el **resultado** del siniestro y están prohibidas como
predictoras:

```
FALLECIDOS   GRAVES   MENOS_GRAV   LEVES   TOTAL_LESI   Siniestro
```

`Siniestro` merece mención aparte: parece una columna descriptiva, pero se
verificó en `notebooks/exploracion.ipynb` que equivale exactamente a
`FALLECIDOS > 0` en el 100 % de las filas. Es el target disfrazado. Incluirla
daría ~100 % de accuracy y un modelo inútil, porque en el momento en que
queremos predecir todavía no se conoce.

## Tratamiento aplicado

1. Normalización de tildes en `CAUSA_NUEV` y `UBICACION` (el origen mezcla
   `SEÑAL` y `SENAL` para la misma categoría: 6.751 + 6.688 filas partidas en
   dos categorías que son una).
2. Agrupación de `UBICACION` en 6 categorías viales.
3. Colapso de las tres banderas de participante en una variable `modo`.
4. Filtro de `Hora_aprox` al rango 0–23 y descarte de filas sin las categóricas
   clave.
5. **No** se eliminan duplicados: cada fila es un siniestro real e
   independiente, y dos siniestros distintos pueden compartir el mismo vector
   de 9 variables gruesas.
