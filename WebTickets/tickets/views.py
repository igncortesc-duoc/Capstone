from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login as auth_login
from django.contrib.auth.models import User, Group
from django.utils import timezone
from django.contrib import messages

from .models import Ticket, Categoria, Prioridad, Estado, ClasificacionIA, Settings, EspecialidadTecnico
from .ml_service import predecir_categoria, predecir_prioridad
from .forms import RegistroForm

from django.core.exceptions import PermissionDenied


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def es_tecnico_o_admin(user):
    return (
        user.groups.filter(name="Tecnico").exists()
        or user.is_staff
        or user.is_superuser
    )

def generar_siguiente_id(modelo, campo_id, prefijo, ancho=4):
    """
    Genera el siguiente ID correlativo tipo 'TCK0001' para modelos cuya
    PK es un CharField (no autoincremental).
    """
    ultimo = (
        modelo.objects.filter(**{f"{campo_id}__startswith": prefijo})
        .order_by(f"-{campo_id}")
        .first()
    )

    if ultimo:
        numero_actual = getattr(ultimo, campo_id).replace(prefijo, "")
        try:
            siguiente = int(numero_actual) + 1
        except ValueError:
            siguiente = 1
    else:
        siguiente = 1

    return f"{prefijo}{str(siguiente).zfill(ancho)}"


# ---------------------------------------------------------------------------
# Público / Auth
# ---------------------------------------------------------------------------

def index(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'tickets/index.html')


def registro(request):

    if request.method == 'POST':
        form = RegistroForm(request.POST)

        if form.is_valid():
            data = form.cleaned_data

            user = User.objects.create_user(
                username=data['correo'],
                email=data['correo'],
                password=data['password'],
                first_name=data['nombre'],
                last_name=data['apellido'],
            )

            grupo_usuario, _ = Group.objects.get_or_create(name="Usuario")
            user.groups.add(grupo_usuario)

            auth_login(request, user)
            return redirect('dashboard')
    else:
        form = RegistroForm()

    return render(request, 'tickets/register.html', {'form': form})

def asignar_tecnico_automatico(categoria_obj):

    if categoria_obj:
        tecnicos_elegibles = User.objects.filter(
            groups__name="Tecnico",
            especialidades__categoria=categoria_obj
        ).distinct()
    else:
        tecnicos_elegibles = User.objects.none()

    if not tecnicos_elegibles.exists():
        tecnicos_elegibles = User.objects.filter(groups__name="Tecnico")

    if not tecnicos_elegibles.exists():
        return None

    tecnico_elegido = min(
        tecnicos_elegibles,
        key=lambda t: t.tickets_asignados.exclude(id_estado__nombre="Cerrado").count()
    )

    return tecnico_elegido

@login_required
def asignar_tecnico(request, ticket_id):

    if not es_tecnico_o_admin(request.user):
        raise PermissionDenied

    ticket = get_object_or_404(Ticket, id_ticket=ticket_id)

    if request.method == 'POST':

        tecnico_id = request.POST.get('tecnico')

        if tecnico_id:
            tecnico = get_object_or_404(User, pk=tecnico_id, groups__name="Tecnico")
            ticket.id_tecnico = tecnico
            ticket.fecha_asignacion = timezone.now()
            ticket.save()

    return redirect('detalle_ticket', ticket_id=ticket.id_ticket)
# ---------------------------------------------------------------------------
# Tickets
# ---------------------------------------------------------------------------

@login_required
def responder_ticket(request, id_ticket):

    # Verificar que sea administrador o técnico
    es_tecnico = request.user.groups.filter(name='Tecnico').exists()
    es_admin = request.user.is_staff

    if not (es_tecnico or es_admin):
        messages.error(
            request,
            'No tienes permisos para responder este ticket.'
        )
        return redirect('lista_tickets')

    ticket = get_object_or_404(
        Ticket,
        id_ticket=id_ticket
    )

    # Guardar respuesta
    if request.method == 'POST':

        solucion = request.POST.get('solucion', '').strip()

        if not solucion:
            messages.error(
                request,
                'La respuesta no puede estar vacía.'
            )

        else:

            ticket.solucion = solucion
            ticket.save(update_fields=['solucion'])

            messages.success(
                request,
                'Respuesta guardada correctamente.'
            )

            return redirect(
                'detalle_ticket',
                id_ticket=ticket.id_ticket
            )

    return render(
        request,
        'tickets/responder_ticket.html',
        {
            'ticket': ticket
        }
    )

