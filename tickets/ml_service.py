import os
import joblib
from django.conf import settings


# Ruta principal del proyecto
BASE_DIR = settings.BASE_DIR


# Rutas de los archivos del modelo
MODELO_PATH = os.path.join(
    BASE_DIR,
    'machine_learning',
    'modelos',
    'modelo_ticket.joblib'
)

VECTORIZADOR_PATH = os.path.join(
    BASE_DIR,
    'machine_learning',
    'modelos',
    'vectorizador.joblib'
)


# Cargar modelo y vectorizador
modelo = joblib.load(MODELO_PATH)

vectorizador = joblib.load(VECTORIZADOR_PATH)


def predecir_categoria(asunto, descripcion):

    # Unir asunto y descripción
    texto = f"{asunto} {descripcion}"

    # Transformar texto usando TF-IDF
    texto_vectorizado = vectorizador.transform([texto])

    # Realizar predicción
    categoria = modelo.predict(texto_vectorizado)[0]

    # Obtener confianza
    probabilidades = modelo.predict_proba(texto_vectorizado)[0]

    confianza = max(probabilidades) * 100

    return categoria, confianza