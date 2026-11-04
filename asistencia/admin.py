from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from types import MethodType
from .models import CorreccionAsistencia, Estudiante, RegistroAsistencia


def _solo_superusuario(self, request):
    return request.user.is_active and request.user.is_superuser


admin.site.has_permission = MethodType(_solo_superusuario, admin.site)

@admin.register(Estudiante)
class EstudianteAdmin(admin.ModelAdmin):
    list_display = ('dni', 'apellidos', 'nombres', 'grado', 'seccion', 'activo', 'codigo_barras')
    search_fields = ('dni', 'apellidos', 'nombres')

    @admin.display(description='Código de barras')
    def codigo_barras(self, obj):
        url = reverse('codigo_barras_estudiante', args=[obj.dni])
        return format_html('<a href="{}" target="_blank">Generar / abrir</a>', url)

@admin.register(RegistroAsistencia)
class RegistroAsistenciaAdmin(admin.ModelAdmin):
    list_display = ('estudiante', 'fecha_hora', 'metodo', 'estado', 'supervisor')
    list_filter = ('estado', 'metodo', 'fecha_hora')


@admin.register(CorreccionAsistencia)
class CorreccionAsistenciaAdmin(admin.ModelAdmin):
    list_display = ('registro', 'estado_anterior', 'estado_nuevo', 'usuario', 'fecha_hora', 'ip')
    readonly_fields = (
        'registro', 'estado_anterior', 'estado_nuevo', 'motivo',
        'usuario', 'fecha_hora', 'ip',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False