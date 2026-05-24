from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('planificador', '0021_clase_hora_inicio_fin_bloque_horario'),
    ]

    operations = [
        migrations.AddField(
            model_name='horarioacademico',
            name='horario_anual_activo',
            field=models.BooleanField(default=False, help_text='Activa proyección automática y alertas de planificación'),
        ),
    ]
