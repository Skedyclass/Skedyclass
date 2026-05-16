from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('planificador', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ConfiguracionUsuario',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('idioma', models.CharField(default='es', max_length=10)),
                ('notif_clases', models.BooleanField(default=True)),
                ('notif_tareas', models.BooleanField(default=True)),
                ('notif_resumen', models.BooleanField(default=False)),
                ('nombre_institucion', models.CharField(blank=True, max_length=200)),
                ('cargo', models.CharField(blank=True, max_length=100)),
                ('usuario', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='configuracion',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Configuracion de Usuario',
            },
        ),
    ]
