from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('planificador', '0004_cleanup_and_indexes'),
    ]

    operations = [
        migrations.AddField(
            model_name='configuracionusuario',
            name='tema',
            field=models.CharField(
                choices=[('light', 'Claro'), ('dark', 'Oscuro')],
                default='light',
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name='configuracionusuario',
            name='color_scheme',
            field=models.CharField(
                choices=[
                    ('default', 'Morado'),
                    ('blue', 'Azul'),
                    ('green', 'Verde'),
                    ('orange', 'Naranja'),
                    ('pink', 'Rosa'),
                ],
                default='default',
                max_length=20,
            ),
        ),
    ]
