from django.contrib import admin
from .models import Estudiante, RegistroAsistencia

@admin.register(Estudiante)
class EstudianteAdmin(admin.ModelAdmin):
    list_display = ('dni', 'apellidos', 'nombres', 'grado', 'seccion', 'activo')
    search_fields = ('dni', 'apellidos', 'nombres')

@admin.register(RegistroAsistencia)
class RegistroAsistenciaAdmin(admin.ModelAdmin):
    list_display = ('estudiante', 'fecha_hora', 'metodo', 'estado', 'supervisor')
    list_filter = ('estado', 'metodo', 'fecha_hora')