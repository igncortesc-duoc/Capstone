from django.urls import path
from . import views


urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('tickets/', views.lista_tickets, name='lista_tickets'),
    path('nuevo/', views.nuevo_ticket, name='nuevo_ticket'),
    path('ticket/<int:ticket_id>/', views.detalle_ticket, name='detalle_ticket'),
    path('ticket/<int:ticket_id>/corregir/', views.corregir_ticket, name='corregir_ticket'),
    path('ticket/<int:ticket_id>/estado/', views.cambiar_estado, name='cambiar_estado'),
]