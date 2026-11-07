import random
from django.contrib.auth.decorators import login_required
from django.contrib.auth import update_session_auth_hash, authenticate, login

from django.contrib.auth.views import LoginView

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login as auth_login
from django.contrib.auth.models import User, Group
from django.utils import timezone
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
from django.http import JsonResponse
from webpush import send_user_notification

from .models import Ticket, Categoria, Prioridad, Estado, ClasificacionIA, Settings, EspecialidadTecnico
from .ml_service import predecir_categoria, predecir_prioridad
from .forms import RegistroForm

from django.core.exceptions import PermissionDenied

from twilio.rest import Client


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
            messages.error(request, 'La respuesta no puede estar vacía.')
        else:
            ticket.solucion = solucion
            ticket.save(update_fields=['solucion'])

            # --- LÓGICA DE CORREO ---
            # Usamos .id para asegurar que la comparación sea exacta
            if request.user.id != ticket.usuario.id:
                
                if ticket.usuario.email:
                    asunto = f'TIX AI: Nueva respuesta en tu ticket #{ticket.id_ticket}'
                    mensaje = f"Hola {ticket.usuario.username},\n\nTienes una nueva respuesta en tu ticket '{ticket.titulo}'.\n\nRespuesta:\n{ticket.solucion}\n\nIngresa al portal para ver más detalles."
                    
                    send_mail(
                        subject=asunto,
                        message=mensaje,
                        from_email=None,
                        recipient_list=[ticket.usuario.email],
                        fail_silently=False,
                    )
                    messages.success(request, 'Respuesta guardada y notificada por correo al cliente.')
                else:
                    messages.warning(request, 'Respuesta guardada. ADVERTENCIA: El usuario no tiene correo registrado.')
            else:
                messages.info(request, 'Respuesta guardada. (No se envió correo porque tú eres el creador de este ticket).')
            # ------------------------

            return redirect('detalle_ticket', id_ticket=ticket.id_ticket)

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

        # --- LÓGICA DE CORREO ---
        # Obtener los correos de todos los técnicos (is_staff o tu lógica para definir un técnico)
        # --- LÓGICA DE CORREO ---
        # Buscar a todos los usuarios que pertenezcan al grupo 'Tecnico' y tengan un correo registrado
        correos_tecnicos = list(User.objects.filter(groups__name='Tecnico').exclude(email='').values_list('email', flat=True))
        
        # Opcional: si quieres que también le llegue a los administradores (staff)
        correos_admin = list(User.objects.filter(is_staff=True).exclude(email='').values_list('email', flat=True))
        
        # Unimos ambas listas sin repetir correos
        correos_destino = list(set(correos_tecnicos + correos_admin))
                    
        asunto = f'TIX AI: Nuevo Ticket de {ticket.usuario.username} - {ticket.titulo}'
        mensaje = f"Se ha creado un nuevo ticket en la plataforma.\n\nDescripción:\n{ticket.descripcion}\n\nIngresa al sistema para revisarlo y asignar a la IA o un agente."

        

        # Obtener staff/técnicos
        tecnicos = User.objects.filter(is_staff=True)
    
        payload = {
            "head": "Nuevo Ticket Creado",
            "body": f"El usuario {request.user.username} ha creado un nuevo ticket.",
            "url": f"/ticket/{ticket.id_ticket}/" # Ajusta la variable al identificador de tu URL (ej. TCK0029)
        }
    
        for tecnico in tecnicos:
            # 1. Extraemos el objeto único de configuración del técnico
            ajustes = tecnico.settings.first() 
        
            # 2. Verificamos si existe la configuración y si tiene las alertas activadas
            if ajustes and ajustes.notif_push:
                try:
                    send_user_notification(user=tecnico, payload=payload, ttl=1000)
                except Exception as e:
                    print(f"Error enviando webpush al técnico {tecnico.username}: {e}")

        notificaciones_activadas = False
                        
        # 1. Extraemos el objeto único de configuración del usuario (usando .first())
        ajustes_usuario = ticket.usuario.settings.first()
                        
        # 2. Verificamos si tiene la configuración creada y extraemos el valor
        if ajustes_usuario:
            notificaciones_activadas = ajustes_usuario.alertas_estado
        
        if notificaciones_activadas:
                   
            if correos_destino:

                send_mail(
                    subject=asunto,
                    message=mensaje,
                    from_email=None,
                    recipient_list=correos_tecnicos,
                    fail_silently=False, # Evita que la app se caiga si falla el envío
                )

                messages.success(request, 'Ticket creado correctamente. Se ha notificado a los técnicos por correo.')
            else:
                # Mensaje por si no hay técnicos registrados con correo
                messages.warning(request, 'Ticket creado, pero no se encontraron correos de técnicos para notificar.')
            # ------------------------

            return redirect('detalle_ticket', ticket_id=ticket.id_ticket)

    return render(request, 'tickets/nuevo_ticket.html')


