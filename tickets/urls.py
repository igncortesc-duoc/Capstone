from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('', views.index, name='index'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('tickets/', views.lista_tickets, name='lista_tickets'),
    path('nuevo/', views.nuevo_ticket, name='nuevo_ticket'),
    path('ticket/<str:ticket_id>/', views.detalle_ticket, name='detalle_ticket'),
    path('tickets/<str:ticket_id>/', views.detalle_ticket),
    path('ticket/<str:ticket_id>/eliminar/', views.eliminar_ticket, name='eliminar_ticket'),
    path('tickets/<str:ticket_id>/eliminar/', views.eliminar_ticket),
    path('tickets/<str:ticket_id>/actualizar/', views.actualizar_ticket, name='actualizar_ticket'),
    path('ticket/<str:ticket_id>/actualizar/', views.actualizar_ticket),
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('login/verificar-2fa/', views.verificar_2fa, name='verificar_2fa'),
    path('logout/', auth_views.LogoutView.as_view(template_name='tickets/logout.html'), name='logout'),
    path('registro/', views.registro, name='register'),
    path('configuracion/', views.configuracion, name='configuracion'),
    path('usuarios/', views.lista_usuarios, name='lista_usuarios'),
    path('usuarios/<str:usuario_id>/', views.detalle_usuario, name='detalle_usuario'),
    path('usuarios/<int:usuario_id>/gestionar/', views.gestionar_usuario, name='gestionar_usuario'),
    path('reportes/', views.reportes, name='reportes'),
    path('perfil/editar/', views.editar_perfil, name='editar_perfil'),
    path('perfil/solicitar-codigo/', views.solicitar_codigo_password, name='solicitar_codigo_password'),
    path('perfil/cambiar-contrasena/', views.cambiar_password, name='cambiar_contrasena'),
    path('perfil/vincular-telefono/', views.vincular_telefono, name='vincular_telefono'),
    path('perfil/verificar-telefono/', views.verificar_telefono, name='verificar_telefono'),
    path('login/seleccionar-metodo/', views.seleccionar_metodo_2fa, name='seleccionar_metodo_2fa'),
]
