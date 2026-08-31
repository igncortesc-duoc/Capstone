from django.db import models
from django.conf import settings


class Categoria(models.Model):
    id_categoria = models.CharField(max_length=10, primary_key=True)
    nombre = models.CharField(max_length=50)
    descripcion = models.CharField(max_length=500, blank=True, null=True)

    class Meta:
        db_table = "categoria"

    def __str__(self):
        return self.nombre


class Prioridad(models.Model):
    id_prioridad = models.CharField(max_length=10, primary_key=True)
    nombre = models.CharField(max_length=100)
    nivel = models.DecimalField(max_digits=2, decimal_places=0)
    descripcion = models.CharField(max_length=500, blank=True, null=True)

    class Meta:
        db_table = "prioridad"

    def __str__(self):
        return self.nombre


class Estado(models.Model):
    id_estado = models.CharField(max_length=10, primary_key=True)
    nombre = models.CharField(max_length=100)
    descripcion = models.CharField(max_length=500, blank=True, null=True)

    class Meta:
        db_table = "estado"

    def __str__(self):
        return self.nombre


class Settings(models.Model):
    id_perfil = models.CharField(max_length=10, primary_key=True)
    tema = models.CharField(max_length=20)
    idioma = models.CharField(max_length=40)
    interfaz = models.CharField(max_length=100)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="settings"
    )

    class Meta:
        db_table = "settings"

    def __str__(self):
        return f"Settings de {self.usuario}"


class Ticket(models.Model):
    id_ticket = models.CharField(max_length=10, primary_key=True)
    titulo = models.CharField(max_length=150)
    descripcion = models.CharField(max_length=1000, blank=True, null=True)
    fecha_creacion = models.DateTimeField(blank=True, null=True)
    fecha_asignacion = models.DateTimeField(blank=True, null=True)
    fecha_cierre = models.DateTimeField(blank=True, null=True)
    solucion = models.CharField(max_length=2000, blank=True, null=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="tickets"
    )
    id_tecnico = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name="tickets_asignados", blank=True, null=True,
        limit_choices_to={'groups__name': 'Tecnico'}
    )
    id_categoria = models.ForeignKey(
        Categoria, on_delete=models.SET_NULL, db_column="id_categoria",
        related_name="tickets", blank=True, null=True
    )
    id_prioridad = models.ForeignKey(
        Prioridad, on_delete=models.SET_NULL, db_column="id_prioridad",
        related_name="tickets", blank=True, null=True
    )
    id_estado = models.ForeignKey(
        Estado, on_delete=models.SET_NULL, db_column="id_estado",
        related_name="tickets", blank=True, null=True
    )

    class Meta:
        db_table = "ticket"

    def __str__(self):
        return self.titulo


class ClasificacionIA(models.Model):
    id_clasificacion_ia = models.CharField(max_length=10, primary_key=True)
    resultado = models.CharField(max_length=100)
    nivel_confianza = models.DecimalField(max_digits=5, decimal_places=2)
    fecha_clasificacion = models.DateTimeField(blank=True, null=True)
    modelo_utilizado = models.CharField(max_length=100)
    id_ticket = models.ForeignKey(
        Ticket, on_delete=models.CASCADE, db_column="id_ticket",
        related_name="clasificaciones_ia"
    )
    id_categoria = models.ForeignKey(
        Categoria, on_delete=models.PROTECT, db_column="id_categoria",
        related_name="clasificaciones_ia"
    )
    id_prioridad = models.ForeignKey(
        Prioridad, on_delete=models.PROTECT, db_column="id_prioridad",
        related_name="clasificaciones_ia"
    )

    class Meta:
        db_table = "clasificacion_ia"

    def __str__(self):
        return f"{self.resultado} ({self.nivel_confianza}%)"

class EspecialidadTecnico(models.Model):
    tecnico = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='especialidades', limit_choices_to={'groups__name': 'Tecnico'}
    )
    categoria = models.ForeignKey(
        Categoria, on_delete=models.CASCADE, related_name='tecnicos_especializados'
    )

    class Meta:
        db_table = "especialidad_tecnico"
        unique_together = ('tecnico', 'categoria')

    def __str__(self):
        return f"{self.tecnico} → {self.categoria}"