@login_required
def actualizar_ticket(request, ticket_id):
    ticket = get_object_or_404(Ticket, id_ticket=ticket_id)

    if not es_tecnico_o_admin(request.user):
        messages.error(
            request,
            'No tienes permisos para modificar este ticket.'
        )
        return redirect('detalle_ticket', ticket_id=ticket.id_ticket)

    if request.method != 'POST':
        return redirect('detalle_ticket', ticket_id=ticket.id_ticket)

    # Obtener los datos enviados desde el formulario
    categoria_id = request.POST.get('categoria')
    prioridad_id = request.POST.get('prioridad')
    nuevo_estado = request.POST.get('estado')
    tecnico_id = request.POST.get('tecnico')
    solucion = request.POST.get('solucion')

    # Actualizar categoría
    if categoria_id:
        ticket.id_categoria = get_object_or_404(
            Categoria, pk=categoria_id
        )
    else:
        ticket.id_categoria = None

    # Actualizar prioridad
    if prioridad_id:
        ticket.id_prioridad = get_object_or_404(
            Prioridad, pk=prioridad_id
        )
    else:
        ticket.id_prioridad = None

    # Actualizar estado
    if nuevo_estado:
        estados_validos = ['Abierto', 'En proceso', 'Cerrado']

        if nuevo_estado not in estados_validos:
            messages.error(request, 'El estado seleccionado no es válido.')
            return redirect(
                'detalle_ticket', ticket_id=ticket.id_ticket
            )

        ticket.id_estado = get_object_or_404(
            Estado, nombre=nuevo_estado
        )

        # Registrar fecha de cierre
        if nuevo_estado == 'Cerrado':
            if not ticket.fecha_cierre:
                ticket.fecha_cierre = timezone.now()
        else:
            ticket.fecha_cierre = None

    # Actualizar técnico asignado
    if tecnico_id:
        tecnico = get_object_or_404(
            User,
            pk=tecnico_id,
            groups__name='Tecnico'
        )

        if ticket.id_tecnico_id != tecnico.id:
            ticket.id_tecnico = tecnico
            ticket.fecha_asignacion = timezone.now()
    else:
        ticket.id_tecnico = None
        ticket.fecha_asignacion = None

    # Actualizar respuesta o solución
    if solucion is not None:
        ticket.solucion = solucion.strip() or None

    # Guardar todos los cambios en una sola operación
    ticket.save()

    messages.success(
        request,
        'Los detalles del ticket se actualizaron correctamente.'
    )

    return redirect('detalle_ticket', ticket_id=ticket.id_ticket)





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

            # Asumiendo que 'ticket' es la instancia del ticket al que se está respondiendo
            payload = {
                "head": "Nueva Respuesta en tu Ticket",
                "body": "Un técnico ha respondido a tu solicitud.",
                "url": f"/ticket/{ticket.id_ticket}/" 
            }
    
            try:
                ajustes_usuario = ticket.usuario.settings.first()

                if ajustes_usuario and ajustes_usuario.notif_push:
                    send_user_notification(
                    user=ticket.usuario,
                    payload=payload,
                    ttl=1000
                )

            except Exception as e:
                print(f"Error enviando webpush al cliente: {e}")
            
            # --- LÓGICA DE CORREO ---
            if request.user.id != ticket.usuario.id:

                # 1. Verificar si el usuario tiene las notificaciones activadas
                # (Asumiendo que tu modelo de configuración está enlazado como .settings)
                notificaciones_activadas = False
                
                if hasattr(ticket.usuario, 'settings'):
                    # Si usa el campo alertas_estado de tu base de datos
                    notificaciones_activadas = ticket.usuario.settings.alertas_estado

                if notificaciones_activadas:

                    if ticket.usuario.email:
                        asunto = f'TIX AI: Nueva respuesta en tu ticket #{ticket.id_ticket}'
                        mensaje = f"Hola {ticket.usuario.username},\n\nTienes una nueva respuesta en tu ticket '{ticket.titulo}'.\n\nRespuesta:\n{ticket.solucion}\n\nIngresa al portal para ver más detalles."
                    
                        send_mail(
                            subject=asunto,
                            message=mensaje,
                            from_email=None,
                            recipient_list=[ticket.usuario.email],
                            fail_silently=False,
                        )
                        messages.success(request, 'Respuesta guardada y notificada por correo al cliente.')
                    else:
                        messages.warning(request, 'Respuesta guardada. ADVERTENCIA: El usuario no tiene correo registrado.')
            else:
                messages.info(request, 'Respuesta guardada. (No se envió correo porque tú eres el creador de este ticket).')
            # ------------------------
            
        else:
            messages.error(request, 'La respuesta no puede estar vacía.')

        return redirect('detalle_ticket', ticket_id=ticket.id_ticket)

    tecnicos_disponibles = User.objects.filter(groups__name='Tecnico')

    return render(request, 'tickets/detalle_ticket.html', {
        'ticket': ticket,
        'tecnicos_disponibles': tecnicos_disponibles,
        'es_tecnico_o_admin': es_tecnico_o_admin(request.user),
        'categorias': Categoria.objects.all(),
        'prioridades': Prioridad.objects.all(),
    })
 


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

    
    
    # 1. Obtener el color global actual
    color_actual = "Púrpura"
    ajuste_existente = Settings.objects.first()
    if ajuste_existente and hasattr(ajuste_existente, 'tema_color'):
        color_actual = ajuste_existente.tema_color

    

    # 2. Cargar o crear configuración del usuario
    settings_usuario, creado = Settings.objects.get_or_create(
        usuario=request.user,
        defaults={
            'id_perfil': generar_siguiente_id(Settings, 'id_perfil', 'SET'),
            'tema': False,  
            'idioma': 'Español',
            'interfaz': 'Cómoda',
            'tema_color': color_actual, 
        }
    )

    # Identificamos el rol REAL del usuario
    es_admin = (
        request.user.is_staff 
        or request.user.is_superuser 
        or request.user.groups.filter(name__icontains="admin").exists()
    )
    es_tecnico = request.user.groups.filter(name__in=["Tecnico", "Técnico", "tecnico"]).exists()

    # Identificamos si está usando el modo "Previsualizar" mediante la URL (?rol=tecnico)
    rol_preview = request.GET.get('rol', '').lower()
    
    # Determinamos qué formulario (Admin o Técnico) se está enviando realmente
    esta_viendo_como_admin = es_admin
    if rol_preview in ['tecnico', 'tech', 'cliente', 'usuario']:
        esta_viendo_como_admin = False

    if request.method == 'POST':

        
        # --- CAMPOS COMPARTIDOS ---
        if 'idioma' in request.POST:
            settings_usuario.idioma = request.POST.get('idioma')
            
        if 'interfaz' in request.POST:
            settings_usuario.interfaz = request.POST.get('interfaz')


        quiere_2fa = request.POST.get('dos_factores') == 'on'
            
        settings_usuario.tema = request.POST.get('tema') == 'on'

        # --- CAMPOS DIVIDIDOS POR LA VISTA ACTUAL ---
        if esta_viendo_como_admin:
            
            # TEMA COLOR (Global)
            nuevo_tema_color = request.POST.get('tema_color')
            if nuevo_tema_color and nuevo_tema_color != settings_usuario.tema_color:
                settings_usuario.tema_color = nuevo_tema_color
                Settings.objects.all().update(tema_color=nuevo_tema_color)

            # Notificaciones Admin
            settings_usuario.notif_push = request.POST.get('notif_push') == 'on'
            settings_usuario.alertas_criticas = request.POST.get('alertas_criticas') == 'on'
            settings_usuario.resumen_diario = request.POST.get('resumen_diario') == 'on'
            
            # Seguridad Admin
            settings_usuario.dos_factores_obligatorio = request.POST.get('dos_factores_obligatorio') == 'on'
            
            # Inteligencia Artificial Admin
            settings_usuario.asignacion_automatica = request.POST.get('asignacion_automatica') == 'on'
            settings_usuario.sugerencias_respuesta = request.POST.get('sugerencias_respuesta') == 'on'
            
            umbral = request.POST.get('umbral_ia')
            if umbral and umbral.isdigit():
                settings_usuario.umbral_ia = int(umbral)
                
        else:
            # Notificaciones Técnico/Usuario
            settings_usuario.notif_push = request.POST.get('notif_push') == 'on'
            
            # ¡AQUÍ SE GUARDA LA ALERTA DE ESTADO PARA LOS CORREOS!
            settings_usuario.alertas_estado = request.POST.get('alertas_estado') == 'on'
            settings_usuario.resumen_semanal = request.POST.get('resumen_semanal') == 'on'
            
            # Seguridad Técnico/Usuario
            settings_usuario.dos_factores = request.POST.get('dos_factores') == 'on'

            if quiere_2fa and not settings_usuario.telefono:
            # Si quiere activarlo pero no tiene número, lo mandamos a registrarlo
                return redirect('vincular_telefono')
            
            settings_usuario.dos_factores = quiere_2fa
        # Guardamos en la base de datos
        settings_usuario.save()
        
        # DETECCIÓN DE AUTOGUARDADO (AJAX) - CORREGIDO PARA DJANGO
        is_ajax = request.META.get('HTTP_X_REQUESTED_WITH') == 'XMLHttpRequest'
        if is_ajax:
            return JsonResponse({'status': 'ok', 'mensaje': 'Autoguardado exitoso'})
            
        # Comportamiento normal si no es AJAX
        messages.success(request, 'Configuración guardada exitosamente.')
        if rol_preview:
            return redirect(f'/configuracion/?rol={rol_preview}')
        return redirect('configuracion')
    
    # --- PREPARACIÓN DE DATOS PARA RENDERIZAR (GET) ---
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
    else:
        contexto['es_admin'] = es_admin
        contexto['es_tecnico'] = es_tecnico
        contexto['rol_nombre'] = 'ADMINISTRADOR' if es_admin else ('TECNICO' if es_tecnico else 'CLIENTE')

    return render(request, 'tickets/settings.html', contexto)

