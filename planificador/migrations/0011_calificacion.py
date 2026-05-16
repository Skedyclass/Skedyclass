import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('planificador', '0010_curso_estudiante_recurso_clase'),
    ]

    operations = [
        migrations.AddField(
            model_name='estudiante',
            name='email_acudiente',
            field=models.EmailField(blank=True, default='', max_length=254),
        ),
        migrations.CreateModel(
            name='Calificacion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('periodo', models.CharField(
                    choices=[('P1', 'Período 1'), ('P2', 'Período 2'), ('P3', 'Período 3'), ('P4', 'Período 4'), ('Final', 'Final')],
                    default='P1',
                    max_length=10,
                )),
                ('nota', models.DecimalField(
                    decimal_places=1,
                    max_digits=3,
                    validators=[
                        django.core.validators.MinValueValidator(0.0),
                        django.core.validators.MaxValueValidator(5.0),
                    ],
                )),
                ('observacion', models.TextField(blank=True)),
                ('alerta_enviada', models.BooleanField(default=False)),
                ('fecha', models.DateField(auto_now_add=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('clase', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='calificaciones',
                    to='planificador.clase',
                )),
                ('curso', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='calificaciones',
                    to='planificador.curso',
                )),
                ('estudiante', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='calificaciones',
                    to='planificador.estudiante',
                )),
            ],
            options={
                'verbose_name': 'Calificación',
                'verbose_name_plural': 'Calificaciones',
                'ordering': ['-created_at'],
            },
        ),
    ]
