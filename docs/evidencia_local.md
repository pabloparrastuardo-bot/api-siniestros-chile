# Evidencia de ejecución local

Transcripción de las llamadas exigidas por el enunciado (§3.4), ejecutadas
contra el servicio corriendo en `localhost:8000`.

La captura de `/docs` en el navegador está en `docs/evidencia_local.png`.

---

## 0. Arranque del servicio

```console
$ uvicorn app.main:app --reload --port 8000
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process using WatchFiles
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

`Application startup complete` aparece **después** de cargar el `.pkl`: el
modelo se lee una sola vez, en el `lifespan`, no en cada petición.

---

## 1. Estado del servicio — `GET /health`

```console
$ curl -s http://localhost:8000/health
```
```json
{"status":"ok","model_loaded":true,"version_modelo":"1.0.0"}
```

---

## 2. Predicción exitosa — `POST /predict`

Atropello a un peatón, sábado a las 23:00, en zona urbana de la Región
Metropolitana:

```console
$ curl -s -X POST http://localhost:8000/predict \
       -H "Content-Type: application/json" \
       -d '{"region":"Metropolitana de Santiago","zona":"URBANA",
            "tipo_siniestro":"ATROPELLO","causa":"IMPRUDENCIA DEL PEATON",
            "ubicacion_via":"TRAMO RECTO","dia_semana":"Sábado","mes":"Julio",
            "modo":"PEATON","hora":23}'
```
```json
{
  "prediccion": 1,
  "etiqueta": "grave o fatal",
  "probabilidad_grave": 0.8953,
  "umbral": 0.5,
  "version_modelo": "1.0.0",
  "timestamp": "2026-09-23T12:37:32+00:00"
}
```

---

## 3. Predicción por lote — `POST /predict-batch`

Tres observaciones de riesgo decreciente; las respuestas vuelven en el mismo
orden en que entraron:

```console
$ curl -s -X POST http://localhost:8000/predict-batch \
       -H "Content-Type: application/json" \
       -d '{"observaciones":[
             {"region":"Metropolitana de Santiago","zona":"URBANA","tipo_siniestro":"ATROPELLO",
              "causa":"IMPRUDENCIA DEL PEATON","ubicacion_via":"TRAMO RECTO",
              "dia_semana":"Sábado","mes":"Julio","modo":"PEATON","hora":23},
             {"region":"Valparaíso","zona":"RURAL","tipo_siniestro":"VOLCADURA",
              "causa":"VELOCIDAD IMPRUDENTE","ubicacion_via":"CURVA O PENDIENTE",
              "dia_semana":"Domingo","mes":"Enero","modo":"VEHICULO","hora":4},
             {"region":"Biobío","zona":"URBANA","tipo_siniestro":"CHOQUE",
              "causa":"DISTRACCION DEL CONDUCTOR","ubicacion_via":"CRUCE",
              "dia_semana":"Martes","mes":"Abril","modo":"VEHICULO","hora":9}]}'
```
```json
{
  "n": 3,
  "predicciones": [
    {"prediccion": 1, "etiqueta": "grave o fatal",       "probabilidad_grave": 0.8953, "umbral": 0.5, "version_modelo": "1.0.0", "timestamp": "2026-09-23T12:37:38+00:00"},
    {"prediccion": 1, "etiqueta": "grave o fatal",       "probabilidad_grave": 0.8040, "umbral": 0.5, "version_modelo": "1.0.0", "timestamp": "2026-09-23T12:37:38+00:00"},
    {"prediccion": 0, "etiqueta": "sin víctimas graves", "probabilidad_grave": 0.0824, "umbral": 0.5, "version_modelo": "1.0.0", "timestamp": "2026-09-23T12:37:38+00:00"}
  ]
}
```

---

## 4. Entrada inválida — `422 Unprocessable Entity`

`hora: 99` viola la restricción `ge=0, le=23` del modelo Pydantic. La petición
**no llega al modelo**: muere en la validación, con un mensaje que dice
exactamente qué campo está mal.

```console
$ curl -s -w "\nHTTP %{http_code}\n" -X POST http://localhost:8000/predict \
       -H "Content-Type: application/json" \
       -d '{"region":"Metropolitana de Santiago","zona":"URBANA",
            "tipo_siniestro":"ATROPELLO","causa":"IMPRUDENCIA DEL PEATON",
            "ubicacion_via":"TRAMO RECTO","dia_semana":"Sábado","mes":"Julio",
            "modo":"PEATON","hora":99}'
```
```json
{
  "detail": [
    {
      "type": "less_than_equal",
      "loc": ["body", "hora"],
      "msg": "Input should be less than or equal to 23",
      "input": 99,
      "ctx": {"le": 23}
    }
  ]
}
```
```
HTTP 422
```

Otra categoría inválida (`"region": "Región de Narnia"`) devuelve también 422,
porque `region` está declarada como `Literal` con las 16 regiones admitidas.

---

## 5. Suite de pruebas

```console
$ pytest -v
============================= test session starts ==============================
platform linux -- Python 3.11, pytest-8.3.4
collected 9 items

tests/test_api.py::test_health_responde_ok_con_modelo_cargado PASSED     [ 11%]
tests/test_api.py::test_model_info_expone_features_y_metricas PASSED     [ 22%]
tests/test_api.py::test_predict_devuelve_clase_y_probabilidad PASSED     [ 33%]
tests/test_api.py::test_predict_batch_conserva_el_orden PASSED           [ 44%]
tests/test_api.py::test_campo_faltante_devuelve_422 PASSED               [ 55%]
tests/test_api.py::test_valor_fuera_de_rango_devuelve_422 PASSED         [ 66%]
tests/test_api.py::test_categoria_inexistente_devuelve_422 PASSED        [ 77%]
tests/test_api.py::test_tipo_incorrecto_devuelve_422 PASSED              [ 88%]
tests/test_api.py::test_lote_vacio_devuelve_422 PASSED                   [100%]

============================== 9 passed in 1.66s ===============================
```

---

## 6. Verificación del artefacto en entorno limpio

La penalización más cara del enunciado es que el `.pkl` no cargue con el
`requirements.txt` declarado. Se comprobó en un entorno virtual recién creado,
instalando **solo** lo que dice `requirements.txt`:

```console
$ python -m venv /tmp/verificacion
$ /tmp/verificacion/bin/pip install -r requirements.txt
$ /tmp/verificacion/bin/python -c "
import joblib, json, pandas as pd, sklearn
pipe = joblib.load('model/model.pkl')
m = json.load(open('model/metadata.json'))
obs = {...}
df = pd.DataFrame([obs])[m['features']]
print('sklearn', sklearn.__version__, '| pred', pipe.predict(df)[0])
"
sklearn 1.8.0 | pred 1
```

Carga sin advertencias de versión y entrega la misma probabilidad (0.8953) que
en el entorno de entrenamiento.