@login_required
def editar_perfil(request):
    usuario = request.user

    if request.method == 'POST':
        nombre = request.POST.get('nombre', '').strip()
        apellido = request.POST.get('apellido', '').strip()
        correo = request.POST.get('correo', '').strip()
        telefono = request.POST.get('telefono', '').strip()

        if not correo:
            messages.error(request, 'El correo electrónico es obligatorio.')

        elif User.objects.exclude(pk=usuario.pk).filter(email=correo).exists():
            messages.error(request, 'Este correo ya está en uso por otra cuenta.')

        else:
            # Validar si el teléfono está en uso antes de hacer nada más
            telefono_en_uso = Settings.objects.filter(telefono=telefono).exclude(usuario=usuario).exists()

            if telefono_en_uso:
                messages.error(request, 'Este número de teléfono ya está registrado en otra cuenta.')
                # Detenemos la ejecución aquí para que NO guarde el dato duplicado
                return render(request, 'tickets/editar_perfil.html', {'usuario': usuario})

            # Si pasa la validación, guardamos el usuario
            usuario.first_name = nombre
            usuario.last_name = apellido
            usuario.email = correo
            usuario.username = correo
            usuario.save()

            # Buscamos su configuración actual usando .first()
            ajustes_usuario = usuario.settings.first()

            if ajustes_usuario:
                ajustes_usuario.telefono = telefono
                ajustes_usuario.save()
            else:
                # Si no existe, lo creamos generando correctamente su id_perfil
                Settings.objects.create(
                    id_perfil=generar_siguiente_id(Settings, 'id_perfil', 'SET'),
                    usuario=usuario,
                    telefono=telefono
                )

            messages.success(request, 'Tu perfil se actualizó correctamente.')
            return redirect('configuracion')

    return render(
        request,
        'tickets/editar_perfil.html',
        {'usuario': usuario}
    )

