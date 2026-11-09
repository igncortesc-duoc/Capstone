import random
import re
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
# bloqueo de inicio de sesion
# ---------------------------------------------------------------------------
def tixai_lockout(request, response, credentials, *args, **kwargs):
    return render(
        request,
        'tickets/login.html',
        {
            'lockout_message': (
                'Has superado el límite de 5 intentos fallidos. '
                'Por seguridad, tu acceso ha sido bloqueado durante '
                '15 minutos. Inténtalo nuevamente después de ese período.'
            ),
            'next': request.POST.get('next', ''),
        },
        status=429
    )
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
    ids = list(
        modelo.objects.filter(**{f"{campo_id}__startswith": prefijo})
        .values_list(campo_id, flat=True)
    )
    patron = re.compile(rf"^{re.escape(prefijo)}(\d+)$")
    numeros = []
    for val in ids:
        m = patron.match(str(val))
        if m:
            try:
                numeros.append(int(m.group(1)))
            except ValueError:
                pass

    siguiente = max(numeros) + 1 if numeros else 1
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

            telefono = (data.get('telefono') or '').strip() or None
            Settings.objects.create(
                id_perfil=generar_siguiente_id(Settings, 'id_perfil', 'SET'),
                usuario=user,
                telefono=telefono,
            )

            auth_login(request, user, backend='django.contrib.auth.backends.ModelBackend')
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

            return redirect('detalle_ticket', ticket_id=ticket.id_ticket)

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
        print("========== DEPURACIÓN TIXAI ==========")
        print("Categoría predicha:", repr(categoria))
        print("Objeto categoría:", categoria_obj)
        print("ID categoría:", categoria_obj.pk if categoria_obj else None)
        print("Prioridad predicha:", repr(prioridad))
        print("Objeto prioridad:", prioridad_obj)
        print("======================================")
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
            id_categoria=categoria_obj
        )
        ticket.refresh_from_db()

        print("========== TICKET GUARDADO ==========")
        print("ID ticket:", ticket.id_ticket)
        print("Categoría FK:", ticket.id_categoria_id)
        print("Prioridad FK:", ticket.id_prioridad_id)
        print("=====================================")
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
                try:
                    send_mail(
                        subject=asunto,
                        message=mensaje,
                        from_email=None,
                        recipient_list=correos_destino,
                        fail_silently=False,
                    )
                    messages.success(request, 'Ticket creado correctamente. Se ha notificado a los técnicos por correo.')
                except Exception as e:
                    messages.warning(request, f'Ticket creado. No se pudo enviar correo a los técnicos: {e}')
            else:
                messages.info(request, 'Ticket creado exitosamente.')
        else:
            messages.success(request, 'Ticket creado exitosamente.')

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

    # Actualizar categoría solo si viene en la petición
    if 'categoria' in request.POST:
        categoria_id = request.POST.get('categoria')
        if categoria_id:
            ticket.id_categoria = get_object_or_404(Categoria, pk=categoria_id)
        else:
            ticket.id_categoria = None

    # Actualizar prioridad solo si viene en la petición
    if 'prioridad' in request.POST:
        prioridad_id = request.POST.get('prioridad')
        if prioridad_id:
            ticket.id_prioridad = get_object_or_404(Prioridad, pk=prioridad_id)
        else:
            ticket.id_prioridad = None

    # Actualizar estado solo si viene en la petición
    if 'estado' in request.POST:
        nuevo_estado = request.POST.get('estado')
        estados_validos = ['Abierto', 'En proceso', 'Cerrado']
        if nuevo_estado in estados_validos:
            ticket.id_estado = get_object_or_404(Estado, nombre=nuevo_estado)
            if nuevo_estado == 'Cerrado':
                if not ticket.fecha_cierre:
                    ticket.fecha_cierre = timezone.now()
            else:
                ticket.fecha_cierre = None
        elif nuevo_estado:
            messages.error(request, 'El estado seleccionado no es válido.')
            return redirect('detalle_ticket', ticket_id=ticket.id_ticket)

    # Actualizar técnico asignado solo si viene en la petición
    if 'tecnico' in request.POST:
        tecnico_id = request.POST.get('tecnico')
        if tecnico_id:
            tecnico = get_object_or_404(User, pk=tecnico_id, groups__name='Tecnico')
            if ticket.id_tecnico_id != tecnico.id:
                ticket.id_tecnico = tecnico
                ticket.fecha_asignacion = timezone.now()
        else:
            ticket.id_tecnico = None
            ticket.fecha_asignacion = None

    # Actualizar respuesta o solución
    if 'solucion' in request.POST:
        solucion = request.POST.get('solucion')
        if solucion is not None:
            ticket.solucion = solucion.strip() or None

    ticket.save()
    messages.success(request, 'Los detalles del ticket se actualizaron correctamente.')
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
    es_admin = (
        request.user.is_staff
        or request.user.is_superuser
        or request.user.groups.filter(name__icontains="admin").exists()
    )
    es_tecnico = request.user.groups.filter(name__in=["Tecnico", "Técnico", "tecnico"]).exists()

    if es_admin:
        # Administrador: visualiza todos los tickets del sistema
        tickets_base = Ticket.objects.all()
    elif es_tecnico:
        # Técnico: visualiza únicamente los tickets que tiene asignados
        tickets_base = Ticket.objects.filter(id_tecnico=request.user)
    else:
        # Cliente / Usuario común: visualiza ÚNICAMENTE sus tickets creados
        tickets_base = Ticket.objects.filter(usuario=request.user)

    total_tickets = tickets_base.count()
    tickets_abiertos = tickets_base.filter(id_estado__nombre='Abierto').count()
    tickets_proceso = tickets_base.filter(id_estado__nombre='En proceso').count()
    tickets_cerrados = tickets_base.filter(id_estado__nombre='Cerrado').count()

    # Contar tickets por categoría final (confirmada o, si no hay, la predicha)
    categorias_dict = {}
    for ticket in tickets_base:
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
        'es_admin': es_admin,
        'es_tecnico': es_tecnico,
    }

    return render(request, 'tickets/dashboard.html', contexto)

