from .models import Settings

def rol_usuario(request):
    # 1. Cambiamos -id por -id_perfil para que coincida con tu base de datos
    ajuste_global = Settings.objects.order_by('-id_perfil').first()
    color_global = ajuste_global.tema_color if ajuste_global else 'Púrpura'

    # ==========================================
    # CASO A: USUARIO DESCONECTADO (ANÓNIMO)
    # ==========================================
    if not request.user.is_authenticated:
        return {
            'es_admin': False,
            'es_tecnico': False,
            'es_tecnico_o_admin': False,
            'rol_nombre': 'INVITADO',
            'user_settings': ajuste_global,
        }

    # ==========================================
    # CASO B: USUARIO CONECTADO
    # ==========================================
    es_admin = (
        request.user.is_staff
        or request.user.is_superuser
        or request.user.groups.filter(name__icontains="admin").exists()
    )
    es_tecnico = request.user.groups.filter(name__in=["Tecnico", "Técnico", "tecnico"]).exists()

    if es_admin:
        rol_nombre = "ADMINISTRADOR"
    elif es_tecnico:
        rol_nombre = "TECNICO"
    else:
        rol_nombre = "CLIENTE"

    # 2. Obtenemos los ajustes personales
    user_settings = Settings.objects.filter(usuario=request.user).first()
    
    # 3. Forzamos el color global
    if user_settings and ajuste_global:
        user_settings.tema_color = color_global
    elif not user_settings:
        user_settings = ajuste_global

    return {
        'es_admin': es_admin,
        'es_tecnico': es_tecnico,
        'es_tecnico_o_admin': es_admin or es_tecnico,
        'rol_nombre': rol_nombre,
        'user_settings': user_settings,
    }