@login_required
def solicitar_codigo_password(request):
    usuario = request.user

    # Si el usuario hace POST, significa que está enviando el código que le llegó al correo
    if request.method == 'POST':
        codigo_ingresado = request.POST.get('codigo', '').strip()
        codigo_guardado = request.session.get('codigo_recuperacion')

        # Verificamos si el código coincide
        if codigo_guardado and codigo_ingresado == str(codigo_guardado):
            # Limpiamos el código de la sesión por seguridad
            del request.session['codigo_recuperacion']
            # Creamos una llave en la sesión para autorizar que entre a la pantalla de cambiar clave
            request.session['autorizado_cambio_clave'] = True
            
            messages.success(request, 'Código verificado correctamente.')
            return redirect('cambiar_contrasena')
        else:
            messages.error(request, 'El código ingresado es incorrecto o ha caducado.')
            return render(request, 'tickets/verificar_codigo.html')

    # Si entra por GET (cuando recién hace clic en el botón de Settings)
    # 1. Generamos un código de 6 dígitos
    codigo = random.randint(100000, 999999)
    # 2. Lo guardamos en la sesión
    request.session['codigo_recuperacion'] = codigo

    # 3. Enviamos el correo
    asunto = 'Código de seguridad para cambiar tu contraseña - TIX AI'
    mensaje = f'Hola {usuario.first_name},\n\nTu código de seguridad para cambiar la contraseña es: {codigo}\n\nPor favor, ingresa este código en la página para continuar.\nSi no solicitaste esto, ignora este correo.'
    
    try:        
        send_mail(
            subject=asunto,
            message=mensaje,
            from_email=None,
            recipient_list=[usuario.email],
            fail_silently=False,
        )
        messages.success(request, f'Hemos enviado un código de seguridad a {usuario.email}')
    except Exception as e:
        messages.error(request, 'Hubo un error al enviar el correo. Intenta de nuevo más tarde.')

    # 4. Mostramos la pantalla para que ingrese el código
    return render(request, 'tickets/verificar_codigo.html')


