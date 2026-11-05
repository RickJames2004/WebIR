import csv
import json
import re
from datetime import datetime, time, timedelta
from mimetypes import guess_type
from io import StringIO
from pathlib import Path
from PIL import Image, UnidentifiedImageError
from django.conf import settings
from django.contrib.auth import authenticate, login
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import Group, User
from django.contrib.auth.password_validation import validate_password
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.http import FileResponse, JsonResponse, Http404, HttpResponse
from django.contrib import messages
from django.utils._os import safe_join
from django.utils.http import url_has_allowed_host_and_scheme
from django.templatetags.static import static
from django.utils import timezone
from django.db.models import Count, Max, Prefetch, Q, Subquery
from django.db.models.functions import TruncDate
from barcode import Code128
from barcode.writer import SVGWriter
from .models import CorreccionAsistencia, Estudiante, RegistroAsistencia
from .permisos import (
    api_personal_requerido, auxiliar_puede_corregir, director_requerido,
    es_auxiliar, es_director, personal_requerido, tiene_rol,
)

HORA_FALTA = time(8, 0)
HORA_TARDANZA = time(8,30)
HORA_PUNTUAL_LIMITE = time(8,0)
HORA_FIN_CLASES = time(15, 30)

# --- Módulo de Registro en Puerta ---

from django.views.decorators.csrf import ensure_csrf_cookie


@ensure_csrf_cookie
@personal_requerido
def pantalla_registro(request):
    return render(request, 'asistencia/registro.html')


def iniciar_sesion(request):
    if request.user.is_authenticated:
        return redirect('/dashboard/' if es_director(request.user) else '/')
    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        usuario = form.get_user()
        if not tiene_rol(usuario):
            form.add_error(None, 'Tu usuario no tiene un rol habilitado.')
        else:
            login(request, usuario)
            siguiente = request.POST.get('next') or request.GET.get('next', '')
            if not url_has_allowed_host_and_scheme(
                siguiente, allowed_hosts={request.get_host()}, require_https=request.is_secure()
            ):
                siguiente = '/dashboard/' if es_director(usuario) else '/'
            return redirect(siguiente)
    return render(request, 'asistencia/login.html', {'form': form})

@api_personal_requerido
def buscar_estudiante(request):
    dni_recibido = request.GET.get('dni', '').strip()
    if not re.fullmatch(r'\d{8}', dni_recibido):
        return JsonResponse({
            'encontrado': False,
            'mensaje': 'El DNI debe contener exactamente 8 dígitos.'
        }, status=400)

    try:
        estudiante = Estudiante.objects.get(dni=dni_recibido, activo=True)
        hoy = timezone.localdate()
        ya_ingreso = RegistroAsistencia.objects.filter(
            estudiante=estudiante, 
            fecha_hora__date=hoy, 
        ).exists()
        
        datos = {
            'encontrado': True,
            'dni': estudiante.dni,
            'nombre_completo': f"{estudiante.nombres} {estudiante.apellidos}",
            'grado_seccion': f"{estudiante.grado} '{estudiante.seccion}'",
            'foto_url': estudiante.foto.url if estudiante.foto else static('foto-default.svg'),
            'ya_ingreso': ya_ingreso
        }
    except Estudiante.DoesNotExist:
        datos = {'encontrado': False, 'mensaje': 'Estudiante no encontrado en la base de datos.'}
        
    return JsonResponse(datos)

