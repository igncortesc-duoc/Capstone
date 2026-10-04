import streamlit as st
import joblib
import os


# CONFIGURACION

st.set_page_config(
    page_title="TIX AI",
    page_icon="TA",
    layout="wide"
)


# RUTAS

BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

MODELOS_DIR = os.path.join(
    BASE_DIR,
    "machine_learning",
    "modelos"
)


MODELO_CATEGORIA_PATH = os.path.join(
    MODELOS_DIR,
    "modelo_categoria.joblib"
)


MODELO_PRIORIDAD_PATH = os.path.join(
    MODELOS_DIR,
    "modelo_prioridad.joblib"
)


# CARGAR MODELOS

@st.cache_resource
def cargar_modelos():

    paquete_categoria = joblib.load(
        MODELO_CATEGORIA_PATH
    )

    paquete_prioridad = joblib.load(
        MODELO_PRIORIDAD_PATH
    )

    return paquete_categoria, paquete_prioridad


try:

    paquete_categoria, paquete_prioridad = (
        cargar_modelos()
    )

except FileNotFoundError:

    st.error(
        "No se encontraron los modelos entrenados."
    )

    st.info(
        "Ejecute primero: "
        "python machine_learning\\entrenar_modelos.py"
    )

    st.stop()


# EXTRAER MODELOS Y VECTORIZADORES

modelo_categoria = paquete_categoria["modelo"]

vectorizador_categoria = (
    paquete_categoria["vectorizador"]
)


modelo_prioridad = paquete_prioridad["modelo"]

vectorizador_prioridad = (
    paquete_prioridad["vectorizador"]
)


# INFORMACIÓN DE LOS MODELOS

nombre_modelo_categoria = (
    paquete_categoria["nombre_modelo"]
)

f1_categoria = (
    paquete_categoria["f1_macro"]
)


nombre_modelo_prioridad = (
    paquete_prioridad["nombre_modelo"]
)

f1_prioridad = (
    paquete_prioridad["f1_macro"]
)


# FUNCIÓN PARA OBTENER PREDICCIÓN Y PORCENTAJE

def obtener_prediccion(modelo, vectorizador, texto):

    texto_tfidf = vectorizador.transform(
        [texto]
    )

    prediccion = modelo.predict(
        texto_tfidf
    )[0]


    # Obtener probabilidades
    if hasattr(modelo, "predict_proba"):

        probabilidades = modelo.predict_proba(
            texto_tfidf
        )[0]

        clases = modelo.classes_

        indice = list(clases).index(
            prediccion
        )

        porcentaje = (
            probabilidades[indice] * 100
        )

    else:

        porcentaje = None


    return prediccion, porcentaje


# INTERFAZ

st.title("TIX AI")

st.subheader(
    "Clasificador inteligente de tickets de soporte TI"
)

st.write(
    "Ingrese la información del ticket para obtener "
    "una clasificación automática de categoría y prioridad "
    "mediante Machine Learning."
)


st.divider()


# ============================================================
# INGRESO DEL TICKET
# ============================================================

st.header("🎫 Clasificación de ticket")


asunto = st.text_input(
    "Asunto del ticket",
    placeholder=(
        "Ejemplo: No puedo conectarme a la red WiFi"
    )
)


descripcion = st.text_area(
    "Descripción del ticket",
    placeholder=(
        "Ejemplo: Desde esta mañana no puedo "
        "conectarme a la red de la empresa."
    ),
    height=150
)


# BOTÓN

if st.button(
    "🤖 Clasificar ticket",
    use_container_width=True
):

    if asunto.strip() or descripcion.strip():

        # UNIR TEXTO

        texto = (
            asunto.strip()
            + " "
            + descripcion.strip()
        )


        # CATEGORÍA

        categoria, porcentaje_categoria = (
            obtener_prediccion(
                modelo_categoria,
                vectorizador_categoria,
                texto
            )
        )


        # PRIORIDAD

        prioridad, porcentaje_prioridad = (
            obtener_prediccion(
                modelo_prioridad,
                vectorizador_prioridad,
                texto
            )
        )


        # RESULTADOS

        st.divider()

        st.header(
            "📊 Resultado de la clasificación"
        )


        col1, col2 = st.columns(2)


        # ----------------------------------------------------
        # CATEGORÍA
        # ----------------------------------------------------

        with col1:

            st.success(
                f"### 📂 Categoría\n"
                f"**{categoria}**"
            )

            if porcentaje_categoria is not None:

                st.metric(
                    "Porcentaje de predicción",
                    f"{porcentaje_categoria:.2f}%"
                )

                st.progress(
                    min(
                        porcentaje_categoria / 100,
                        1.0
                    )
                )


        # PRIORIDAD

        with col2:

            st.info(
                f"### 🚨 Prioridad\n"
                f"**{prioridad}**"
            )

            if porcentaje_prioridad is not None:

                st.metric(
                    "Porcentaje de predicción",
                    f"{porcentaje_prioridad:.2f}%"
                )

                st.progress(
                    min(
                        porcentaje_prioridad / 100,
                        1.0
                    )
                )


        # MODELOS UTILIZADOS

        st.divider()

        st.subheader(
            "🤖 Información de los modelos"
        )


        col3, col4 = st.columns(2)


        with col3:

            st.write(
                f"**Modelo de categoría:** "
                f"{nombre_modelo_categoria}"
            )

            st.write(
                f"**F1 Macro:** "
                f"{f1_categoria:.4f}"
            )


        with col4:

            st.write(
                f"**Modelo de prioridad:** "
                f"{nombre_modelo_prioridad}"
            )

            st.write(
                f"**F1 Macro:** "
                f"{f1_prioridad:.4f}"
            )


        # TICKET ANALIZADO

        st.divider()

        st.subheader(
            "📝 Ticket analizado"
        )

        st.write(
            f"**Asunto:** {asunto}"
        )

        st.write(
            f"**Descripción:** {descripcion}"
        )


    else:

        st.warning(
            "Debe ingresar al menos el asunto "
            "o la descripción del ticket."
        )
