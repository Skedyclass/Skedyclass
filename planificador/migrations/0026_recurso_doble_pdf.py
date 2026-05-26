from django.db import migrations, models
import planificador.models


class Migration(migrations.Migration):

    dependencies = [
        ('planificador', '0025_anio_actual_dinamico'),
    ]

    operations = [
        migrations.AddField(
            model_name='recurso',
            name='archivo_profesor',
            field=models.FileField(blank=True, null=True, upload_to=planificador.models._recurso_upload_path),
        ),
        migrations.AddField(
            model_name='recurso',
            name='archivo_estudiante',
            field=models.FileField(blank=True, null=True, upload_to=planificador.models._recurso_upload_path),
        ),
    ]
