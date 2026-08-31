import os
import joblib
from django.conf import settings


BASE_DIR = settings.BASE_DIR

# Modelo de categoría
MODELO_PATH = os.path.join(BASE_DIR, 'machine_learning', 'modelos', 'modelo_ticket.joblib')
VECTORIZADOR_PATH = os.path.join(BASE_DIR, 'machine_learning', 'modelos', 'vectorizador.joblib')

# Modelo de prioridad
MODELO_PRIORIDAD_PATH = os.path.join(BASE_DIR, 'machine_learning', 'modelos', 'modelo_prioridad.joblib')
VECTORIZADOR_PRIORIDAD_PATH = os.path.join(BASE_DIR, 'machine_learning', 'modelos', 'vectorizador_prioridad.joblib')


modelo = joblib.load(MODELO_PATH)
vectorizador = joblib.load(VECTORIZADOR_PATH)

modelo_prioridad = joblib.load(MODELO_PRIORIDAD_PATH)
vectorizador_prioridad = joblib.load(VECTORIZADOR_PRIORIDAD_PATH)


def predecir_categoria(titulo, descripcion):

    texto = f"{titulo} {descripcion}"

    # --- Categoría ---
    texto_vectorizado = vectorizador.transform([texto])
    categoria = modelo.predict(texto_vectorizado)[0]
    probabilidades = modelo.predict_proba(texto_vectorizado)[0]
    confianza = max(probabilidades) * 100

    # --- Prioridad ---
    texto_vectorizado_prioridad = vectorizador_prioridad.transform([texto])
    prioridad = modelo_prioridad.predict(texto_vectorizado_prioridad)[0]

    return categoria, confianza, prioridad