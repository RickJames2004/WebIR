from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include
from asistencia import views as asistencia_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('media/<path:ruta>', asistencia_views.media_protegida, name='media_protegida'),
    path('', include('asistencia.urls')),
]