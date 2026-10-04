import os
import joblib

from django.conf import settings

from .anonimizador import anonimizar_ticket


BASE_DIR = settings.BASE_DIR

MODELOS_DIR = os.path.join(
    BASE_DIR,
    'machine_learning',
    'modelos'
)


# MODELO DE CATEGORIA

MODELO_CATEGORIA_PATH = os.path.join(
    MODELOS_DIR,
    'modelo_categoria.joblib'
)


paquete_categoria = joblib.load(
    MODELO_CATEGORIA_PATH
)

modelo_categoria = paquete_categoria['modelo']
vectorizador_categoria = paquete_categoria['vectorizador']


# MODELO DE PRIORIDAD

MODELO_PRIORIDAD_PATH = os.path.join(
    MODELOS_DIR,
    'modelo_prioridad.joblib'
)


paquete_prioridad = joblib.load(
    MODELO_PRIORIDAD_PATH
)

modelo_prioridad = paquete_prioridad['modelo']
vectorizador_prioridad = paquete_prioridad['vectorizador']


# CATEGORIA

def predecir_categoria(titulo, descripcion):

    # Anonimizar antes de utilizar el modelo
    titulo, descripcion = anonimizar_ticket(
        titulo,
        descripcion
    )

    texto = f"{titulo} {descripcion}"

    texto_vectorizado = vectorizador_categoria.transform(
        [texto]
    )

    categoria = modelo_categoria.predict(
        texto_vectorizado
    )[0]

    confianza = None

    if hasattr(modelo_categoria, 'predict_proba'):

        probabilidades = modelo_categoria.predict_proba(
            texto_vectorizado
        )[0]

        clases = modelo_categoria.classes_

        indice = list(clases).index(categoria)

        confianza = probabilidades[indice] * 100

    return categoria, confianza


# PRIORIDAD

def predecir_prioridad(titulo, descripcion):

    # Anonimizar antes de utilizar el modelo
    titulo, descripcion = anonimizar_ticket(
        titulo,
        descripcion
    )

    texto = f"{titulo} {descripcion}"

    texto_vectorizado = vectorizador_prioridad.transform(
        [texto]
    )

    prioridad = modelo_prioridad.predict(
        texto_vectorizado
    )[0]

    confianza = None

    if hasattr(modelo_prioridad, 'predict_proba'):

        probabilidades = modelo_prioridad.predict_proba(
            texto_vectorizado
        )[0]

        clases = modelo_prioridad.classes_

        indice = list(clases).index(prioridad)

        confianza = probabilidades[indice] * 100

    return prioridad, confianza
