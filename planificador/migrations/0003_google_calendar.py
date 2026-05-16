from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('planificador', '0002_configuracionusuario'),
    ]
    operations = [
        migrations.AddField(
            model_name='configuracionusuario',
            name='google_calendar_id',
            field=models.CharField(blank=True, max_length=300, help_text='ID o URL embed de Google Calendar'),
        ),
    ]
