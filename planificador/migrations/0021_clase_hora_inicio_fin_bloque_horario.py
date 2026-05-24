from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('planificador', '0020_alter_recurso_archivo'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # 1. Rename hora → hora_inicio on Clase
        migrations.RenameField(
            model_name='clase',
            old_name='hora',
            new_name='hora_inicio',
        ),
        # 2. Add hora_fin (nullable) to Clase
        migrations.AddField(
            model_name='clase',
            name='hora_fin',
            field=models.TimeField(blank=True, null=True),
        ),
        # 3. Update ordering meta (no DB op needed, Django handles it)
        migrations.AlterModelOptions(
            name='clase',
            options={'ordering': ['-fecha', '-hora_inicio'], 'verbose_name': 'Clase', 'verbose_name_plural': 'Clases'},
        ),
        # 4. Add año lectivo fields to HorarioAcademico
        migrations.AddField(
            model_name='horarioacademico',
            name='ano_lectivo',
            field=models.CharField(blank=True, help_text='Ej: 2025-2026', max_length=20),
        ),
        migrations.AddField(
            model_name='horarioacademico',
            name='fecha_inicio_lectivo',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='horarioacademico',
            name='fecha_fin_lectivo',
            field=models.DateField(blank=True, null=True),
        ),
        # 5. Create BloqueHorario
        migrations.CreateModel(
            name='BloqueHorario',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('dia_semana', models.PositiveSmallIntegerField(choices=[(0, 'Lunes'), (1, 'Martes'), (2, 'Miércoles'), (3, 'Jueves'), (4, 'Viernes')])),
                ('hora_inicio', models.TimeField()),
                ('hora_fin', models.TimeField()),
                ('titulo', models.CharField(blank=True, max_length=200)),
                ('materia', models.CharField(blank=True, choices=[('Matemáticas', 'Matemáticas'), ('Lenguaje', 'Lenguaje'), ('Ciencias Naturales', 'Ciencias Naturales'), ('Ciencias Sociales', 'Ciencias Sociales'), ('Educación Física', 'Educación Física'), ('Artes', 'Artes'), ('Música', 'Música'), ('Inglés', 'Inglés')], max_length=50)),
                ('curso', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='bloques_horario', to='planificador.curso')),
                ('usuario', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='bloques_horario', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Bloque de Horario',
                'verbose_name_plural': 'Bloques de Horario',
                'ordering': ['dia_semana', 'hora_inicio'],
            },
        ),
    ]
