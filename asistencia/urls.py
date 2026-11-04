from django.urls import path
from . import views

urlpatterns = [
    path('', views.pantalla_registro, name='pantalla_registro'),
    path('api/buscar_estudiante/', views.buscar_estudiante, name='buscar_estudiante'),
    path('api/confirmar_ingreso/', views.confirmar_ingreso, name='confirmar_ingreso'),
    # Panel de métricas y reportes
    path('dashboard/', views.dashboard, name='dashboard'),
    path('exportar_reporte/', views.exportar_reporte_csv, name='exportar_reporte_csv'),
]