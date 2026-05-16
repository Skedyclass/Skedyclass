from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('planificador', '0016_alter_horarioacademico_hora_fin_jornada_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='curso',
            name='dia_semana',
        ),
        migrations.RemoveField(
            model_name='curso',
            name='hora_inicio',
        ),
        migrations.RemoveField(
            model_name='curso',
            name='descripcion',
        ),
        migrations.RenameField(
            model_name='curso',
            old_name='grado_nombre',
            new_name='nivel_academico',
        ),
        migrations.AlterField(
            model_name='curso',
            name='nivel_academico',
            field=models.CharField(blank=True, max_length=100),
        ),
    ]
