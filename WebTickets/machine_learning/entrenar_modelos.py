import pandas as pd

from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer

from sklearn.naive_bayes import MultinomialNB
from sklearn.linear_model import LogisticRegression
from sklearn.svm import SVC

from sklearn.metrics import (
    accuracy_score,
    precision_recall_fscore_support,
    classification_report,
    confusion_matrix
)

import joblib
import os


# ============================================================
# 1. CONFIGURACIÓN DE RUTAS
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATASET_PATH = os.path.join(
    BASE_DIR,
    'dataset',
    'tickets.csv'
)

MODELOS_DIR = os.path.join(
    BASE_DIR,
    'modelos'
)

os.makedirs(
    MODELOS_DIR,
    exist_ok=True
)


# ============================================================
# 2. CARGAR DATASET
# ============================================================

df = pd.read_csv(DATASET_PATH)

print("\n" + "=" * 60)
print("DATASET CARGADO")
print("=" * 60)

print(df.head())

print("\nColumnas del dataset:")
print(df.columns.tolist())

print("\nCantidad de registros:")
print(len(df))


# ============================================================
# 3. LIMPIAR DATOS
# ============================================================

df['asunto'] = df['asunto'].fillna('')
df['descripcion'] = df['descripcion'].fillna('')
df['categoria'] = df['categoria'].fillna('')
df['prioridad'] = df['prioridad'].fillna('')


# ============================================================
# 4. UNIR ASUNTO + DESCRIPCIÓN
# ============================================================

df['texto'] = (
    df['asunto']
    + ' '
    + df['descripcion']
)


# ============================================================
# FUNCIÓN PARA ENTRENAR UN OBJETIVO
# ============================================================

def entrenar_objetivo(X, y, nombre_objetivo):

    print("\n" + "=" * 60)
    print(f"ENTRENANDO: {nombre_objetivo.upper()}")
    print("=" * 60)

    print("\nCantidad por clase:")
    print(y.value_counts())


    # ========================================================
    # TRAIN / TEST
    # ========================================================

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.20,
        random_state=42,
        stratify=y
    )


    # ========================================================
    # TF-IDF
    # ========================================================

    vectorizador = TfidfVectorizer(
        lowercase=True,
        stop_words=None
    )

    X_train_tfidf = vectorizador.fit_transform(
        X_train
    )

    X_test_tfidf = vectorizador.transform(
        X_test
    )


    # ========================================================
    # FUNCIÓN PARA EVALUAR MODELOS
    # ========================================================

    def evaluar_modelo(nombre, modelo):

        modelo.fit(
            X_train_tfidf,
            y_train
        )

        predicciones = modelo.predict(
            X_test_tfidf
        )

        accuracy = accuracy_score(
            y_test,
            predicciones
        )

        precision, recall, f1, _ = (
            precision_recall_fscore_support(
                y_test,
                predicciones,
                average='macro',
                zero_division=0
            )
        )

        print("\n" + "-" * 50)
        print(nombre)
        print("-" * 50)

        print(f"Accuracy:        {accuracy:.4f}")
        print(f"Precision Macro: {precision:.4f}")
        print(f"Recall Macro:    {recall:.4f}")
        print(f"F1 Macro:        {f1:.4f}")

        print("\nREPORTE POR CLASE")

        print(
            classification_report(
                y_test,
                predicciones,
                zero_division=0
            )
        )

        print("\nMATRIZ DE CONFUSIÓN")

        print(
            confusion_matrix(
                y_test,
                predicciones
            )
        )

        return modelo, f1


    # ========================================================
    # ENTRENAR NAIVE BAYES
    # ========================================================

    modelo_nb, f1_nb = evaluar_modelo(
        "NAIVE BAYES",
        MultinomialNB()
    )


    # ========================================================
    # ENTRENAR LOGISTIC REGRESSION
    # ========================================================

    modelo_lr, f1_lr = evaluar_modelo(
        "LOGISTIC REGRESSION",
        LogisticRegression(
            max_iter=1000
        )
    )


    # ========================================================
    # ENTRENAR SVM
    # ========================================================

    modelo_svm, f1_svm = evaluar_modelo(
        "SVM",
        SVC(
            kernel='linear',
            probability=True
        )
    )


    # ========================================================
    # SELECCIONAR MEJOR MODELO
    # ========================================================

    modelos = {
        'naive_bayes': (modelo_nb, f1_nb),
        'logistic_regression': (modelo_lr, f1_lr),
        'svm': (modelo_svm, f1_svm)
    }


    mejor_nombre = max(
        modelos,
        key=lambda nombre: modelos[nombre][1]
    )

    mejor_modelo = modelos[mejor_nombre][0]

    mejor_f1 = modelos[mejor_nombre][1]


    print("\n" + "=" * 60)
    print(
        f"MEJOR MODELO PARA "
        f"{nombre_objetivo.upper()}"
    )
    print("=" * 60)

    print(f"Modelo: {mejor_nombre}")
    print(f"F1 Macro: {mejor_f1:.4f}")


    # ========================================================
    # GUARDAR MODELO + VECTORIZADOR
    # ========================================================

    paquete_modelo = {
        'modelo': mejor_modelo,
        'vectorizador': vectorizador,
        'nombre_modelo': mejor_nombre,
        'f1_macro': mejor_f1
    }


    if nombre_objetivo == 'categoria':

        nombre_archivo = 'modelo_categoria.joblib'

    else:

        nombre_archivo = 'modelo_prioridad.joblib'


    ruta_modelo = os.path.join(
        MODELOS_DIR,
        nombre_archivo
    )


    joblib.dump(
        paquete_modelo,
        ruta_modelo
    )


    print("\nModelo guardado correctamente:")
    print(ruta_modelo)


# ============================================================
# 5. ENTRENAR CATEGORÍA
# ============================================================

entrenar_objetivo(
    df['texto'],
    df['categoria'],
    'categoria'
)


# ============================================================
# 6. ENTRENAR PRIORIDAD
# ============================================================

entrenar_objetivo(
    df['texto'],
    df['prioridad'],
    'prioridad'
)


# ============================================================
# 7. FINALIZACIÓN
# ============================================================

print("\n" + "=" * 60)
print("ENTRENAMIENTO COMPLETADO")
print("=" * 60)

print("\nModelos generados:")

print(
    os.path.join(
        MODELOS_DIR,
        'modelo_categoria.joblib'
    )
)

print(
    os.path.join(
        MODELOS_DIR,
        'modelo_prioridad.joblib'
    )
)