@login_required
def nuevo_ticket(request):

    if request.method == 'POST':

        titulo = request.POST.get('titulo')
        descripcion = request.POST.get('descripcion')

        # Predicción de IA: categoría, confianza y prioridad
        categoria, confianza_categoria = predecir_categoria(titulo, descripcion)
        prioridad, confianza_prioridad = predecir_prioridad(titulo, descripcion)

        # Estado inicial por defecto: Abierto
        estado_abierto = Estado.objects.get(nombre="Abierto")

        # Buscar objetos de categoría y prioridad predichos
        categoria_obj = Categoria.objects.filter(nombre=categoria).first()
        prioridad_obj = Prioridad.objects.filter(nombre=prioridad).first()

        tecnico_asignado = asignar_tecnico_automatico(categoria_obj)

        ticket = Ticket.objects.create(
            id_ticket=generar_siguiente_id(Ticket, 'id_ticket', 'TCK'),
            titulo=titulo,
            descripcion=descripcion,
            fecha_creacion=timezone.now(),
            usuario=request.user,
            id_tecnico=tecnico_asignado,
            id_prioridad=prioridad_obj,
            id_estado=estado_abierto,
            fecha_asignacion=timezone.now() if tecnico_asignado else None,
        )

        # Registrar la clasificación de la IA (queda como historial/predicción)
        if categoria_obj and prioridad_obj:
            ClasificacionIA.objects.create(
                id_clasificacion_ia=generar_siguiente_id(
                    ClasificacionIA, 'id_clasificacion_ia', 'CIA'
                ),
                resultado=categoria,
                nivel_confianza_categoria = confianza_categoria,
                nivel_confianza_prioridad = confianza_prioridad,
                fecha_clasificacion=timezone.now(),
                modelo_utilizado="modelo_ia_v1",
                id_ticket=ticket,
                id_categoria=categoria_obj,
                id_prioridad=prioridad_obj,
            )

        return redirect('detalle_ticket', ticket_id=ticket.id_ticket)

    return render(request, 'tickets/nuevo_ticket.html')


@login_required
def lista_tickets(request):

    busqueda = request.GET.get('q', '').strip()
    estado = request.GET.get('estado', '').strip()

    es_admin = (
        request.user.is_staff
        or request.user.is_superuser
        or request.user.groups.filter(name__icontains="admin").exists()
    )
    es_tecnico = request.user.groups.filter(name__in=["Tecnico", "Técnico", "tecnico"]).exists()

    if es_admin:
        # Administrador: visualiza todos los tickets del sistema
        tickets = Ticket.objects.all()
    elif es_tecnico:
        # Técnico: ÚNICAMENTE visualiza los tickets que tiene asignados
        tickets = Ticket.objects.filter(id_tecnico=request.user)
    else:
        # Cliente / Usuario común: visualiza únicamente sus tickets creados
        tickets = Ticket.objects.filter(usuario=request.user)

    if busqueda:
        tickets = tickets.filter(titulo__icontains=busqueda) | tickets.filter(
            descripcion__icontains=busqueda
        )

    if estado:
        tickets = tickets.filter(id_estado__nombre=estado)

    tickets = tickets.order_by('-fecha_creacion')

    return render(
        request,
        'tickets/lista_tickets.html',
        {
            'tickets': tickets,
            'busqueda': busqueda,
            'estado': estado,
            'es_admin': es_admin,
            'es_tecnico': es_tecnico,
            'es_tecnico_o_admin': es_admin or es_tecnico,
        }
    )


@login_required
def dashboard(request):

    total_tickets = Ticket.objects.count()

    tickets_abiertos = Ticket.objects.filter(id_estado__nombre='Abierto').count()
    tickets_proceso = Ticket.objects.filter(id_estado__nombre='En proceso').count()
    tickets_cerrados = Ticket.objects.filter(id_estado__nombre='Cerrado').count()

    # Contar tickets por categoría final (confirmada o, si no hay, la predicha)
    categorias_dict = {}

    for ticket in Ticket.objects.all():

        if ticket.id_categoria:
            categoria = ticket.id_categoria.nombre
        else:
            ultima_clasificacion = ticket.clasificaciones_ia.last()
            categoria = ultima_clasificacion.id_categoria.nombre if ultima_clasificacion else None

        if categoria:
            categorias_dict[categoria] = categorias_dict.get(categoria, 0) + 1

    categorias_labels = list(categorias_dict.keys())
    categorias_data = list(categorias_dict.values())

    estados_labels = ['Abierto', 'En proceso', 'Cerrado']
    estados_data = [tickets_abiertos, tickets_proceso, tickets_cerrados]

    contexto = {
        'total_tickets': total_tickets,
        'tickets_abiertos': tickets_abiertos,
        'tickets_proceso': tickets_proceso,
        'tickets_cerrados': tickets_cerrados,
        'categorias_labels': categorias_labels,
        'categorias_data': categorias_data,
        'estados_labels': estados_labels,
        'estados_data': estados_data,
    }

    return render(request, 'tickets/dashboard.html', contexto)

