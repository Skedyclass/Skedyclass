import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('planificador', '0005_configuracion_tema'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Ownership: Clase y Nota vinculadas al usuario
        migrations.AddField(
            model_name='clase',
            name='usuario',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='clases',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='nota',
            name='usuario',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='notas',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        # Timestamps de auditoría
        migrations.AddField(
            model_name='clase',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AddField(
            model_name='nota',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AddField(
            model_name='profesor',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AddField(
            model_name='estudiante',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
    ]
