from django.db import migrations, models


def migrar_in_progress_a_pending(apps, schema_editor):
    Clase = apps.get_model('planificador', 'Clase')
    Clase.objects.filter(estado='in_progress').update(estado='pending')


class Migration(migrations.Migration):

    dependencies = [
        ('planificador', '0027_notificacion'),
    ]

    operations = [
        migrations.AddField(
            model_name='clase',
            name='razon_cancelacion',
            field=models.CharField(blank=True, max_length=300),
        ),
        migrations.AlterField(
            model_name='clase',
            name='estado',
            field=models.CharField(
                choices=[
                    ('pending', 'Pendiente'),
                    ('completed', 'Completada'),
                    ('cancelada', 'Cancelada'),
                ],
                default='pending',
                max_length=20,
            ),
        ),
        migrations.RunPython(migrar_in_progress_a_pending, migrations.RunPython.noop),
    ]