@login_required
def reportes(request):

    total_tickets = Ticket.objects.count()

    tickets_abiertos = Ticket.objects.filter(id_estado__nombre='Abierto').count()
    tickets_proceso = Ticket.objects.filter(id_estado__nombre='En proceso').count()
    tickets_cerrados = Ticket.objects.filter(id_estado__nombre='Cerrado').count()

    # Contar tickets por categoría final (confirmada o, si no hay, la predicha)
    categorias_dict = {}

    for ticket in Ticket.objects.all():

        if ticket.id_categoria:
            categoria = ticket.id_categoria.nombre
        else:
            ultima_clasificacion = ticket.clasificaciones_ia.last()
            categoria = ultima_clasificacion.id_categoria.nombre if ultima_clasificacion else None

        if categoria:
            categorias_dict[categoria] = categorias_dict.get(categoria, 0) + 1

    categorias_labels = list(categorias_dict.keys())
    categorias_data = list(categorias_dict.values())

    estados_labels = ['Abierto', 'En proceso', 'Cerrado']
    estados_data = [tickets_abiertos, tickets_proceso, tickets_cerrados]

    contexto = {
        'total_tickets': total_tickets,
        'tickets_abiertos': tickets_abiertos,
        'tickets_proceso': tickets_proceso,
        'tickets_cerrados': tickets_cerrados,
        'categorias_labels': categorias_labels,
        'categorias_data': categorias_data,
        'estados_labels': estados_labels,
        'estados_data': estados_data,
    }

    return render(request, 'tickets/reportes.html', contexto)


@login_required
def detalle_ticket(request, ticket_id):

    ticket = get_object_or_404(Ticket, id_ticket=ticket_id)

    if request.method == 'POST' and 'solucion' in request.POST:
        if not es_tecnico_o_admin(request.user):
            messages.error(request, 'No tienes permisos para responder a este ticket.')
            return redirect('detalle_ticket', ticket_id=ticket.id_ticket)

        solucion = request.POST.get('solucion', '').strip()
        if solucion:
            ticket.solucion = solucion
            ticket.save(update_fields=['solucion'])
            messages.success(request, 'Respuesta guardada correctamente.')
        else:
            messages.error(request, 'La respuesta no puede estar vacía.')

        return redirect('detalle_ticket', ticket_id=ticket.id_ticket)

    tecnicos_disponibles = User.objects.filter(groups__name='Tecnico')

    return render(
        request,
        'tickets/detalle_ticket.html',
        {
            'ticket': ticket,
            'tecnicos_disponibles': tecnicos_disponibles,
        }
    )


@login_required
def corregir_ticket(request, ticket_id):

    ticket = get_object_or_404(Ticket, id_ticket=ticket_id)

    if request.method == 'POST':

        nombre_categoria_corregida = request.POST.get('categoria_corregida')

        categoria_obj = get_object_or_404(Categoria, nombre=nombre_categoria_corregida)

        ticket.id_categoria = categoria_obj
        ticket.save()

        return redirect('detalle_ticket', ticket_id=ticket.id_ticket)

    return render(request, 'tickets/corregir_ticket.html', {'ticket': ticket})


@login_required
def cambiar_estado(request, ticket_id):

    ticket = get_object_or_404(Ticket, id_ticket=ticket_id)

    if request.method == 'POST':

        nuevo_estado = request.POST.get('estado')

        estados_validos = ['Abierto', 'En proceso', 'Cerrado']

        if nuevo_estado in estados_validos:

            estado_obj = get_object_or_404(Estado, nombre=nuevo_estado)
            ticket.id_estado = estado_obj

            if nuevo_estado == 'Cerrado':
                ticket.fecha_cierre = timezone.now()

            ticket.save()

        return redirect('detalle_ticket', ticket_id=ticket.id_ticket)

    return redirect('detalle_ticket', ticket_id=ticket.id_ticket)


# ---------------------------------------------------------------------------
# Usuarios (ahora sobre el modelo User de Django + Groups)
# ---------------------------------------------------------------------------

@login_required
def lista_usuarios(request):

    if not es_tecnico_o_admin(request.user):
        raise PermissionDenied

    busqueda = request.GET.get('q', '').strip()
    rol = request.GET.get('rol', '').strip()
    estado = request.GET.get('estado', '').strip()

    usuarios = User.objects.all()

    if busqueda:
        usuarios = usuarios.filter(first_name__icontains=busqueda) | usuarios.filter(last_name__icontains=busqueda) | usuarios.filter(email__icontains=busqueda)

    if rol:
        usuarios = usuarios.filter(groups__name=rol)

    if estado == "Activo":
        usuarios = usuarios.filter(is_active=True)
    elif estado == "Inactivo":
        usuarios = usuarios.filter(is_active=False)

    usuarios = usuarios.order_by('first_name')

    return render(
        request,
        'tickets/lista_usuarios.html',
        {
            'usuarios': usuarios,
            'busqueda': busqueda,
            'rol': rol,
            'estado': estado,
        }
    )


