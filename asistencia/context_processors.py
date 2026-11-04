from .permisos import es_auxiliar, es_director


def roles(request):
    return {
        'es_director': es_director(request.user),
        'es_auxiliar': es_auxiliar(request.user),
    }
