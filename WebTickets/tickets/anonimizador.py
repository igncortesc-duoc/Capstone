import re


def anonimizar_texto(texto):
    """
    Anonimiza información personal que pueda aparecer
    en el asunto o descripción de un ticket.
    """

    if not texto:
        return texto

    # CORREOS ELECTRÓNICOS

    texto = re.sub(
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b',
        '[EMAIL]',
        texto
    )

    # RUT CHILENO

    texto = re.sub(
        r'\b\d{1,2}(?:\.\d{3}){2}-[\dkK]\b',
        '[RUT]',
        texto
    )

    # También detecta RUT sin puntos

    texto = re.sub(
        r'\b\d{7,8}-[\dkK]\b',
        '[RUT]',
        texto
    )

    # TELEFONOS

    texto = re.sub(
        r'(?<!\d)(?:\+?56\s?)?9\s?\d{4}\s?\d{4}(?!\d)',
        '[TELEFONO]',
        texto
    )

    # DIRECCIONES IP

    texto = re.sub(
        r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
        '[IP]',
        texto
    )

    # DIRECCIONES WEB

    texto = re.sub(
        r'https?://[^\s]+',
        '[URL]',
        texto
    )

    # USUARIOS / NOMBRES DE USUARIO


    texto = re.sub(
        r'(?i)\b(usuario|username|user)\s*[:=]\s*[^\s,;]+',
        r'\1: [USUARIO]',
        texto
    )

    return texto


def anonimizar_ticket(asunto, descripcion):
    """
    Anonimiza el asunto y la descripción de un ticket.
    """

    asunto_anonimizado = anonimizar_texto(asunto)
    descripcion_anonimizada = anonimizar_texto(descripcion)

    return asunto_anonimizado, descripcion_anonimizada
