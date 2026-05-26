from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('planificador', '0026_recurso_doble_pdf'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Notificacion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('titulo', models.CharField(max_length=200)),
                ('mensaje', models.TextField()),
                ('tipo', models.CharField(choices=[('info', 'Información'), ('alerta', 'Alerta'), ('exito', 'Éxito'), ('sistema', 'Sistema')], default='info', max_length=20)),
                ('leido', models.BooleanField(db_index=True, default=False)),
                ('fecha_creacion', models.DateTimeField(auto_now_add=True)),
                ('clave', models.CharField(blank=True, db_index=True, max_length=200)),
                ('usuario', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notificaciones', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Notificación',
                'verbose_name_plural': 'Notificaciones',
                'ordering': ['-fecha_creacion'],
            },
        ),
        migrations.AddIndex(
            model_name='notificacion',
            index=models.Index(fields=['usuario', 'leido'], name='notif_user_leido_idx'),
        ),
        migrations.AddIndex(
            model_name='notificacion',
            index=models.Index(fields=['usuario', 'fecha_creacion'], name='notif_user_fecha_idx'),
        ),
    ]
