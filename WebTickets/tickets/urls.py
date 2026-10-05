from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('', views.index, name='index'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('tickets/', views.lista_tickets, name='lista_tickets'),
    path('nuevo/', views.nuevo_ticket, name='nuevo_ticket'),
    path('ticket/<str:ticket_id>/', views.detalle_ticket, name='detalle_ticket'),
    path('ticket/<str:ticket_id>/corregir/', views.corregir_ticket, name='corregir_ticket'),
    path('ticket/<str:ticket_id>/estado/', views.cambiar_estado, name='cambiar_estado'),
    path('login/', auth_views.LoginView.as_view(template_name='tickets/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(template_name='tickets/logout.html'), name='logout'),
    path('registro/', views.registro, name='register'),
    path('configuracion/', views.configuracion, name='configuracion'),
    path('usuarios/', views.lista_usuarios, name='lista_usuarios'),
    path('usuarios/<str:usuario_id>/', views.detalle_usuario, name='detalle_usuario'),
    path('usuarios/<int:usuario_id>/gestionar/', views.gestionar_usuario, name='gestionar_usuario'),
    path('reportes/', views.reportes, name='reportes'),
    path('ticket/<str:ticket_id>/asignar/', views.asignar_tecnico, name='asignar_tecnico'),
    path('ticket/<str:ticket_id>/clasificacion/', views.actualizar_clasificacion, name='actualizar_clasificacion'),
]