@login_required
def detalle_usuario(request, usuario_id):

    usuario = get_object_or_404(User, pk=usuario_id)

    todas_categorias = Categoria.objects.all().order_by('nombre')
    categorias_usuario_ids = list(
        usuario.especialidades.values_list('categoria_id', flat=True)
    )

    grupo_actual = usuario.groups.first()
    rol_actual = grupo_actual.name if grupo_actual else ''
    es_tecnico = usuario.groups.filter(name__in=['Tecnico', 'Técnico', 'tecnico']).exists()

    if es_tecnico:
        # Para técnicos: buscar los tickets que ha respondido (con solución registrada)
        tickets_respondidos = usuario.tickets_asignados.filter(
            solucion__isnull=False
        ).exclude(solucion__exact='').order_by('-fecha_cierre', '-fecha_creacion')
        tickets_usuario = tickets_respondidos
    else:
        # Para clientes/usuarios: tickets creados por ellos
        tickets_usuario = usuario.tickets.all().order_by('-fecha_creacion')[:10]
        tickets_respondidos = None

    return render(
        request,
        'tickets/detalle_usuario.html',
        {
            'usuario': usuario,
            'tickets_usuario': tickets_usuario,
            'tickets_respondidos': tickets_respondidos,
            'todas_categorias': todas_categorias,
            'categorias_usuario_ids': categorias_usuario_ids,
            'rol_actual': rol_actual,
            'es_usuario_tecnico': es_tecnico,
        }
    )


@login_required
def gestionar_usuario(request, usuario_id):

    if not (request.user.is_staff or request.user.is_superuser):
        raise PermissionDenied

    usuario = get_object_or_404(User, pk=usuario_id)

    if request.method == 'POST':

        nuevo_rol = request.POST.get('rol', '').strip()

        if nuevo_rol in ('Tecnico', 'Usuario'):

            grupo = get_object_or_404(Group, name=nuevo_rol)
            usuario.groups.clear()
            usuario.groups.add(grupo)

            # Limpia especialidades previas siempre; si sigue siendo Técnico,
            # las vuelve a crear con lo que venga marcado en el formulario.
            EspecialidadTecnico.objects.filter(tecnico=usuario).delete()

            if nuevo_rol == 'Tecnico':
                categorias_ids = request.POST.getlist('categorias')
                for cat_id in categorias_ids:
                    categoria = Categoria.objects.filter(id_categoria=cat_id).first()
                    if categoria:
                        EspecialidadTecnico.objects.create(tecnico=usuario, categoria=categoria)

        return redirect('detalle_usuario', usuario_id=usuario.id)

    return redirect('detalle_usuario', usuario_id=usuario.id)


@login_required
def configuracion(request):

    settings_usuario, creado = Settings.objects.get_or_create(
        usuario=request.user,
        defaults={
            'id_perfil': generar_siguiente_id(Settings, 'id_perfil', 'SET'),
            'tema': 'Claro',
            'idioma': 'Español',
            'interfaz': 'Cómoda',
        }
    )

    if request.method == 'POST':

        settings_usuario.tema = request.POST.get('tema')
        settings_usuario.idioma = request.POST.get('idioma')
        settings_usuario.interfaz = request.POST.get('interfaz')
        settings_usuario.save()

        rol_param = request.GET.get('rol', '')
        if rol_param:
            return redirect(f'/configuracion/?rol={rol_param}')
        return redirect('configuracion')

    # Soporte para previsualizar roles con pestañas o parámetro ?rol=admin / ?rol=tecnico / ?rol=cliente
    rol_preview = request.GET.get('rol', '').lower()
    contexto = {
        'settings': settings_usuario,
        'rol_preview': rol_preview,
    }

    if rol_preview == 'admin':
        contexto['es_admin'] = True
        contexto['es_tecnico'] = False
        contexto['rol_nombre'] = 'ADMINISTRADOR'
    elif rol_preview in ('tecnico', 'tech'):
        contexto['es_admin'] = False
        contexto['es_tecnico'] = True
        contexto['rol_nombre'] = 'TECNICO'
    elif rol_preview in ('cliente', 'usuario'):
        contexto['es_admin'] = False
        contexto['es_tecnico'] = False
        contexto['rol_nombre'] = 'CLIENTE'

    return render(
        request,
        'tickets/settings.html',
        contexto
    )