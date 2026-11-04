from django.shortcuts import render
from django.http import JsonResponse
from django.utils import timezone
from datetime import time
from .models import Estudiante, RegistroAsistencia
import json

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