@api_personal_requerido
def confirmar_ingreso(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'mensaje': 'Método no permitido.'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'mensaje': 'La solicitud no es válida.'}, status=400)

    dni = str(data.get('dni', '')).strip()
    accion = data.get('accion')
    metodo = data.get('metodo')
    if not re.fullmatch(r'\d{8}', dni):
        return JsonResponse({'success': False, 'mensaje': 'El DNI debe contener exactamente 8 dígitos.'}, status=400)
    if accion not in {'confirmar', 'falta'}:
        return JsonResponse({'success': False, 'mensaje': 'La acción no es válida.'}, status=400)
    if metodo != 'DNI':
        return JsonResponse({'success': False, 'mensaje': 'El método de registro no es válido.'}, status=400)

    try:
        estudiante = Estudiante.objects.get(dni=dni, activo=True)
    except Estudiante.DoesNotExist:
        return JsonResponse({'success': False, 'mensaje': 'Estudiante no encontrado o inactivo.'}, status=404)

    if accion == 'falta':
        estado = 'FALTA'
    else:
        hora_actual = timezone.localtime().time()
        if hora_actual >= HORA_FIN_CLASES:
            estado = 'FALTA'
        elif hora_actual <= HORA_PUNTUAL_LIMITE:
            estado = 'PUNTUAL'
        else:
            estado = 'TARDANZA'

    try:
        with transaction.atomic():
            estudiante = Estudiante.objects.select_for_update().get(
                dni=dni,
                activo=True,
            )
            hoy = timezone.localdate()
            if RegistroAsistencia.objects.filter(
                estudiante=estudiante,
                fecha_hora__date=hoy,
            ).exists():
                return JsonResponse({
                    'success': False,
                    'mensaje': 'Este estudiante ya tiene un registro para hoy.'
                }, status=409)
            RegistroAsistencia.objects.create(
                estudiante=estudiante,
                metodo=metodo,
                estado=estado,
                supervisor=request.user
            )
    except IntegrityError:
        return JsonResponse({
            'success': False,
            'mensaje': 'No se pudo guardar el registro. Inténtelo nuevamente.'
        }, status=409)

    return JsonResponse({'success': True, 'estado': estado})


@director_requerido
def codigo_barras_estudiante(request, dni):
    """Genera un código Code 128 para reponer la credencial del estudiante."""
    dni = dni.strip()
    if not re.fullmatch(r'\d{8}', dni):
        return JsonResponse({'mensaje': 'El DNI debe contener exactamente 8 dígitos.'}, status=400)
    if not Estudiante.objects.filter(dni=dni).exists():
        return JsonResponse({'mensaje': 'Estudiante no encontrado.'}, status=404)

    codigo = Code128(dni, writer=SVGWriter())
    svg = codigo.render(writer_options={
        'module_width': 0.3,
        'module_height': 15,
        'font_size': 10,
        'text_distance': 3,
        'quiet_zone': 2,
    })
    response = HttpResponse(svg, content_type='image/svg+xml')
    response['Content-Disposition'] = f'inline; filename="codigo-barras-{dni}.svg"'
    return response


# --- Panel de Métricas y Reportes ---

