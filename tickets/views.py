from django.shortcuts import render, redirect, get_object_or_404
from .models import Ticket
from .ml_service import predecir_categoria


def lista_tickets(request):
    tickets = Ticket.objects.all().order_by('-fecha_creacion')

    return render(
        request,
        'tickets/lista_tickets.html',
        {'tickets': tickets}
    )


def nuevo_ticket(request):

    if request.method == 'POST':

        asunto = request.POST.get('asunto')
        descripcion = request.POST.get('descripcion')

        # Realizar predicción con Machine Learning
        categoria, confianza = predecir_categoria(
            asunto,
            descripcion
        )

        # Guardar ticket con la predicción
        ticket = Ticket.objects.create(
            asunto=asunto,
            descripcion=descripcion,
            categoria_predicha=categoria,
            confianza=confianza
        )

        return redirect(
            'detalle_ticket',
            ticket_id=ticket.id
        )

    return render(
        request,
        'tickets/nuevo_ticket.html'
    )





def dashboard(request):

    total_tickets = Ticket.objects.count()

    tickets_abiertos = Ticket.objects.filter(
        estado='Abierto'
    ).count()

    tickets_proceso = Ticket.objects.filter(
        estado='En proceso'
    ).count()

    tickets_cerrados = Ticket.objects.filter(
        estado='Cerrado'
    ).count()


    # Contar tickets por categoría final
    categorias_dict = {}

    tickets = Ticket.objects.all()

    for ticket in tickets:

        categoria = (
            ticket.categoria_corregida
            if ticket.categoria_corregida
            else ticket.categoria_predicha
        )

        if categoria:

            if categoria in categorias_dict:
                categorias_dict[categoria] += 1
            else:
                categorias_dict[categoria] = 1


    # Datos para gráfico de categorías
    categorias_labels = list(categorias_dict.keys())
    categorias_data = list(categorias_dict.values())


    # Datos para gráfico de estados
    estados_labels = [
        'Abierto',
        'En proceso',
        'Cerrado'
    ]

    estados_data = [
        tickets_abiertos,
        tickets_proceso,
        tickets_cerrados
    ]


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

    return render(
        request,
        'tickets/dashboard.html',
        contexto
    )



def detalle_ticket(request, ticket_id):

    ticket = get_object_or_404(
        Ticket,
        id=ticket_id
    )

    return render(
        request,
        'tickets/detalle_ticket.html',
        {'ticket': ticket}
    )


def corregir_ticket(request, ticket_id):

    ticket = get_object_or_404(
        Ticket,
        id=ticket_id
    )

    if request.method == 'POST':

        categoria_corregida = request.POST.get(
            'categoria_corregida'
        )

        ticket.categoria_corregida = categoria_corregida
        ticket.save()

        return redirect(
            'detalle_ticket',
            ticket_id=ticket.id
        )

    return render(
        request,
        'tickets/corregir_ticket.html',
        {'ticket': ticket}
    )

def cambiar_estado(request, ticket_id):

    ticket = get_object_or_404(
        Ticket,
        id=ticket_id
    )

    if request.method == 'POST':

        nuevo_estado = request.POST.get('estado')

        estados_validos = [
            'Abierto',
            'En proceso',
            'Cerrado'
        ]

        if nuevo_estado in estados_validos:

            ticket.estado = nuevo_estado

            ticket.save()

        return redirect(
            'detalle_ticket',
            ticket_id=ticket.id
        )

    return redirect(
        'detalle_ticket',
        ticket_id=ticket.id
    )

def lista_tickets(request):

    busqueda = request.GET.get(
        'q',
        ''
    ).strip()

    estado = request.GET.get('estado', '').strip()

    tickets = Ticket.objects.all()

    if busqueda:

        tickets = Ticket.objects.filter(asunto__icontains=busqueda) | Ticket.objects.filter(
            descripcion__icontains=busqueda)

    
    if estado:
        tickets = tickets.filter(estado=estado)

    tickets = tickets.order_by(
        '-fecha_creacion'
    )

    return render(
        request,
        'tickets/lista_tickets.html',
        {
            'tickets': tickets,
            'busqueda': busqueda,
            'estado': estado
        }
    )