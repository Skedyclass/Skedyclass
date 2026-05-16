from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('planificador', '0007_remove_profesor_add_perfil_docente'),
    ]

    operations = [
        migrations.AddField(
            model_name='clase',
            name='tipo_clase',
            field=models.CharField(
                choices=[('normal', 'Normal'), ('dinamica', 'Dinámica'), ('mixta', 'Mixta')],
                default='normal',
                max_length=20,
            ),
        ),
    ]
