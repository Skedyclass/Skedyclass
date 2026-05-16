from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('planificador', '0014_clase_google_event_id'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='HorarioAcademico',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('hora_inicio_jornada', models.TimeField(default='06:00')),
                ('hora_fin_jornada', models.TimeField(default='14:00')),
                ('duracion_sesion', models.PositiveSmallIntegerField(default=60, help_text='Minutos por sesión')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('usuario', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='horario_academico',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'verbose_name': 'Horario Académico'},
        ),
        migrations.CreateModel(
            name='BloqueDescanso',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=100)),
                ('hora_inicio', models.TimeField()),
                ('hora_fin', models.TimeField()),
                ('horario', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='descansos',
                    to='planificador.horarioacademico',
                )),
            ],
            options={
                'verbose_name': 'Bloque de Descanso',
                'verbose_name_plural': 'Bloques de Descanso',
                'ordering': ['hora_inicio'],
            },
        ),
    ]
