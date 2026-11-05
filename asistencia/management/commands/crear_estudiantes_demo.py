from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count

from asistencia.models import Estudiante


class Command(BaseCommand):
    help = 'Completa las secciones de primero a quinto con estudiantes ficticios.'

    grados = ('1ero', '2do', '3ero', '4to', '5to')
    secciones = ('A', 'B', 'C')
    nombres = (
        'Valeria', 'Mateo', 'Camila', 'Thiago', 'Luciana', 'Santiago',
        'Antonella', 'Sebastián', 'Mía', 'Gabriel', 'Sofía', 'Diego',
        'Daniela', 'Joaquín', 'Alessia', 'Adrián', 'Mariana', 'Nicolás',
        'Ariana', 'Emiliano', 'Isabella', 'Benjamín', 'Ximena', 'Samuel',
        'Lucía', 'Andrés', 'Julieta', 'Martín', 'Renata', 'Leonardo',
        'Fernanda', 'Ángel', 'Paula', 'Ian', 'Victoria', 'Maximiliano',
        'Carolina', 'Bruno', 'Alejandra', 'Dylan',
    )
    apellidos = (
        'García Mendoza', 'Rojas Castillo', 'Huamán Salazar', 'Torres Paredes',
        'Flores Navarro', 'Vargas Medina', 'Quispe Romero', 'Ramírez Cabrera',
        'Mendoza Cárdenas', 'Chávez Aguilar', 'Castillo Herrera', 'Díaz Campos',
        'Sánchez Lozano', 'Ramos Espinoza', 'Cruz Valdivia', 'Reyes Palomino',
        'Morales Zegarra', 'Gutiérrez Vera', 'Ortiz Benavides', 'Paredes Rivas',
        'Silva Carrasco', 'Medina Soto', 'Cáceres León', 'Salazar Núñez',
        'Herrera Ponce', 'Navarro Vilca', 'Aguilar Bravo', 'Romero Acosta',
        'Cabrera Tapia', 'Espinoza Ríos', 'Valdez Cornejo', 'Campos Delgado',
        'Palomino Arias', 'Vera Bustamante', 'Lozano Fuentes', 'Carrasco Gil',
        'Zegarra Flores', 'Núñez Pacheco', 'Rivas Ochoa', 'León Mendoza',
    )

    def nombre_completo(self, indice):
        posicion = indice % len(self.nombres)
        apellido = (indice // len(self.nombres) + 7 * indice) % len(self.apellidos)
        return self.nombres[posicion], self.apellidos[apellido]

    @transaction.atomic
    def handle(self, *args, **options):
        conteos = {
            (item['grado'], item['seccion']): item['total']
            for item in Estudiante.objects.values('grado', 'seccion')
            .order_by()
            .annotate(total=Count('dni'))
        }
        dnis_existentes = set(
            Estudiante.objects.values_list('dni', flat=True)
        )
        siguiente_dni = 99000001
        nuevos = []
        actualizados = 0

        for indice_grado, grado in enumerate(self.grados):
            for indice_seccion, seccion in enumerate(self.secciones):
                grupo = (grado, seccion)
                indice_grupo = indice_grado * len(self.secciones) + indice_seccion
                objetivo = 28 + ((indice_grado * len(self.secciones) + indice_seccion) % 4)
                estudiantes_demo = Estudiante.objects.filter(
                    grado=grado,
                    seccion=seccion,
                    nombres__startswith='Estudiante demo ',
                    apellidos=f'Prueba {grado} {seccion}',
                )
                for estudiante in estudiantes_demo:
                    try:
                        numero = int(estudiante.nombres.rsplit(' ', 1)[1])
                    except (IndexError, ValueError) as error:
                        raise CommandError(
                            f'No se pudo identificar el registro de demostración {estudiante.dni}.'
                        ) from error
                    estudiante.nombres, estudiante.apellidos = self.nombre_completo(
                        indice_grupo * 31 + numero - 1
                    )
                    estudiante.save(update_fields=['nombres', 'apellidos'])
                    actualizados += 1

                total_grupo = conteos.get(grupo, 0)
                for numero in range(total_grupo + 1, objetivo + 1):
                    nombres, apellidos = self.nombre_completo(
                        indice_grupo * 31 + numero - 1
                    )
                    while str(siguiente_dni) in dnis_existentes:
                        siguiente_dni += 1
                    if siguiente_dni > 99999999:
                        raise CommandError('No quedan DNI de demostración disponibles.')

                    dni = str(siguiente_dni)
                    dnis_existentes.add(dni)
                    siguiente_dni += 1
                    nuevos.append(Estudiante(
                        dni=dni,
                        nombres=nombres,
                        apellidos=apellidos,
                        grado=grado,
                        seccion=seccion,
                    ))

        Estudiante.objects.bulk_create(nuevos)
        self.stdout.write(self.style.SUCCESS(
            f'Se crearon {len(nuevos)} estudiantes ficticios y se actualizaron '
            f'{actualizados} registros de demostración existentes.'
        ))
