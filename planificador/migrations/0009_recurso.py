from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('planificador', '0008_clase_tipo_clase'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Recurso',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('titulo', models.CharField(max_length=200)),
                ('descripcion', models.TextField(blank=True)),
                ('tipo', models.CharField(
                    choices=[
                        ('documento', 'Documento / PDF'),
                        ('video', 'Enlace de Video'),
                        ('imagen', 'Imagen'),
                        ('taller', 'Taller / Actividad'),
                        ('otro', 'Otro'),
                    ],
                    default='documento',
                    max_length=20,
                )),
                ('archivo', models.FileField(blank=True, null=True, upload_to='recursos/%Y/%m/')),
                ('url_video', models.URLField(blank=True, max_length=500)),
                ('fecha_creacion', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('usuario', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='recursos',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Recurso',
                'verbose_name_plural': 'Recursos',
                'ordering': ['-fecha_creacion'],
            },
        ),
    ]
