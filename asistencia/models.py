from django.db import models
from django.contrib.auth.models import User

class Estudiante(models.Model):
    dni = models.CharField(max_length=8, unique=True, primary_key=True)
    nombres = models.CharField(max_length=100)
    apellidos = models.CharField(max_length=100)
    grado = models.CharField(max_length=10)   # Ej: "3.º"
    seccion = models.CharField(max_length=5)   # Ej: "B"
    foto = models.ImageField(upload_to='estudiantes/')
    activo = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.apellidos}, {self.nombres} ({self.dni})"

class RegistroAsistencia(models.Model):
    METODO_CHOICES = [
        ('BARRAS', 'Código de barras'),
        ('DNI', 'DNI digitado'),
    ]
    ESTADO_CHOICES = [
        ('PUNTUAL', 'Puntual'),
        ('TARDANZA', 'Tardanza'),
        ('ANULADO', 'Anulado por suplantación'),
    ]

    estudiante = models.ForeignKey(Estudiante, on_delete=models.CASCADE, related_name='asistencias')
    fecha_hora = models.DateTimeField(auto_now_add=True)
    metodo = models.CharField(max_length=10, choices=METODO_CHOICES, default='BARRAS')
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES, default='PUNTUAL')
    supervisor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.estudiante.dni} - {self.fecha_hora.strftime('%Y-%m-%d %H:%M:%S')}"