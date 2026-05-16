from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('planificador', '0013_refactor_horario_curso'),
    ]

    operations = [
        migrations.AddField(
            model_name='clase',
            name='google_event_id',
            field=models.CharField(blank=True, default='', max_length=300),
        ),
    ]
