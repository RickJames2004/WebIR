from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Crea o verifica los grupos Director y Auxiliar.'

    def handle(self, *args, **options):
        Group.objects.get_or_create(name='Director')
        Group.objects.get_or_create(name='Auxiliar')
        self.stdout.write(self.style.SUCCESS('Roles verificados correctamente.'))
