from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('asistencia', '0004_alter_registroasistencia_metodo'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddIndex(
            model_name='registroasistencia',
            index=models.Index(fields=['fecha_hora'], name='asist_reg_fecha_idx'),
        ),
        migrations.AddIndex(
            model_name='registroasistencia',
            index=models.Index(fields=['estudiante', 'fecha_hora'], name='asist_reg_estud_fecha_idx'),
        ),
        migrations.CreateModel(
            name='CorreccionAsistencia',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('estado_anterior', models.CharField(blank=True, max_length=10)),
                ('estado_nuevo', models.CharField(max_length=10)),
                ('motivo', models.CharField(max_length=200)),
                ('fecha_hora', models.DateTimeField(auto_now_add=True)),
                ('ip', models.GenericIPAddressField(blank=True, null=True)),
                ('registro', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='correcciones', to='asistencia.registroasistencia')),
                ('usuario', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='correcciones_asistencia', to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
