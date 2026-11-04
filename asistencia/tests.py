from datetime import datetime, timedelta
from io import BytesIO
import tempfile

from django.test import TestCase
from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from PIL import Image

from .models import Estudiante, RegistroAsistencia
from .models import CorreccionAsistencia


class RegistroAsistenciaTests(TestCase):
    def setUp(self):
        self.director = User.objects.create_superuser(
            username='director', password='clave-segura'
        )
        self.estudiante = Estudiante.objects.create(
            dni='74852316',
            nombres='Ana',
            apellidos='Pérez',
            grado='3',
            seccion='B',
        )

    def test_registra_asistencia_por_dni(self):
        self.client.force_login(self.director)
        response = self.client.post(
            '/api/confirmar_ingreso/',
            data={'dni': '74852316', 'accion': 'confirmar', 'metodo': 'DNI'},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['success'], True)
        self.assertEqual(RegistroAsistencia.objects.get().metodo, 'DNI')

    def test_no_permite_dos_registros_el_mismo_dia(self):
        self.client.force_login(self.director)
        self.client.post(
            '/api/confirmar_ingreso/',
            data={'dni': '74852316', 'accion': 'confirmar', 'metodo': 'DNI'},
            content_type='application/json',
        )
        response = self.client.post(
            '/api/confirmar_ingreso/',
            data={'dni': '74852316', 'accion': 'confirmar', 'metodo': 'DNI'},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(RegistroAsistencia.objects.count(), 1)

    def test_no_permite_nuevo_registro_si_el_anterior_fue_anulado(self):
        self.client.force_login(self.director)
        RegistroAsistencia.objects.create(
            estudiante=self.estudiante,
            metodo='DNI',
            estado='ANULADO',
        )

        response = self.client.post(
            '/api/confirmar_ingreso/',
            data={'dni': '74852316', 'accion': 'confirmar', 'metodo': 'DNI'},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(RegistroAsistencia.objects.count(), 1)

    def test_genera_codigo_de_barras_para_estudiante(self):
        self.client.force_login(self.director)
        response = self.client.get('/estudiantes/74852316/codigo-barras/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/svg+xml')
        self.assertIn(b'74852316', response.content)

    def test_dashboard_requiere_login(self):
        response = self.client.get('/dashboard/')

        self.assertRedirects(response, '/login/?next=/dashboard/')

    def test_sidebar_es_comun_en_paginas_protegidas(self):
        self.client.force_login(self.director)
        rutas = [
            '/',
            '/dashboard/',
            '/asistencias/',
            '/gestion/',
            '/gestion/importar/',
            '/gestion/74852316/foto/',
            '/gestion/fotos/',
            '/gestion/usuarios/',
        ]
        enlaces = [
            'Registro de ingreso',
            'Asistencias por fecha',
            'Panel de métricas',
            'Gestión de estudiantes',
            'Importar estudiantes',
            'Fotos en lote',
            'Usuarios',
            'Cerrar sesión',
        ]
        for ruta in rutas:
            response = self.client.get(ruta)
            self.assertEqual(response.status_code, 200, ruta)
            for enlace in enlaces:
                self.assertContains(response, enlace, msg_prefix=ruta)

    def test_dashboard_carga_chart_antes_de_inicializar(self):
        self.client.force_login(self.director)
        contenido = self.client.get('/dashboard/').content.decode()
        carga = contenido.index('src="/static/chart.umd.min.js"')
        inicializacion = contenido.index("typeof Chart === 'undefined'")
        self.assertLess(carga, inicializacion)

    def test_usuario_staff_puede_importar_csv(self):
        usuario = User.objects.create_user(
            username='admin',
            password='clave-segura',
            is_superuser=True,
        )
        self.client.force_login(usuario)
        response = self.client.post(
            '/gestion/importar/',
            data={
                'archivo_csv': (
                    SimpleUploadedFile(
                        'estudiantes.csv',
                        (
                            'dni;apellidos;nombres;grado;seccion\n'
                            '70123456;López;Carlos;1;A\n'
                            '123;Dato;Inválido;1;A\n'
                        ).encode('utf-8'),
                        content_type='text/csv',
                    )
                ),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Estudiante.objects.filter(dni='70123456').exists())
        self.assertContains(response, 'creados')
        self.assertContains(response, 'Línea 3')

    def test_importar_actualiza_estudiante_existente(self):
        usuario = User.objects.create_user(
            username='admin',
            password='clave-segura',
            is_superuser=True,
        )
        self.client.force_login(usuario)
        response = self.client.post(
            '/gestion/importar/',
            data={
                'archivo_csv': SimpleUploadedFile(
                    'estudiantes.csv',
                    'dni,apellidos,nombres,grado,seccion\n74852316,Pérez,Ana,5,C\n'.encode('utf-8'),
                    content_type='text/csv',
                ),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.estudiante.refresh_from_db()
        self.assertEqual(self.estudiante.grado, '5')
        self.assertEqual(Estudiante.objects.count(), 1)
        self.assertContains(response, 'actualizados')

    def crear_usuario_staff(self):
        usuario = User.objects.create_user(
            username='staff-fechas',
            password='clave-segura',
            is_superuser=True,
        )
        self.client.force_login(usuario)

    def crear_registro(self, estudiante, fecha, estado='PUNTUAL'):
        registro = RegistroAsistencia.objects.create(
            estudiante=estudiante,
            metodo='DNI',
            estado=estado,
        )
        RegistroAsistencia.objects.filter(pk=registro.pk).update(
            fecha_hora=timezone.make_aware(datetime.combine(fecha, datetime.min.time()))
        )
        return registro

    def imagen_subida(self, nombre='foto.png', formato='PNG'):
        contenido = BytesIO()
        Image.new('RGB', (20, 20), color='green').save(contenido, format=formato)
        return SimpleUploadedFile(
            nombre,
            contenido.getvalue(),
            content_type=f'image/{formato.lower()}',
        )

    def test_asistencias_requiere_login(self):
        response = self.client.get('/asistencias/')

        self.assertRedirects(response, '/login/?next=/asistencias/')

    def test_asistencias_filtra_por_fecha_y_no_muestra_otro_dia(self):
        self.crear_usuario_staff()
        hoy = timezone.localdate()
        self.crear_registro(self.estudiante, hoy, 'PUNTUAL')
        otro = Estudiante.objects.create(
            dni='70123456', nombres='Luis', apellidos='García',
            grado='3', seccion='B',
        )
        self.crear_registro(otro, hoy - timedelta(days=1), 'PUNTUAL')

        response = self.client.get('/asistencias/', {'fecha': hoy.isoformat()})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '74852316')
        self.assertFalse(any(
            registro.estudiante.dni == '70123456'
            for registro in response.context['pagina']
        ))

    def test_fecha_invalida_usa_hoy(self):
        self.crear_usuario_staff()

        response = self.client.get('/asistencias/', {'fecha': 'fecha-invalida'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, timezone.localdate().isoformat())

    def test_sin_registro_solo_incluye_activos(self):
        self.crear_usuario_staff()
        hoy = timezone.localdate()
        self.crear_registro(self.estudiante, hoy)
        sin_registro = Estudiante.objects.create(
            dni='70123456', nombres='Luis', apellidos='García',
            grado='3', seccion='B',
        )
        inactivo = Estudiante.objects.create(
            dni='76543210', nombres='Inactivo', apellidos='Alumno',
            grado='3', seccion='B', activo=False,
        )

        response = self.client.get('/asistencias/', {'fecha': hoy.isoformat()})

        self.assertContains(response, sin_registro.dni)
        self.assertNotContains(response, inactivo.dni)

    def test_filtros_de_grado_seccion_y_estado(self):
        self.crear_usuario_staff()
        hoy = timezone.localdate()
        self.crear_registro(self.estudiante, hoy, 'PUNTUAL')
        otro = Estudiante.objects.create(
            dni='70123456', nombres='Luis', apellidos='García',
            grado='4', seccion='A',
        )
        self.crear_registro(otro, hoy, 'FALTA')

        response = self.client.get('/asistencias/', {
            'fecha': hoy.isoformat(), 'grado': '4', 'seccion': 'A', 'estado': 'FALTA',
        })

        self.assertContains(response, '70123456')
        self.assertNotContains(response, '74852316')

    def test_anulado_no_cuenta_como_puntual_ni_tardanza(self):
        self.crear_usuario_staff()
        hoy = timezone.localdate()
        self.crear_registro(self.estudiante, hoy, 'ANULADO')

        response = self.client.get('/asistencias/', {'fecha': hoy.isoformat()})

        self.assertEqual(response.context['conteos'].get('PUNTUAL', 0), 0)
        self.assertEqual(response.context['conteos'].get('TARDANZA', 0), 0)
        self.assertEqual(response.context['conteos'].get('ANULADO', 0), 1)
        self.assertContains(response, 'Anulado')

    @override_settings(MEDIA_ROOT=tempfile.mkdtemp())
    def test_foto_por_defecto_y_foto_real(self):
        self.client.force_login(self.director)
        response = self.client.get('/api/buscar_estudiante/?dni=74852316')
        self.assertEqual(response.json()['foto_url'], '/static/foto-default.svg')

        self.estudiante.foto.save('original.png', self.imagen_subida(), save=True)
        response = self.client.get('/api/buscar_estudiante/?dni=74852316')
        self.assertIn('/media/', response.json()['foto_url'])

    @override_settings(MEDIA_ROOT=tempfile.mkdtemp())
    def test_subida_individual_valida_y_rechaza_archivos_invalidos(self):
        self.crear_usuario_staff()
        response = self.client.post(
            '/gestion/74852316/foto/',
            {
                'nombres': 'Ana',
                'apellidos': 'Pérez',
                'grado': '3',
                'seccion': 'B',
                'activo': 'on',
                'foto': self.imagen_subida(),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.estudiante.refresh_from_db()
        self.assertEqual(self.estudiante.foto.name, 'fotos/74852316.png')

        response = self.client.post(
            '/gestion/74852316/foto/',
            {
                'nombres': 'Ana',
                'apellidos': 'Pérez',
                'grado': '3',
                'seccion': 'B',
                'activo': 'on',
                'foto': SimpleUploadedFile('texto.txt', b'no es imagen', content_type='text/plain'),
            },
        )
        self.assertContains(response, 'extensión', status_code=200)

        response = self.client.post(
            '/gestion/74852316/foto/',
            {
                'nombres': 'Ana',
                'apellidos': 'Pérez',
                'grado': '3',
                'seccion': 'B',
                'activo': 'on',
                'foto': SimpleUploadedFile('grande.png', b'x' * (2 * 1024 * 1024 + 1), content_type='image/jpg'),
            },
        )
        self.assertContains(response, '2 MB', status_code=200)

    def test_edita_datos_sin_reemplazar_foto(self):
        self.crear_usuario_staff()
        response = self.client.post('/gestion/74852316/foto/', {
            'nombres': 'Ana María',
            'apellidos': 'Pérez Gómez',
            'grado': '4',
            'seccion': 'A',
        })

        self.assertEqual(response.status_code, 200)
        self.estudiante.refresh_from_db()
        self.assertEqual(self.estudiante.nombres, 'Ana María')
        self.assertEqual(self.estudiante.apellidos, 'Pérez Gómez')
        self.assertEqual(self.estudiante.grado, '4')
        self.assertEqual(self.estudiante.seccion, 'A')
        self.assertFalse(self.estudiante.activo)

    @override_settings(MEDIA_ROOT=tempfile.mkdtemp())
    def test_fotos_en_lote_asigna_y_rechaza(self):
        self.crear_usuario_staff()
        response = self.client.post('/gestion/fotos/', {
            'fotos': [
                self.imagen_subida('74852316.jpg', 'JPEG'),
                self.imagen_subida('nombre-invalido.png'),
                self.imagen_subida('70123456.png'),
            ],
        })

        self.assertEqual(response.status_code, 200)
        self.estudiante.refresh_from_db()
        self.assertEqual(self.estudiante.foto.name, 'fotos/74852316.jpg')
        self.assertContains(response, 'nombre-invalido.png')
        self.assertContains(response, '70123456.png')

    def test_fotos_requieren_usuario_staff(self):
        response = self.client.get('/gestion/74852316/foto/')

        self.assertRedirects(response, '/login/?next=/gestion/74852316/foto/')

        User.objects.create_user(username='normal', password='clave-segura')
        self.client.login(username='normal', password='clave-segura')
        response = self.client.get('/gestion/fotos/')
        self.assertEqual(response.status_code, 403)


class RolesYCorreccionesTests(TestCase):
    def setUp(self):
        self.director = User.objects.create_superuser('director2', password='clave-segura')
        self.auxiliar = User.objects.create_user('auxiliar2', password='clave-segura')
        self.auxiliar.groups.add(Group.objects.get_or_create(name='Auxiliar')[0])
        self.estudiante = Estudiante.objects.create(
            dni='74852316', nombres='Ana', apellidos='Pérez', grado='3', seccion='B',
        )

    def test_api_sin_login_devuelve_401_json(self):
        response = self.client.get('/api/buscar_estudiante/?dni=74852316')
        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json()['encontrado'])

    def test_auxiliar_no_accede_dashboard(self):
        self.client.force_login(self.auxiliar)
        self.assertEqual(self.client.get('/dashboard/').status_code, 403)

    @override_settings(CORRECCIONES_IPS_PERMITIDAS=['10.0.0.5'])
    def test_auxiliar_puede_registro_manual_hoy_y_audita(self):
        self.client.force_login(self.auxiliar)
        response = self.client.post(
            '/asistencias/74852316/manual/',
            {'fecha': timezone.localdate().isoformat(), 'estado': 'FALTA', 'motivo': 'Confirmado por docente'},
            REMOTE_ADDR='10.0.0.5',
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(RegistroAsistencia.objects.get().estado, 'FALTA')
        self.assertEqual(CorreccionAsistencia.objects.get().usuario, self.auxiliar)

    def test_usuario_sin_rol_recibe_403(self):
        usuario = User.objects.create_user('sinrol', password='clave-segura')
        self.client.force_login(usuario)
        self.assertEqual(self.client.get('/asistencias/').status_code, 403)
