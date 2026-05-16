from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('planificador', '0006_ownership_and_timestamps'),
    ]

    operations = [
        # Eliminar modelo Profesor (ya no tiene FKs desde la migración 0004)
        migrations.DeleteModel(
            name='Profesor',
        ),
        # Agregar materia al perfil del usuario
        migrations.AddField(
            model_name='configuracionusuario',
            name='materia',
            field=models.CharField(
                blank=True,
                choices=[
                    ('Matemáticas', 'Matemáticas'),
                    ('Lenguaje', 'Lenguaje'),
                    ('Ciencias Naturales', 'Ciencias Naturales'),
                    ('Ciencias Sociales', 'Ciencias Sociales'),
                    ('Educación Física', 'Educación Física'),
                    ('Artes', 'Artes'),
                    ('Música', 'Música'),
                    ('Inglés', 'Inglés'),
                ],
                max_length=50,
            ),
        ),
        # Relación M2M: usuario ↔ grados que imparte
        migrations.AddField(
            model_name='configuracionusuario',
            name='grados',
            field=models.ManyToManyField(
                blank=True,
                related_name='usuarios',
                to='planificador.grado',
            ),
        ),
    ]
