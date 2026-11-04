from functools import wraps

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.utils import timezone


def es_director(user):
    return user.is_authenticated and user.is_superuser


def es_auxiliar(user):
    return (
        user.is_authenticated
        and not user.is_superuser
        and user.groups.filter(name='Auxiliar').exists()
    )


def tiene_rol(user):
    return es_director(user) or es_auxiliar(user)


def _rol_requerido(view, allowed):
    @wraps(view)
    @login_required
    def wrapped(request, *args, **kwargs):
        if not allowed(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return wrapped


def director_requerido(view):
    return _rol_requerido(view, es_director)


def personal_requerido(view):
    return _rol_requerido(view, tiene_rol)


def api_personal_requerido(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({
                'encontrado': False,
                'mensaje': 'Tu sesión venció. Inicia sesión de nuevo.',
            }, status=401)
        if not tiene_rol(request.user):
            return JsonResponse({
                'encontrado': False,
                'mensaje': 'No tienes permiso para registrar asistencia.',
            }, status=403)
        return view(request, *args, **kwargs)
    return wrapped


def ip_correccion_permitida(request):
    ips = getattr(settings, 'CORRECCIONES_IPS_PERMITIDAS', [])
    return not ips or request.META.get('REMOTE_ADDR') in ips


def auxiliar_puede_corregir(request, fecha):
    return (
        es_director(request.user)
        or (
            es_auxiliar(request.user)
            and ip_correccion_permitida(request)
            and fecha == timezone.localdate()
        )
    )
