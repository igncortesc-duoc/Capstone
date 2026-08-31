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


# ==========================================
# 1. CARGAR DATASET
# ==========================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATASET_PATH = os.path.join(
    BASE_DIR,
    'dataset',
    'tickets_prioridad.csv'
)

df = pd.read_csv(DATASET_PATH)

print("\nDATASET CARGADO")
print(df.head())

print("\nCANTIDAD POR PRIORIDAD")
print(df['prioridad'].value_counts())


# ==========================================
# 2. UNIR ASUNTO + DESCRIPCIÓN
# ==========================================

df['texto'] = (
    df['asunto'].fillna('') +
    ' ' +
    df['descripcion'].fillna('')
)


X = df['texto']
y = df['prioridad']


# ==========================================
# 3. DIVIDIR TRAIN Y TEST
# ==========================================

X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.20,
    random_state=42,
    stratify=y
)


# ==========================================
# 4. TF-IDF
# ==========================================

vectorizador_prioridad = TfidfVectorizer(
    lowercase=True,
    stop_words=None
)

X_train_tfidf = vectorizador_prioridad.fit_transform(X_train)

X_test_tfidf = vectorizador_prioridad.transform(X_test)


# ==========================================
# FUNCIÓN PARA EVALUAR MODELOS
# ==========================================

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

    precision, recall, f1, _ = precision_recall_fscore_support(
        y_test,
        predicciones,
        average='macro',
        zero_division=0
    )

    print("\n" + "=" * 50)
    print(nombre)
    print("=" * 50)

    print(f"Accuracy: {accuracy:.4f}")
    print(f"Precision Macro: {precision:.4f}")
    print(f"Recall Macro: {recall:.4f}")
    print(f"F1 Macro: {f1:.4f}")

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


# ==========================================
# 5. ENTRENAR MODELOS
# ==========================================

modelo_nb, f1_nb = evaluar_modelo(
    "NAIVE BAYES",
    MultinomialNB()
)

modelo_lr, f1_lr = evaluar_modelo(
    "LOGISTIC REGRESSION",
    LogisticRegression(
        max_iter=1000
    )
)

modelo_svm, f1_svm = evaluar_modelo(
    "SVM",
    SVC(
        kernel='linear',
        probability=True
    )
)


# ==========================================
# 6. SELECCIONAR MEJOR MODELO
# ==========================================

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

print("\n" + "=" * 50)
print(f"MEJOR MODELO: {mejor_nombre}")
print(f"F1 Macro: {modelos[mejor_nombre][1]:.4f}")
print("=" * 50)


# ==========================================
# 7. GUARDAR MODELO Y VECTORIZADOR
# ==========================================

MODELOS_DIR = os.path.join(
    BASE_DIR,
    'modelos'
)

os.makedirs(
    MODELOS_DIR,
    exist_ok=True
)

joblib.dump(
    mejor_modelo,
    os.path.join(
        MODELOS_DIR,
        'modelo_prioridad.joblib'
    )
)

joblib.dump(
    vectorizador_prioridad,
    os.path.join(
        MODELOS_DIR,
        'vectorizador_prioridad.joblib'
    )
)

print("\nModelo de prioridad guardado correctamente.")