@login_required
def cambiar_password(request):
    # Validamos que el usuario haya pasado por el paso del código primero
    if not request.session.get('autorizado_cambio_clave'):
        messages.warning(request, 'Debes verificar tu identidad con un código primero.')
        return redirect('solicitar_codigo_password')

    if request.method == 'POST':
        nueva_password = request.POST.get('nueva_password')
        confirmar_password = request.POST.get('confirmar_password')

        if nueva_password and nueva_password == confirmar_password:
            usuario = request.user
            
            # --- NUEVA VALIDACIÓN ---
            # Verificamos si la nueva contraseña es igual a la contraseña actual
            if usuario.check_password(nueva_password):
                messages.error(request, 'La nueva contraseña no puede ser igual a tu contraseña actual. Por favor, elige una diferente.')
            else:
                # Si es diferente, la encriptamos y la guardamos
                usuario.set_password(nueva_password)
                usuario.save()
                
                # Mantiene la sesión iniciada después de cambiar la contraseña
                update_session_auth_hash(request, usuario)
                
                # Quitamos la autorización para que no pueda volver a esta URL directamente
                del request.session['autorizado_cambio_clave']
                
                messages.success(request, '¡Contraseña actualizada con éxito!')
                return redirect('configuracion') 
                
        else:
            messages.error(request, 'Las contraseñas no coinciden. Inténtalo de nuevo.')

    return render(request, 'tickets/cambiar_password.html')


class CustomLoginView(LoginView):
    template_name = 'tickets/login.html' # Mantenemos tu misma plantilla

    def form_valid(self, form):
        # form_valid se ejecuta SOLO si el usuario y contraseña son correctos
        user = form.get_user()
        
        # Extraemos la configuración del usuario usando .first()[cite: 3]
        ajustes_usuario = user.settings.first()
        
        # Verificamos si tiene la configuración y si el campo dos_factores es True
        if ajustes_usuario and getattr(ajustes_usuario, 'dos_factores', False):
            
            # 1. Guardamos el ID del usuario en la sesión temporalmente
            self.request.session['pre_2fa_user_id'] = user.id
            
            # 2. Lo redirigimos a la pantalla para que elija SMS o Correo
            return redirect('seleccionar_metodo_2fa')
        
        # Si NO tiene activado el 2FA, iniciamos sesión normalmente (comportamiento por defecto)
        return super().form_valid(form)


