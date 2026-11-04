from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.pantalla_registro, name='pantalla_registro'),
    path('api/buscar_estudiante/', views.buscar_estudiante, name='buscar_estudiante'),
    path('api/confirmar_ingreso/', views.confirmar_ingreso, name='confirmar_ingreso'),
    path('estudiantes/<str:dni>/codigo-barras/', views.codigo_barras_estudiante, name='codigo_barras_estudiante'),
    path('login/', views.iniciar_sesion, name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    # Panel de métricas y reportes
    path('dashboard/', views.dashboard, name='dashboard'),
    path('exportar_reporte/', views.exportar_reporte_csv, name='exportar_reporte_csv'),
    path('asistencias/', views.asistencias_fecha, name='asistencias_fecha'),
    path('asistencias/<int:pk>/corregir/', views.corregir_asistencia, name='corregir_asistencia'),
    path('asistencias/<int:pk>/anular/', views.anular_asistencia, name='anular_asistencia'),
    path('asistencias/<int:pk>/restaurar/', views.restaurar_asistencia, name='restaurar_asistencia'),
    path('asistencias/<str:dni>/manual/', views.registrar_asistencia_manual, name='registrar_asistencia_manual'),
    path('asistencias/faltas-masivas/', views.marcar_faltas_masivas, name='marcar_faltas_masivas'),
    path('gestion/', views.gestion_estudiantes, name='gestion_estudiantes'),
    path('gestion/importar/', views.importar_estudiantes, name='importar_estudiantes'),
    path('gestion/plantilla-csv/', views.plantilla_csv, name='plantilla_csv'),
    path('gestion/<str:dni>/foto/', views.foto_estudiante, name='foto_estudiante'),
    path('gestion/fotos/', views.fotos_lote, name='fotos_lote'),
    path('gestion/usuarios/', views.gestion_usuarios, name='gestion_usuarios'),
]