@login_required
def reportes(request):
    if not es_tecnico_o_admin(request.user):
        raise PermissionDenied

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
    if not (es_tecnico_o_admin(request.user) or ticket.usuario == request.user):
        raise PermissionDenied

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
                ajustes_usuario = ticket.usuario.settings.first()
                notificaciones_activadas = getattr(ajustes_usuario, 'alertas_estado', True) if ajustes_usuario else True

                if notificaciones_activadas:
                    if ticket.usuario.email:
                        asunto = f'TIX AI: Nueva respuesta en tu ticket #{ticket.id_ticket}'
                        mensaje = f"Hola {ticket.usuario.username},\n\nTienes una nueva respuesta en tu ticket '{ticket.titulo}'.\n\nRespuesta:\n{ticket.solucion}\n\nIngresa al portal para ver más detalles."
                        try:
                            send_mail(
                                subject=asunto,
                                message=mensaje,
                                from_email=None,
                                recipient_list=[ticket.usuario.email],
                                fail_silently=False,
                            )
                            messages.success(request, 'Respuesta guardada y notificada por correo al cliente.')
                        except Exception as e:
                            messages.warning(request, f'Respuesta guardada. No se pudo enviar el correo de notificación: {e}')
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
    if not es_tecnico_o_admin(request.user):
        raise PermissionDenied

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

        # Validar los roles permitidos
        if nuevo_rol not in ('Tecnico', 'Usuario'):
            messages.error(request, 'El rol seleccionado no es válido.')
            return redirect('detalle_usuario', usuario_id=usuario.id)

        # Obtener el grupo o crearlo si todavía no existe
        grupo, creado = Group.objects.get_or_create(name=nuevo_rol)

        # Eliminar los roles anteriores
        usuario.groups.clear()

        # Asignar el nuevo rol
        usuario.groups.add(grupo)

        # Limpiar las especialidades anteriores
        EspecialidadTecnico.objects.filter(tecnico=usuario).delete()

        # Si ahora es técnico, registrar sus especialidades
        if nuevo_rol == 'Tecnico':

            categorias_ids = request.POST.getlist('categorias')

            for cat_id in categorias_ids:
                categoria = Categoria.objects.filter(
                    id_categoria=cat_id
                ).first()

                if categoria:
                    EspecialidadTecnico.objects.get_or_create(
                        tecnico=usuario,
                        categoria=categoria
                    )

        messages.success(
            request,
            f'El rol de {usuario.username} se actualizó correctamente.'
        )

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
            telefono_limpio = telefono.strip() if telefono else ""
            telefono_en_uso = (
                bool(telefono_limpio)
                and Settings.objects.filter(telefono=telefono_limpio).exclude(usuario=usuario).exists()
            )

            if telefono_en_uso:
                messages.error(request, 'Este número de teléfono ya está registrado en otra cuenta.')
                return render(request, 'tickets/editar_perfil.html', {'usuario': usuario})

            usuario.first_name = nombre
            usuario.last_name = apellido
            usuario.email = correo
            usuario.username = correo
            usuario.save()

            ajustes_usuario = usuario.settings.first()

            if ajustes_usuario:
                ajustes_usuario.telefono = telefono_limpio or None
                ajustes_usuario.save()
            else:
                Settings.objects.create(
                    id_perfil=generar_siguiente_id(Settings, 'id_perfil', 'SET'),
                    usuario=usuario,
                    telefono=telefono_limpio or None
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
    print(f'\n========================================\n[TIX AI] CODIGO DE SEGURIDAD PARA {usuario.email}: {codigo}\n========================================\n')

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
    # Validamos que el usuario haya pasado por el paso del codigo primero
    if not request.session.get('autorizado_cambio_clave'):
        messages.warning(request, 'Debes verificar tu identidad con un codigo primero.')
        return redirect('solicitar_codigo_password')

    if request.method == 'POST':
        nueva_password = request.POST.get('nueva_password', '')
        confirmar_password = request.POST.get('confirmar_password', '')

        if not nueva_password or not confirmar_password:
            messages.error(request, 'Por favor, completa ambos campos de contraseña.')
        elif len(nueva_password) < 8:
            messages.error(request, 'La nueva contraseña debe tener al menos 8 caracteres.')
        elif nueva_password != confirmar_password:
            messages.error(request, 'Las contraseñas no coinciden. Inténtalo de nuevo.')
        elif request.user.check_password(nueva_password):
            messages.error(request, 'La nueva contraseña no puede ser igual a tu contraseña actual. Por favor, elige una diferente.')
        else:
            usuario = request.user
            usuario.set_password(nueva_password)
            usuario.save()

            # Mantiene la sesion iniciada despues de cambiar la contraseña
            update_session_auth_hash(request, usuario)

            # Quitamos la autorizacion para que no pueda volver a esta URL directamente
            if 'autorizado_cambio_clave' in request.session:
                del request.session['autorizado_cambio_clave']

            messages.success(request, '¡Contraseña actualizada con éxito!')
            return redirect('configuracion')

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
            user_id = request.session.get('pre_2fa_user_id')
            user = User.objects.filter(id=user_id).first()
            if not user:
                request.session.pop('codigo_2fa', None)
                request.session.pop('pre_2fa_user_id', None)
                return redirect('login')

            login(request, user, backend='django.contrib.auth.backends.ModelBackend')

            request.session.pop('codigo_2fa', None)
            request.session.pop('pre_2fa_user_id', None)

            messages.success(request, 'Autenticación exitosa.')
            return redirect('dashboard')
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
            ajustes, _ = Settings.objects.get_or_create(
                usuario=request.user,
                defaults={'id_perfil': generar_siguiente_id(Settings, 'id_perfil', 'SET')}
            )
            ajustes.telefono = request.session.get('telefono_temp')
            ajustes.dos_factores = True
            ajustes.save()
            
            request.session.pop('codigo_sms', None)
            request.session.pop('telefono_temp', None)
            
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
    user = User.objects.filter(id=user_id).first()
    if not user:
        request.session.pop('pre_2fa_user_id', None)
        return redirect('login')
    ajustes_usuario = user.settings.first()
    numero_registrado = getattr(ajustes_usuario, 'telefono', None)

    if request.method == 'POST':
        metodo = request.POST.get('metodo')

        # Generar el código solo cuando hace clic en un botón
        import random
        codigo_2fa = str(random.randint(100000, 999999))
        request.session['codigo_2fa'] = codigo_2fa
        print(f'\n========================================\n[TIX AI] CODIGO 2FA PARA {user.email}: {codigo_2fa}\n========================================\n')

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
                from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None)
                send_mail(
                    'Tu código de acceso 2FA - TIX AI',
                    f'Hola {user.username},\n\nTu código de verificación de 2 Factores es: {codigo_2fa}',
                    from_email,
                    [user.email],
                    fail_silently=False,
                )
                messages.success(request, 'Código enviado a tu correo electrónico.')
                return redirect('verificar_2fa')
            except Exception as e:
                messages.error(request, 'Problema al enviar el correo.')

    return render(request, 'tickets/seleccionar_metodo_2fa.html', {'tiene_telefono': bool(numero_registrado)})

@login_required
def eliminar_ticket(request, ticket_id):
    ticket = get_object_or_404(Ticket, id_ticket=ticket_id)
    es_admin = (
        request.user.is_staff
        or request.user.is_superuser
        or request.user.groups.filter(name__icontains="admin").exists()
    )
    es_autor = (ticket.usuario == request.user)
    es_tecnico = request.user.groups.filter(name__in=["Tecnico", "Técnico", "tecnico"]).exists()

    if not (es_admin or es_autor or es_tecnico):
        raise PermissionDenied

    if request.method == 'POST':
        ticket_num = ticket.id_ticket
        ticket.delete()
        messages.success(request, f'El ticket #{ticket_num} se eliminó correctamente.')
        return redirect('lista_tickets')

    return redirect('detalle_ticket', ticket_id=ticket.id_ticket)

