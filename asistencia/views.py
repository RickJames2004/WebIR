from django.shortcuts import render
from django.http import JsonResponse
from django.utils import timezone
from datetime import time
from .models import Estudiante, RegistroAsistencia
import json
import csv
from django.http import HttpResponse
from django.db.models import Count, Q

def pantalla_registro(request):
    # Carga la plantilla visual para el supervisor
    return render(request, 'asistencia/registro.html')

def buscar_estudiante(request):
    # Caso de Uso: Leer código o digitar DNI y mostrar datos y foto
    dni_recibido = request.GET.get('dni', '')
    try:
        estudiante = Estudiante.objects.get(dni=dni_recibido, activo=True)
        # Verificar si ya registró asistencia hoy (Regla de Negocio RN01)
        hoy = timezone.localdate()
        ya_ingreso = RegistroAsistencia.objects.filter(estudiante=estudiante, fecha_hora__date=hoy, estado__in=['PUNTUAL', 'TARDANZA']).exists()
        
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
    # Caso de Uso: Confirmar o anular el registro tras verificación visual
    if request.method == 'POST':
        data = json.loads(request.body)
        dni = data.get('dni')
        accion = data.get('accion') # 'confirmar' o 'anular'
        metodo = 'BARRAS' if len(dni) == 8 else 'DNI' # Asumimos BARRAS si viene del escáner directo
        
        estudiante = Estudiante.objects.get(dni=dni)
        
        if accion == 'anular':
            estado = 'ANULADO'
        else:
            # Regla de Negocio RN02: Calcular tardanza (ej. hora límite 08:00 AM)
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
    
    def dashboard(request):
        hoy = timezone.localdate()
        total_estudiantes = Estudiante.objects.filter(activo=True).count()
        
        # Asistencias del día
        asistencias_hoy = RegistroAsistencia.objects.filter(
            fecha_hora__date=hoy, 
            estado__in=['PUNTUAL', 'TARDANZA']
        ).count()
        
        tardanzas_hoy = RegistroAsistencia.objects.filter(
            fecha_hora__date=hoy, 
            estado='TARDANZA'
        ).count()
        
        inasistencias_hoy = max(0, total_estudiantes - asistencias_hoy)
        porcentaje_asistencia = round((asistencias_hoy / total_estudiantes * 100), 1) if total_estudiantes > 0 else 0

        # Estudiantes con más faltas (Ranking - Caso CU06)
        estudiantes_con_faltas = Estudiante.objects.filter(activo=True).annotate(
            total_faltas=Count('asistencias', filter=Q(asistencias__estado='ANULADO'))
        ).order_by('-total_faltas')[:10]

        contexto = {
            'total_estudiantes': total_estudiantes,
            'asistencias_hoy': asistencias_hoy,
            'tardanzas_hoy': tardanzas_hoy,
            'inasistencias_hoy': inasistencias_hoy,
            'porcentaje_asistencia': porcentaje_asistencia,
            'estudiantes_con_faltas': estudiantes_con_faltas,
        }
        return render(request, 'asistencia/dashboard.html', contexto)


def exportar_reporte_csv(request):
    # Caso CU07: Exportar reporte a Excel/CSV
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