@director_requerido
def dashboard(request):
    try:
        rango = int(request.GET.get('rango', 14))
    except ValueError:
        rango = 14
    rango = rango if rango in (7, 14, 30) else 14
    grado = request.GET.get('grado', '').strip()
    seccion = request.GET.get('seccion', '').strip()
    hoy = timezone.localdate()
    inicio = hoy - timedelta(days=rango - 1)
    registros = RegistroAsistencia.objects.filter(
        fecha_hora__gte=timezone.make_aware(datetime.combine(inicio, time.min)),
        fecha_hora__lt=timezone.make_aware(datetime.combine(hoy + timedelta(days=1), time.min)),
    ).exclude(estado='ANULADO')
    if grado:
        registros = registros.filter(estudiante__grado=grado)
    if seccion:
        registros = registros.filter(estudiante__seccion=seccion)
    estados = {row['estado']: row['total'] for row in registros.values('estado').annotate(total=Count('id'))}
    total = sum(estados.values())
    validos = estados.get('PUNTUAL', 0) + estados.get('TARDANZA', 0) + estados.get('FALTA', 0)
    asistencia_promedio = round(
        (estados.get('PUNTUAL', 0) + estados.get('TARDANZA', 0)) * 100 / validos, 1
    ) if validos else 0
    diarios = list(registros.annotate(dia=TruncDate('fecha_hora')).values('dia').annotate(
        puntual=Count('id', filter=Q(estado='PUNTUAL')),
        tardanza=Count('id', filter=Q(estado='TARDANZA')),
        falta=Count('id', filter=Q(estado='FALTA')),
    ).order_by('dia'))
    por_seccion = list(registros.filter(estado='FALTA').values(
        'estudiante__grado', 'estudiante__seccion'
    ).annotate(total=Count('id')).order_by('estudiante__grado', 'estudiante__seccion'))
    por_dia_semana = list(registros.filter(estado='TARDANZA').annotate(
        dia=TruncDate('fecha_hora')
    ).values('dia').annotate(total=Count('id')).order_by('dia'))
    alertas = list(registros.filter(estado__in=['FALTA', 'TARDANZA']).values(
        'estudiante_id', 'estudiante__dni', 'estudiante__nombres',
        'estudiante__apellidos', 'estudiante__grado', 'estudiante__seccion',
    ).annotate(
        total=Count('id'),
        ultimo_dia=Max('fecha_hora', filter=Q(estado='FALTA')),
    ).order_by('-total')[:10])
    for alerta in alertas:
        alerta['ultimo_dia'] = (
            timezone.localtime(alerta['ultimo_dia']).date().isoformat()
            if alerta['ultimo_dia'] else hoy.isoformat()
        )
    contexto = {
        'total_estudiantes': Estudiante.objects.filter(activo=True).count(),
        'grados_disponibles': Estudiante.objects.filter(activo=True).values_list('grado', flat=True).distinct().order_by('grado'),
        'secciones_disponibles': Estudiante.objects.filter(activo=True).values_list('seccion', flat=True).distinct().order_by('seccion'),
        'rango': rango, 'grado': grado, 'seccion': seccion,
        'asistencia_promedio': asistencia_promedio,
        'total_faltas': estados.get('FALTA', 0),
        'total_tardanzas': estados.get('TARDANZA', 0),
        'alertas': alertas,
        'grafica_diaria': json.dumps([
            {'dia': row['dia'].isoformat(), 'porcentaje': round(
                (row['puntual'] + row['tardanza']) * 100 / (row['puntual'] + row['tardanza'] + row['falta']), 1
            ) if row['puntual'] + row['tardanza'] + row['falta'] else 0}
            for row in diarios
        ]),
        'grafica_secciones': json.dumps(por_seccion),
        'grafica_estados': json.dumps({
            'Puntual': estados.get('PUNTUAL', 0),
            'Tardanza': estados.get('TARDANZA', 0),
            'Falta': estados.get('FALTA', 0),
        }),
        'grafica_semana': json.dumps([
            {'dia': row['dia'].strftime('%A'), 'total': row['total']} for row in por_dia_semana
        ]),
    }
    return render(request, 'asistencia/dashboard.html', contexto)

