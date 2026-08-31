def rol_usuario(request):

    if not request.user.is_authenticated:
        return {
            'es_admin': False,
            'es_tecnico': False,
            'es_tecnico_o_admin': False,
        }

    es_admin = request.user.is_staff or request.user.is_superuser
    es_tecnico = request.user.groups.filter(name="Tecnico").exists()

    return {
        'es_admin': es_admin,
        'es_tecnico': es_tecnico,
        'es_tecnico_o_admin': es_admin or es_tecnico,
    }