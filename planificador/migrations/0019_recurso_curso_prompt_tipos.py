from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('planificador', '0018_alter_clase_materia_alter_clase_usuario_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='recurso',
            name='curso',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='recursos',
                to='planificador.curso',
                help_text='Curso/grado asociado — respeta la separación estricta de grupos.',
            ),
        ),
        migrations.AddField(
            model_name='recurso',
            name='prompt_origen',
            field=models.TextField(
                blank=True,
                help_text='Prompt usado para generar el recurso (imágenes IA / guías).',
            ),
        ),
        migrations.AlterField(
            model_name='recurso',
            name='tipo',
            field=models.CharField(
                default='documento',
                max_length=20,
                choices=[
                    ('documento', 'Documento / PDF'),
                    ('video', 'Enlace de Video'),
                    ('imagen', 'Imagen'),
                    ('taller', 'Taller / Actividad'),
                    ('guia', 'Guía Metodológica'),
                    ('imagen_ia', 'Imagen generada por IA'),
                    ('plan_pdf', 'Plan de clase (PDF)'),
                    ('quiz', 'Evaluación Diagnóstica'),
                    ('otro', 'Otro'),
                ],
            ),
        ),
    ]