def _fecha_solicitada(valor):
    if not valor:
        return timezone.localdate()
    try:
        return datetime.strptime(valor, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return timezone.localdate()


def _rango_dia(fecha):
    inicio = timezone.make_aware(datetime.combine(fecha, time.min))
    return inicio, inicio + timedelta(days=1)


@director_requerido
def exportar_reporte_csv(request):
    response = HttpResponse(content_type='text/csv')
    fecha = request.GET.get('fecha')
    if fecha:
        fecha = _fecha_solicitada(fecha)
        inicio, fin = _rango_dia(fecha)
        registros = RegistroAsistencia.objects.filter(
            fecha_hora__gte=inicio,
            fecha_hora__lt=fin,
        )
        nombre = f'reporte_asistencia_{fecha.isoformat()}.csv'
    else:
        registros = RegistroAsistencia.objects.all()
        nombre = 'reporte_asistencia.csv'
    response['Content-Disposition'] = f'attachment; filename="{nombre}"'
    
    writer = csv.writer(response)
    writer.writerow(['DNI', 'Apellidos', 'Nombres', 'Grado', 'Seccion', 'Fecha y Hora', 'Estado', 'Metodo'])
    
    registros = registros.select_related('estudiante').order_by('-fecha_hora')
    for reg in registros:
        writer.writerow([
            reg.estudiante.dni,
            reg.estudiante.apellidos,
            reg.estudiante.nombres,
            reg.estudiante.grado,
            reg.estudiante.seccion,
            reg.fecha_hora.strftime('%Y-%m-%d %H:%M:%S'),
            reg.estado,
            reg.metodo
        ])
        
    return response


staff_required = director_requerido


@staff_required
def gestion_estudiantes(request):
    query = request.GET.get('q', '').strip()
    estudiantes = Estudiante.objects.all().order_by('apellidos', 'nombres')
    if query:
        estudiantes = estudiantes.filter(
            Q(dni__icontains=query) | Q(apellidos__icontains=query)
        )

    paginator = Paginator(estudiantes, 25)
    pagina = paginator.get_page(request.GET.get('page'))
    return render(request, 'asistencia/gestion.html', {
        'pagina': pagina,
        'busqueda': query,
        'total_estudiantes': paginator.count,
    })


@staff_required
def importar_estudiantes(request):
    resumen = None
    if request.method == 'POST':
        archivo = request.FILES.get('archivo_csv')
        resumen = {
            'creados': 0,
            'actualizados': 0,
            'errores': [],
        }

        if not archivo:
            resumen['errores'].append({'linea': '-', 'motivo': 'No se seleccionó ningún archivo.'})
        elif not archivo.name.lower().endswith('.csv'):
            resumen['errores'].append({'linea': '-', 'motivo': 'El archivo debe tener extensión .csv.'})
        else:
            try:
                contenido = archivo.read().decode('utf-8-sig')
                muestra = contenido[:4096]
                try:
                    dialecto = csv.Sniffer().sniff(muestra, delimiters=',;')
                    delimitador = dialecto.delimiter
                except csv.Error:
                    delimitador = ',' if ',' in muestra.splitlines()[0] else ';'

                lector = csv.DictReader(StringIO(contenido), delimiter=delimitador)
                encabezados = {
                    (encabezado or '').strip().lower()
                    for encabezado in (lector.fieldnames or [])
                }
                requeridos = {'dni', 'apellidos', 'nombres', 'grado', 'seccion'}
                faltantes = sorted(requeridos - encabezados)
                if faltantes:
                    resumen['errores'].append({
                        'linea': 1,
                        'motivo': f"Faltan columnas: {', '.join(faltantes)}.",
                    })
                else:
                    filas_validas = []
                    for numero, fila in enumerate(lector, start=2):
                        fila_normalizada = {
                            (clave or '').strip().lower(): (valor or '').strip()
                            for clave, valor in fila.items()
                        }
                        errores = []
                        dni = fila_normalizada.get('dni', '')
                        if not re.fullmatch(r'\d{8}', dni):
                            errores.append('el DNI debe tener exactamente 8 dígitos numéricos')
                        for campo in ('apellidos', 'nombres', 'grado', 'seccion'):
                            if not fila_normalizada.get(campo):
                                errores.append(f'el campo {campo} está vacío')

                        if errores:
                            resumen['errores'].append({
                                'linea': numero,
                                'motivo': '; '.join(errores),
                            })
                            continue
                        filas_validas.append((dni, fila_normalizada))

                    with transaction.atomic():
                        for dni, fila in filas_validas:
                            _, creado = Estudiante.objects.update_or_create(
                                dni=dni,
                                defaults={
                                    'apellidos': fila['apellidos'],
                                    'nombres': fila['nombres'],
                                    'grado': fila['grado'],
                                    'seccion': fila['seccion'],
                                },
                            )
                            resumen['creados' if creado else 'actualizados'] += 1
            except UnicodeDecodeError:
                resumen['errores'].append({
                    'linea': '-',
                    'motivo': 'El archivo debe estar codificado en UTF-8.',
                })
            except (csv.Error, IndexError) as error:
                resumen['errores'].append({
                    'linea': '-',
                    'motivo': f'No se pudo leer el CSV: {error}',
                })

    return render(request, 'asistencia/importar.html', {'resumen': resumen})


@staff_required
def plantilla_csv(request):
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="plantilla_estudiantes.csv"'
    response.write('\ufeff')
    writer = csv.writer(response)
    writer.writerow(['dni', 'apellidos', 'nombres', 'grado', 'seccion'])
    writer.writerow(['74852316', 'Pérez', 'Ana', '3', 'B'])
    writer.writerow(['70456123', 'García', 'Luis', '4', 'A'])
    writer.writerow(['76543210', 'Quispe', 'María', '5', 'C'])
    return response


@personal_requerido
def asistencias_fecha(request):
    fecha = _fecha_solicitada(request.GET.get('fecha'))
    grado = request.GET.get('grado', '').strip()
    seccion = request.GET.get('seccion', '').strip()
    estado = request.GET.get('estado', '').strip()
    inicio, fin = _rango_dia(fecha)

    registros = RegistroAsistencia.objects.select_related(
        'estudiante', 'supervisor'
    ).prefetch_related(Prefetch(
        'correcciones',
        queryset=CorreccionAsistencia.objects.select_related('usuario').order_by('-fecha_hora'),
        to_attr='lista_correcciones',
    )).filter(fecha_hora__gte=inicio, fecha_hora__lt=fin)
    estudiantes = Estudiante.objects.filter(activo=True)
    if grado:
        registros = registros.filter(estudiante__grado=grado)
        estudiantes = estudiantes.filter(grado=grado)
    if seccion:
        registros = registros.filter(estudiante__seccion=seccion)
        estudiantes = estudiantes.filter(seccion=seccion)
    if estado in {'PUNTUAL', 'TARDANZA', 'FALTA', 'ANULADO'}:
        registros = registros.filter(estado=estado)

    registros_sin_filtro = RegistroAsistencia.objects.filter(
        fecha_hora__gte=inicio,
        fecha_hora__lt=fin,
        estudiante__in=estudiantes,
    )
    conteos = registros_sin_filtro.values('estado').annotate(total=Count('id'))
    conteos = {item['estado']: item['total'] for item in conteos}
    sin_registro = estudiantes.exclude(
        pk__in=registros_sin_filtro.values('estudiante_id')
    ).order_by('apellidos', 'nombres')

    paginator = Paginator(registros.order_by('fecha_hora'), 50)
    pagina = paginator.get_page(request.GET.get('page'))
    grados = Estudiante.objects.filter(activo=True).values_list(
        'grado', flat=True
    ).distinct().order_by('grado')
    secciones = Estudiante.objects.filter(activo=True).values_list(
        'seccion', flat=True
    ).distinct().order_by('seccion')
    fecha_legible = fecha.strftime('%A {dia} de %B de %Y').format(dia=fecha.day)
    meses = {
        'January': 'enero', 'February': 'febrero', 'March': 'marzo',
        'April': 'abril', 'May': 'mayo', 'June': 'junio',
        'July': 'julio', 'August': 'agosto', 'September': 'septiembre',
        'October': 'octubre', 'November': 'noviembre', 'December': 'diciembre',
    }
    dias = {
        'Monday': 'lunes', 'Tuesday': 'martes', 'Wednesday': 'miércoles',
        'Thursday': 'jueves', 'Friday': 'viernes', 'Saturday': 'sábado',
        'Sunday': 'domingo',
    }
    fecha_legible = fecha_legible.replace(
        fecha.strftime('%B'), meses.get(fecha.strftime('%B'), fecha.strftime('%B'))
    )
    fecha_legible = fecha_legible.replace(
        fecha.strftime('%A'), dias.get(fecha.strftime('%A'), fecha.strftime('%A'))
    )
    filtros = f'fecha={fecha.isoformat()}&grado={grado}&seccion={seccion}&estado={estado}'
    return render(request, 'asistencia/asistencias.html', {
        'pagina': pagina,
        'fecha': fecha,
        'fecha_legible': fecha_legible,
        'hoy': timezone.localdate(),
        'grado': grado,
        'seccion': seccion,
        'estado': estado,
        'grados': grados,
        'secciones': secciones,
        'conteos': conteos,
        'sin_registro': sin_registro,
        'mostrar_sin_registro': not estado and fecha <= timezone.localdate(),
        'fecha_anterior': fecha - timedelta(days=1),
        'fecha_siguiente': fecha + timedelta(days=1),
        'filtros': filtros,
        'puede_corregir': auxiliar_puede_corregir(request, fecha),
        'es_director': es_director(request.user),
    })


def _redireccion_asistencias(request):
    destino = request.POST.get('next') or request.META.get('HTTP_REFERER', '')
    if not url_has_allowed_host_and_scheme(
        destino, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        destino = '/asistencias/'
    return redirect(destino)


def _motivo(request):
    motivo = request.POST.get('motivo', '').strip()
    if len(motivo) < 5 or len(motivo) > 200:
        return None
    return motivo


def registro_valido_del_dia(estudiante, fecha):
    inicio, fin = _rango_dia(fecha)
    return RegistroAsistencia.objects.filter(
        estudiante=estudiante,
        fecha_hora__gte=inicio,
        fecha_hora__lt=fin,
        estado__in=['PUNTUAL', 'TARDANZA', 'FALTA'],
    )


def _auditar(registro, anterior, nuevo, motivo, request):
    CorreccionAsistencia.objects.create(
        registro=registro,
        estado_anterior=anterior,
        estado_nuevo=nuevo,
        motivo=motivo,
        usuario=request.user,
        ip=request.META.get('REMOTE_ADDR'),
    )


@personal_requerido
def corregir_asistencia(request, pk):
    if request.method != 'POST':
        return HttpResponse(status=405)
    fecha = _fecha_solicitada(request.POST.get('fecha'))
    if not auxiliar_puede_corregir(request, fecha):
        raise PermissionDenied
    motivo = _motivo(request)
    if not motivo:
        messages.error(request, 'El motivo es obligatorio y debe tener entre 5 y 200 caracteres.')
        return _redireccion_asistencias(request)
    nuevo = request.POST.get('estado')
    if nuevo not in {'PUNTUAL', 'TARDANZA', 'FALTA', 'ANULADO'}:
        raise PermissionDenied
    if nuevo == 'ANULADO' and not es_director(request.user):
        raise PermissionDenied
    with transaction.atomic():
        registro = get_object_or_404(
            RegistroAsistencia.objects.select_for_update(), pk=pk
        )
        if timezone.localtime(registro.fecha_hora).date() != fecha:
            raise PermissionDenied
        if registro.estado == nuevo:
            messages.info(request, 'El registro ya tiene ese estado.')
            return _redireccion_asistencias(request)
        if nuevo != 'ANULADO' and registro.estado == 'ANULADO':
            if registro_valido_del_dia(registro.estudiante, fecha).exclude(pk=registro.pk).exists():
                messages.error(request, 'El estudiante ya tiene otra asistencia válida ese día.')
                return _redireccion_asistencias(request)
        anterior = registro.estado
        registro.estado, registro.supervisor = nuevo, request.user
        registro.save(update_fields=['estado', 'supervisor'])
        _auditar(registro, anterior, nuevo, motivo, request)
    messages.success(request, 'El registro fue actualizado.')
    return _redireccion_asistencias(request)


@director_requerido
def anular_asistencia(request, pk):
    request.POST = request.POST.copy()
    request.POST['estado'] = 'ANULADO'
    return corregir_asistencia(request, pk)


@director_requerido
def restaurar_asistencia(request, pk):
    request.POST = request.POST.copy()
    request.POST['estado'] = request.POST.get('estado', 'PUNTUAL')
    return corregir_asistencia(request, pk)


@personal_requerido
def registrar_asistencia_manual(request, dni):
    if request.method != 'POST':
        return HttpResponse(status=405)
    fecha = _fecha_solicitada(request.POST.get('fecha'))
    if fecha > timezone.localdate() or not auxiliar_puede_corregir(request, fecha):
        raise PermissionDenied
    motivo = _motivo(request)
    estado = request.POST.get('estado')
    if not motivo or estado not in {'PUNTUAL', 'TARDANZA', 'FALTA'}:
        messages.error(request, 'Indica un motivo válido de al menos 5 caracteres.')
        return _redireccion_asistencias(request)
    estudiante = get_object_or_404(Estudiante, pk=dni, activo=True)
    with transaction.atomic():
        estudiante = Estudiante.objects.select_for_update().get(pk=estudiante.pk)
        if RegistroAsistencia.objects.filter(
            estudiante=estudiante, fecha_hora__date=fecha
        ).exists():
            messages.error(request, 'El estudiante ya tiene un registro ese día.')
            return _redireccion_asistencias(request)
        hora = HORA_TARDANZA if estado == 'TARDANZA' else HORA_FALTA
        registro = RegistroAsistencia.objects.create(
            estudiante=estudiante, metodo='DNI', estado=estado,
            supervisor=request.user,
        )
        inicio, _ = _rango_dia(fecha)
        RegistroAsistencia.objects.filter(pk=registro.pk).update(
            fecha_hora=inicio + timedelta(hours=hora.hour, minutes=hora.minute)
        )
        registro.refresh_from_db()
        _auditar(registro, '', estado, motivo, request)
    messages.success(request, 'Asistencia registrada manualmente.')
    return _redireccion_asistencias(request)


@director_requerido
def marcar_faltas_masivas(request):
    if request.method != 'POST':
        return HttpResponse(status=405)
    fecha = _fecha_solicitada(request.POST.get('fecha'))
    if fecha > timezone.localdate():
        raise PermissionDenied
    motivo = _motivo(request)
    if not motivo:
        messages.error(request, 'El motivo es obligatorio y debe tener entre 5 y 200 caracteres.')
        return _redireccion_asistencias(request)


    estudiantes = Estudiante.objects.filter(activo=True)
    if request.POST.get('grado'):
        estudiantes = estudiantes.filter(grado=request.POST['grado'])
    if request.POST.get('seccion'):
        estudiantes = estudiantes.filter(seccion=request.POST['seccion'])
    inicio, fin = _rango_dia(fecha)
    pendientes = list(estudiantes.exclude(
        pk__in=RegistroAsistencia.objects.filter(
            fecha_hora__gte=inicio, fecha_hora__lt=fin
        ).values('estudiante_id')
    ))
    with transaction.atomic():
        registros = RegistroAsistencia.objects.bulk_create([
            RegistroAsistencia(estudiante=estudiante, estado='FALTA',
                               metodo='DNI', supervisor=request.user)
            for estudiante in pendientes
        ])
        RegistroAsistencia.objects.filter(pk__in=[r.pk for r in registros]).update(
            fecha_hora=inicio + timedelta(hours=HORA_FALTA.hour)
        )
        CorreccionAsistencia.objects.bulk_create([
            CorreccionAsistencia(
                registro=registro, estado_anterior='', estado_nuevo='FALTA',
                motivo=motivo, usuario=request.user,
                ip=request.META.get('REMOTE_ADDR'),
            ) for registro in registros
        ])
    messages.success(request, f'Se marcaron {len(pendientes)} estudiantes como falta.')
    return _redireccion_asistencias(request)


@director_requerido
def gestion_usuarios(request):
    usuarios = User.objects.filter(groups__name='Auxiliar').distinct().order_by('username')
    error = ''
    if request.method == 'POST':
        accion = request.POST.get('accion')
        if accion == 'crear':
            username = request.POST.get('username', '').strip()
            password = request.POST.get('password', '')
            if User.objects.filter(username=username).exists():
                error = 'Ese usuario ya existe.'
            else:
                nuevo = User(
                    username=username,
                    first_name=request.POST.get('nombres', '').strip(),
                    last_name=request.POST.get('apellidos', '').strip(),
                )
                try:
                    validate_password(password, nuevo)
                    nuevo.set_password(password)
                    nuevo.is_staff = False
                    nuevo.save()
                    nuevo.groups.add(Group.objects.get_or_create(name='Auxiliar')[0])
                except ValidationError as exc:
                    error = ' '.join(exc.messages)
        else:
            usuario = get_object_or_404(User, pk=request.POST.get('usuario'))
            if accion == 'estado':
                if usuario.pk == request.user.pk:
                    error = 'No puedes desactivar tu propia cuenta.'
                else:
                    usuario.is_active = not usuario.is_active
                    usuario.save(update_fields=['is_active'])
            elif accion == 'reset':
                try:
                    validate_password(request.POST.get('password', ''), usuario)
                    usuario.set_password(request.POST['password'])
                    usuario.save(update_fields=['password'])
                except ValidationError as exc:
                    error = ' '.join(exc.messages)
    return render(request, 'asistencia/usuarios.html', {
        'usuarios': usuarios, 'error': error,
    })


def media_protegida(request, ruta):
    if not request.user.is_authenticated:
        return redirect(f'/login/?next={request.path}')
    if not tiene_rol(request.user):
        raise PermissionDenied
    try:
        archivo = safe_join(settings.MEDIA_ROOT, ruta)
    except ValueError:
        raise Http404
    if not Path(archivo).is_file():
        raise Http404
    return FileResponse(open(archivo, 'rb'), content_type=guess_type(archivo)[0] or 'application/octet-stream')


ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}
MAX_IMAGE_SIZE = 2 * 1024 * 1024


def _validar_imagen(archivo):
    extension = Path(archivo.name).suffix.lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        return None, 'La extensión debe ser JPG, JPEG, PNG o WEBP.'
    if archivo.size > MAX_IMAGE_SIZE:
        return None, 'La imagen no puede superar 2 MB.'
    try:
        imagen = Image.open(archivo)
        imagen.verify()
        archivo.seek(0)
    except (UnidentifiedImageError, OSError):
        return None, 'El archivo no es una imagen válida.'
    return extension, None


def _guardar_foto(estudiante, archivo, extension):
    nombre_anterior = estudiante.foto.name
    nombre_nuevo = f'fotos/{estudiante.dni}{extension}'
    contenido = ContentFile(archivo.read())
    storage = estudiante.foto.storage
    storage.delete(nombre_nuevo)
    nombre_guardado = storage.save(nombre_nuevo, contenido)
    estudiante.foto.name = nombre_guardado
    Estudiante.objects.filter(pk=estudiante.pk).update(foto=nombre_guardado)
    if nombre_anterior and nombre_anterior != nombre_nuevo:
        storage.delete(nombre_anterior)


@staff_required
def foto_estudiante(request, dni):
    estudiante = get_object_or_404(Estudiante, dni=dni)
    mensaje = ''
    error = ''
    if request.method == 'POST':
        nombres = request.POST.get('nombres', '').strip()
        apellidos = request.POST.get('apellidos', '').strip()
        grado = request.POST.get('grado', '').strip()
        seccion = request.POST.get('seccion', '').strip()
        archivo = request.FILES.get('foto')
        if not all((nombres, apellidos, grado, seccion)):
            error = 'Nombres, apellidos, grado y sección son obligatorios.'
        elif archivo:
            extension, error = _validar_imagen(archivo)
            if not error:
                _guardar_foto(estudiante, archivo, extension)
        if not error:
            estudiante.nombres = nombres
            estudiante.apellidos = apellidos
            estudiante.grado = grado
            estudiante.seccion = seccion
            estudiante.activo = request.POST.get('activo') == 'on'
            estudiante.save(update_fields=[
                'nombres', 'apellidos', 'grado', 'seccion', 'activo',
            ])
            mensaje = 'Los datos del estudiante se actualizaron correctamente.'
    return render(request, 'asistencia/foto_estudiante.html', {
        'estudiante': estudiante,
        'mensaje': mensaje,
        'error': error,
        'foto_url': estudiante.foto.url if estudiante.foto else static('foto-default.svg'),
    })


@staff_required
def fotos_lote(request):
    resumen = None
    if request.method == 'POST':
        asignadas = 0
        rechazadas = []
        for archivo in request.FILES.getlist('fotos'):
            dni, extension = Path(archivo.name).stem, Path(archivo.name).suffix.lower()
            if not re.fullmatch(r'\d{8}', dni):
                rechazadas.append(f'{archivo.name}: el nombre debe ser un DNI de 8 dígitos.')
                continue
            try:
                estudiante = Estudiante.objects.get(dni=dni)
            except Estudiante.DoesNotExist:
                rechazadas.append(f'{archivo.name}: el DNI no existe.')
                continue
            extension_validada, error = _validar_imagen(archivo)
            if error:
                rechazadas.append(f'{archivo.name}: {error}')
                continue
            _guardar_foto(estudiante, archivo, extension_validada)
            asignadas += 1
        resumen = {'asignadas': asignadas, 'rechazadas': rechazadas}
    return render(request, 'asistencia/fotos_lote.html', {'resumen': resumen})