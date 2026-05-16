from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('planificador', '0012_clase_objetivos'),
    ]

    operations = [
        # Drop Calificacion first (has FK to Estudiante)
        migrations.DeleteModel(name='Calificacion'),
        # Drop Estudiante
        migrations.DeleteModel(name='Estudiante'),
        # Add schedule fields to Curso
        migrations.AddField(
            model_name='curso',
            name='dia_semana',
            field=models.CharField(
                max_length=20,
                blank=True,
                choices=[
                    ('lunes', 'Lunes'),
                    ('martes', 'Martes'),
                    ('miercoles', 'Miércoles'),
                    ('jueves', 'Jueves'),
                    ('viernes', 'Viernes'),
                ],
                default='',
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='curso',
            name='hora_inicio',
            field=models.TimeField(null=True, blank=True),
        ),
    ]
