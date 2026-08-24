from django.db import models


class Ticket(models.Model):

    CATEGORIAS = [
        ('Accesos', 'Accesos'),
        ('Hardware', 'Hardware'),
        ('Software', 'Software'),
        ('Red', 'Red'),
        ('Seguridad', 'Seguridad'),
        ('Consulta general', 'Consulta general'),
    ]

    ESTADOS = [
        ('Abierto', 'Abierto'),
        ('En proceso', 'En proceso'),
        ('Cerrado', 'Cerrado'),
    ]

    asunto = models.CharField(max_length=200)
    descripcion = models.TextField()

    categoria_predicha = models.CharField(
        max_length=50,
        blank=True,
        null=True
    )

    confianza = models.FloatField(
        blank=True,
        null=True
    )

    categoria_corregida = models.CharField(
        max_length=50,
        choices=CATEGORIAS,
        blank=True,
        null=True
    )

    estado = models.CharField(
        max_length=20,
        choices=ESTADOS,
        default='Abierto'
    )

    fecha_creacion = models.DateTimeField(auto_now_add=True)

    fecha_actualizacion = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.asunto