def verificar_2fa(request):
    # Si alguien intenta entrar a esta URL sin pasar por el login, lo echamos
    if 'pre_2fa_user_id' not in request.session:
        return redirect('login')

    if request.method == 'POST':
        codigo_ingresado = request.POST.get('codigo', '').strip()
        codigo_real = request.session.get('codigo_2fa')
        
        if codigo_ingresado == codigo_real:
            # ¡Código correcto! Buscamos al usuario y lo logueamos oficialmente
            user_id = request.session.get('pre_2fa_user_id')
            user = User.objects.get(id=user_id)
            
            login(request, user)
            
            # Limpiamos la basura de la sesión por seguridad
            del request.session['codigo_2fa']
            del request.session['pre_2fa_user_id']
            
            messages.success(request, 'Autenticación exitosa.')
            return redirect('configuracion') # <-- Cambia esto por la url de tu inicio o dashboard
        else:
            messages.error(request, 'Código incorrecto. Revisa tu correo e intenta nuevamente.')

    return render(request, 'tickets/verificar_2fa.html')


@login_required
def vincular_telefono(request):
    if request.method == 'POST':
        numero = request.POST.get('telefono')
        if numero:
            codigo = str(random.randint(100000, 999999))
            request.session['codigo_sms'] = codigo
            request.session['telefono_temp'] = numero
            
            # --- ENVÍO DE SMS REAL CON TWILIO ---
            try:
                client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
                message = client.messages.create(
                    body=f"TIX AI: Tu codigo de verificacion es {codigo}",
                    from_=settings.TWILIO_PHONE_NUMBER,
                    to=numero # El número debe incluir el código de país (ej: +56912345678)
                )
                messages.success(request, 'SMS enviado correctamente. Revisa tu celular.')
            except Exception as e:
                messages.error(request, f'Error al enviar SMS: {e}')
                return redirect('vincular_telefono')
                
            return redirect('verificar_telefono')
    return render(request, 'tickets/vincular_telefono.html')

@login_required
def verificar_telefono(request):
    if request.method == 'POST':
        codigo_ingresado = request.POST.get('codigo')
        codigo_real = request.session.get('codigo_sms')
        
        if codigo_ingresado == codigo_real:
            # El código es correcto: Guardamos el teléfono y activamos el 2FA automáticamente
            ajustes = request.user.settings.first()
            ajustes.telefono = request.session.get('telefono_temp')
            ajustes.dos_factores = True
            ajustes.save()
            
            # Limpieza de sesión
            del request.session['codigo_sms']
            del request.session['telefono_temp']
            
            messages.success(request, 'Teléfono verificado. 2FA activado correctamente.')
            return redirect('configuracion')
        else:
            messages.error(request, 'Código incorrecto.')
            
    return render(request, 'tickets/verificar_telefono.html')


# En views.py (Asegúrate de tener importados send_mail, settings, y Twilio Client)
def seleccionar_metodo_2fa(request):
    # Validar que venga del login
    if 'pre_2fa_user_id' not in request.session:
        return redirect('login')

    user_id = request.session.get('pre_2fa_user_id')
    from django.contrib.auth.models import User
    user = User.objects.get(id=user_id)
    ajustes_usuario = user.settings.first()
    numero_registrado = getattr(ajustes_usuario, 'telefono', None)

    if request.method == 'POST':
        metodo = request.POST.get('metodo')
        
        # Generar el código solo cuando hace clic en un botón
        import random
        codigo_2fa = str(random.randint(100000, 999999))
        request.session['codigo_2fa'] = codigo_2fa

        if metodo == 'sms':
            if numero_registrado:
                try:
                    client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
                    client.messages.create(
                        body=f"TIX AI: Tu codigo de acceso 2FA es {codigo_2fa}",
                        from_=settings.TWILIO_PHONE_NUMBER,
                        to=numero_registrado
                    )
                    messages.success(request, 'Código enviado a tu teléfono por SMS.')
                    return redirect('verificar_2fa')
                except Exception as e:
                    messages.error(request, 'Problema al enviar SMS. Intenta con correo.')
            else:
                messages.error(request, 'No tienes un número de teléfono registrado.')
        
        elif metodo == 'email':
            try:
                send_mail(
                    'Tu código de acceso 2FA - TIX AI',
                    f'Hola {user.username},\n\nTu código de verificación de 2 Factores es: {codigo_2fa}',
                    from_email=None,
                    recipient_list=[user.email],
                    fail_silently=False,
                )
                messages.success(request, 'Código enviado a tu correo electrónico.')
                return redirect('verificar_2fa')
            except Exception as e:
                messages.error(request, 'Problema al enviar el correo.')

    return render(request, 'tickets/seleccionar_metodo_2fa.html', {'tiene_telefono': bool(numero_registrado)})