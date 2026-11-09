import os
import joblib
from django.conf import settings
from .anonimizador import anonimizar_ticket

BASE_DIR = settings.BASE_DIR
MODELOS_DIR = os.path.join(BASE_DIR, 'machine_learning', 'modelos')

MODELO_CATEGORIA_PATH = os.path.join(MODELOS_DIR, 'modelo_categoria.joblib')
MODELO_PRIORIDAD_PATH = os.path.join(MODELOS_DIR, 'modelo_prioridad.joblib')

_modelo_categoria = None
_vectorizador_categoria = None
_modelo_prioridad = None
_vectorizador_prioridad = None


def _cargar_modelos():
    global _modelo_categoria, _vectorizador_categoria, _modelo_prioridad, _vectorizador_prioridad

    if _modelo_categoria is None and os.path.exists(MODELO_CATEGORIA_PATH):
        try:
            paquete_cat = joblib.load(MODELO_CATEGORIA_PATH)
            _modelo_categoria = paquete_cat.get('modelo')
            _vectorizador_categoria = paquete_cat.get('vectorizador')
        except Exception as e:
            print(f"[ML SERVICE] Error cargando modelo_categoria: {e}")

    if _modelo_prioridad is None and os.path.exists(MODELO_PRIORIDAD_PATH):
        try:
            paquete_prio = joblib.load(MODELO_PRIORIDAD_PATH)
            _modelo_prioridad = paquete_prio.get('modelo')
            _vectorizador_prioridad = paquete_prio.get('vectorizador')
        except Exception as e:
            print(f"[ML SERVICE] Error cargando modelo_prioridad: {e}")


def predecir_categoria(titulo, descripcion):
    _cargar_modelos()

    titulo, descripcion = anonimizar_ticket(titulo, descripcion)
    texto = f"{titulo} {descripcion}"

    if _modelo_categoria is None or _vectorizador_categoria is None:
        return "Soporte General", 50.0

    try:
        texto_vectorizado = _vectorizador_categoria.transform([texto])
        categoria = _modelo_categoria.predict(texto_vectorizado)[0]
        confianza = None

        if hasattr(_modelo_categoria, 'predict_proba'):
            probabilidades = _modelo_categoria.predict_proba(texto_vectorizado)[0]
            clases = _modelo_categoria.classes_
            indice = list(clases).index(categoria)
            confianza = float(probabilidades[indice] * 100)

        return categoria, confianza
    except Exception as e:
        print(f"[ML SERVICE] Error al predecir categoria: {e}")
        return "Soporte General", 50.0


def predecir_prioridad(titulo, descripcion):
    _cargar_modelos()

    titulo, descripcion = anonimizar_ticket(titulo, descripcion)
    texto = f"{titulo} {descripcion}"

    if _modelo_prioridad is None or _vectorizador_prioridad is None:
        return "Media", 50.0

    try:
        texto_vectorizado = _vectorizador_prioridad.transform([texto])
        prioridad = _modelo_prioridad.predict(texto_vectorizado)[0]
        confianza = None

        if hasattr(_modelo_prioridad, 'predict_proba'):
            probabilidades = _modelo_prioridad.predict_proba(texto_vectorizado)[0]
            clases = _modelo_prioridad.classes_
            indice = list(clases).index(prioridad)
            confianza = float(probabilidades[indice] * 100)

        return prioridad, confianza
    except Exception as e:
        print(f"[ML SERVICE] Error al predecir prioridad: {e}")
        return "Media", 50.0
