import csv
import json
from datetime import time
from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.db.models import Count, Q
from .models import Estudiante, RegistroAsistencia

# --- Módulo de Registro en Puerta ---

def pantalla_registro(request):
    return render(request, 'asistencia/registro.html')

def buscar_estudiante(request):
    dni_recibido = request.GET.get('dni', '')
    try:
        estudiante = Estudiante.objects.get(dni=dni_recibido, activo=True)
        hoy = timezone.localdate()
        ya_ingreso = RegistroAsistencia.objects.filter(
            estudiante=estudiante, 
            fecha_hora__date=hoy, 
            estado__in=['PUNTUAL', 'TARDANZA']
        ).exists()
        
        datos = {
            'encontrado': True,
            'dni': estudiante.dni,
            'nombre_completo': f"{estudiante.nombres} {estudiante.apellidos}",
            'grado_seccion': f"{estudiante.grado} '{estudiante.seccion}'",
            'foto_url': estudiante.foto.url if estudiante.foto else '',
            'ya_ingreso': ya_ingreso
        }
    except Estudiante.DoesNotExist:
        datos = {'encontrado': False, 'mensaje': 'Estudiante no encontrado en la base de datos.'}
        
    return JsonResponse(datos)

def confirmar_ingreso(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        dni = data.get('dni')
        accion = data.get('accion')
        metodo = 'BARRAS' if len(dni) == 8 else 'DNI'
        
        estudiante = Estudiante.objects.get(dni=dni)
        
        if accion == 'falta':
            estado = 'FALTA'
        else:
            # Si la acción es confirmar asistencia, calcula puntualidad
            hora_actual = timezone.localtime().time()
            hora_limite = time(8, 0, 0)
            estado = 'PUNTUAL' if hora_actual <= hora_limite else 'TARDANZA'
            
        RegistroAsistencia.objects.create(
            estudiante=estudiante,
            metodo=metodo,
            estado=estado,
            supervisor=request.user if request.user.is_authenticated else None
        )
        return JsonResponse({'success': True, 'estado': estado})

# --- Panel de Métricas y Reportes ---

def dashboard(request):
    hoy = timezone.localdate()
    
    # 1. Capturar los filtros desde la URL (si existen)
    grado_filtro = request.GET.get('grado', '')
    seccion_filtro = request.GET.get('seccion', '')
    
    # 2. Filtrar los estudiantes base
    estudiantes = Estudiante.objects.filter(activo=True)
    if grado_filtro:
        estudiantes = estudiantes.filter(grado=grado_filtro)
    if seccion_filtro:
        estudiantes = estudiantes.filter(seccion=seccion_filtro)
        
    total_estudiantes = estudiantes.count()
    
    # 3. Filtrar las asistencias solo para los estudiantes seleccionados
    asistencias_hoy = RegistroAsistencia.objects.filter(
        estudiante__in=estudiantes,
        fecha_hora__date=hoy, 
        estado__in=['PUNTUAL', 'TARDANZA']
    ).count()
    
    tardanzas_hoy = RegistroAsistencia.objects.filter(
        estudiante__in=estudiantes,
        fecha_hora__date=hoy, 
        estado='TARDANZA'
    ).count()
    
    inasistencias_hoy = max(0, total_estudiantes - asistencias_hoy)
    porcentaje_asistencia = round((asistencias_hoy / total_estudiantes * 100), 1) if total_estudiantes > 0 else 0

    # 4. Obtener estudiantes con faltas registradas de esa selección
    estudiantes_con_faltas = estudiantes.annotate(
        total_faltas=Count('asistencias', filter=Q(asistencias__estado='FALTA'))
    ).order_by('-total_faltas')[:10]

    # 5. Obtener listas únicas de grados y secciones para llenar los <select>
    grados_disp = Estudiante.objects.filter(activo=True).values_list('grado', flat=True).distinct().order_by('grado')
    secciones_disp = Estudiante.objects.filter(activo=True).values_list('seccion', flat=True).distinct().order_by('seccion')

    contexto = {
        'total_estudiantes': total_estudiantes,
        'asistencias_hoy': asistencias_hoy,
        'tardanzas_hoy': tardanzas_hoy,
        'inasistencias_hoy': inasistencias_hoy,
        'porcentaje_asistencia': porcentaje_asistencia,
        'estudiantes_con_faltas': estudiantes_con_faltas,
        'grados_disponibles': grados_disp,
        'secciones_disponibles': secciones_disp,
        'grado_seleccionado': grado_filtro,
        'seccion_seleccionada': seccion_filtro,
    }
    return render(request, 'asistencia/dashboard.html', contexto)

def exportar_reporte_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="reporte_asistencia.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['DNI', 'Apellidos', 'Nombres', 'Grado', 'Seccion', 'Fecha y Hora', 'Estado', 'Metodo'])
    
    registros = RegistroAsistencia.objects.select_related('estudiante').all().order_by('-fecha_hora')
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