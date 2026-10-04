def rol_usuario(request):

    if not request.user.is_authenticated:
        return {
            'es_admin': False,
            'es_tecnico': False,
            'es_tecnico_o_admin': False,
            'rol_nombre': 'INVITADO',
        }

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

    return {
        'es_admin': es_admin,
        'es_tecnico': es_tecnico,
        'es_tecnico_o_admin': es_admin or es_tecnico,
        'rol_nombre': rol_nombre,
    }