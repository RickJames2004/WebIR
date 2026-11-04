from django.urls import path
from . import views

urlpatterns = [
    path('', views.pantalla_registro, name='pantalla_registro'),
    path('api/buscar_estudiante/', views.buscar_estudiante, name='buscar_estudiante'),
    path('api/confirmar_ingreso/', views.confirmar_ingreso, name='confirmar_ingreso'),
]