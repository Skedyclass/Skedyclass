from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('planificador', '0022_horarioacademico_anual_activo'),
    ]

    operations = [
        migrations.DeleteModel(
            name='BloqueHorario',
        ),
        migrations.RemoveField(
            model_name='horarioacademico',
            name='ano_lectivo',
        ),
        migrations.RemoveField(
            model_name='horarioacademico',
            name='fecha_inicio_lectivo',
        ),
        migrations.RemoveField(
            model_name='horarioacademico',
            name='fecha_fin_lectivo',
        ),
        migrations.RemoveField(
            model_name='horarioacademico',
            name='horario_anual_activo',
        ),
    ]
