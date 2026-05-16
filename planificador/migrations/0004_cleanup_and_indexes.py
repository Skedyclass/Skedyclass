from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('planificador', '0003_google_calendar'),
    ]

    operations = [
        # Eliminar FKs no usadas de Clase
        migrations.RemoveField(
            model_name='clase',
            name='profesor',
        ),
        migrations.RemoveField(
            model_name='clase',
            name='grado',
        ),
        # Índices en campos de búsqueda frecuente
        migrations.AlterField(
            model_name='clase',
            name='titulo',
            field=models.CharField(db_index=True, max_length=200),
        ),
        migrations.AlterField(
            model_name='clase',
            name='materia',
            field=models.CharField(
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
                db_index=True,
                max_length=50,
            ),
        ),
        migrations.AlterField(
            model_name='profesor',
            name='nombre',
            field=models.CharField(db_index=True, max_length=100),
        ),
        migrations.AlterField(
            model_name='profesor',
            name='email',
            field=models.EmailField(max_length=254, unique=True),
        ),
        migrations.AlterField(
            model_name='estudiante',
            name='nombre',
            field=models.CharField(db_index=True, max_length=100),
        ),
        migrations.AlterField(
            model_name='estudiante',
            name='email',
            field=models.EmailField(max_length=254, unique=True),
        ),
        # Cambiar SET_NULL → PROTECT en Estudiante.grado
        migrations.AlterField(
            model_name='estudiante',
            name='grado',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to='planificador.grado',
            ),
        ),
        # Unicidad en Grado.nombre para evitar duplicados
        migrations.AlterField(
            model_name='grado',
            name='nombre',
            field=models.CharField(max_length=50, unique=True),
        ),
    ]
