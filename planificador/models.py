from datetime import time

from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver


def _default_jornada_inicio():
    return time(6, 0)


def _default_jornada_fin():
    return time(14, 0)

MATERIA_CHOICES = [
    ('Matemáticas', 'Matemáticas'),
    ('Lenguaje', 'Lenguaje'),
    ('Ciencias Naturales', 'Ciencias Naturales'),
    ('Ciencias Sociales', 'Ciencias Sociales'),
    ('Educación Física', 'Educación Física'),
    ('Artes', 'Artes'),
    ('Música', 'Música'),
    ('Inglés', 'Inglés'),
]

class Grado(models.Model):
    nombre = models.CharField(max_length=50, unique=True)
    descripcion = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Grado'
        verbose_name_plural = 'Grados'

    def __str__(self):
        return self.nombre


class Curso(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='cursos')
    nombre = models.CharField(max_length=200)
    nivel_academico = models.CharField(max_length=100, blank=True)
    materia = models.CharField(max_length=50, choices=MATERIA_CHOICES, blank=True)
    anio = models.IntegerField(default=2026)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Curso'
        verbose_name_plural = 'Cursos'
        ordering = ['-fecha_creacion']
        constraints = [
            models.UniqueConstraint(
                fields=['usuario', 'nombre'],
                name='curso_unique_per_user',
            ),
        ]

    def __str__(self):
        return f"{self.nombre} ({self.nivel_academico})" if self.nivel_academico else self.nombre


class Clase(models.Model):
    ESTADO_CHOICES = [
        ('pending', 'Pendiente'),
        ('in_progress', 'En Progreso'),
        ('completed', 'Completada'),
    ]
    TIPO_CHOICES = [
        ('normal', 'Normal'),
        ('dinamica', 'Dinámica'),
        ('mixta', 'Mixta'),
    ]

    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='clases')
    titulo = models.CharField(max_length=200, db_index=True)
    materia = models.CharField(max_length=50, choices=MATERIA_CHOICES, blank=True, db_index=True)
    profesor_nombre = models.CharField(max_length=100, blank=True)
    grado_nombre = models.CharField(max_length=50, blank=True)
    fecha = models.DateField()
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField(null=True, blank=True)
    tipo_clase = models.CharField(max_length=20, choices=TIPO_CHOICES, default='normal')
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='pending')
    objetivos = models.TextField(blank=True)
    notas = models.TextField(blank=True)
    google_event_id = models.CharField(max_length=300, blank=True, default='')
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Clase'
        verbose_name_plural = 'Clases'
        ordering = ['-fecha', '-hora_inicio']
        indexes = [
            models.Index(fields=['usuario', 'fecha']),
            models.Index(fields=['usuario', 'estado']),
        ]

    def __str__(self):
        return f"{self.titulo} - {self.materia}"

    def get_estado_emoji(self):
        return {'pending': '⏰', 'in_progress': '🔵', 'completed': '✅'}.get(self.estado, '')

    def get_estado_display_spanish(self):
        return {'pending': 'Pendiente', 'in_progress': 'En progreso', 'completed': 'Completada'}.get(self.estado, self.estado)


class Nota(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='notas')
    titulo = models.CharField(max_length=200)
    contenido = models.TextField()
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Nota'
        verbose_name_plural = 'Notas'
        ordering = ['-fecha_creacion']

    def __str__(self):
        return self.titulo


class ConfiguracionUsuario(models.Model):
    TEMAS = [('light', 'Claro'), ('dark', 'Oscuro')]
    COLORES = [
        ('default', 'Morado'),
        ('blue', 'Azul'),
        ('green', 'Verde'),
        ('orange', 'Naranja'),
        ('pink', 'Rosa'),
    ]

    usuario = models.OneToOneField(User, on_delete=models.CASCADE, related_name='configuracion')
    materia = models.CharField(max_length=50, choices=MATERIA_CHOICES, blank=True)
    grados = models.ManyToManyField(Grado, blank=True, related_name='usuarios')
    idioma = models.CharField(max_length=10, default='es')
    # Notification preferences (UI toggles in Ajustes); honored by future digest jobs
    notif_clases = models.BooleanField(default=True)
    notif_tareas = models.BooleanField(default=True)
    notif_resumen = models.BooleanField(default=False)
    recibir_recordatorio_email = models.BooleanField(default=False)
    hora_recordatorio_preferida = models.TimeField(default=time(6, 0))
    ultimo_recordatorio_enviado = models.DateField(null=True, blank=True)
    nombre_institucion = models.CharField(max_length=200, blank=True)
    cargo = models.CharField(max_length=100, blank=True)
    google_calendar_id = models.CharField(max_length=300, blank=True)
    tema = models.CharField(max_length=10, choices=TEMAS, default='dark')
    color_scheme = models.CharField(max_length=20, choices=COLORES, default='default')

    class Meta:
        verbose_name = 'Configuracion de Usuario'

    def __str__(self):
        return f'Config de {self.usuario.username}'

    def grados_display(self):
        return ', '.join(g.nombre for g in self.grados.all()) or '—'


def _recurso_upload_path(instance, filename):
    """Storage path namespaceado por usuario para evitar mezcla de archivos
    entre docentes y facilitar auditoría forense.
    Resultado: recursos/u<user_id>/YYYY/MM/<filename>
    """
    import datetime as _dt
    uid = instance.usuario_id or 0
    now = _dt.datetime.now()
    return f'recursos/u{uid}/{now.year:04d}/{now.month:02d}/{filename}'


class Recurso(models.Model):
    TIPO_CHOICES = [
        ('documento', 'Documento / PDF'),
        ('video', 'Enlace de Video'),
        ('imagen', 'Imagen'),
        ('taller', 'Taller / Actividad'),
        ('guia', 'Guía Metodológica'),
        ('imagen_ia', 'Imagen generada por IA'),
        ('plan_pdf', 'Plan de clase (PDF)'),
        ('quiz', 'Evaluación Diagnóstica'),
        ('otro', 'Otro'),
    ]

    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='recursos')
    clase = models.ForeignKey(Clase, on_delete=models.SET_NULL, null=True, blank=True, related_name='recursos')
    curso = models.ForeignKey(
        Curso, on_delete=models.SET_NULL, null=True, blank=True, related_name='recursos',
        help_text='Curso/grado asociado — respeta la separación estricta de grupos.'
    )
    titulo = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default='documento')
    archivo = models.FileField(upload_to=_recurso_upload_path, blank=True, null=True)
    url_video = models.URLField(max_length=500, blank=True)
    prompt_origen = models.TextField(
        blank=True,
        help_text='Prompt usado para generar el recurso (imágenes IA / guías).'
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Recurso'
        verbose_name_plural = 'Recursos'
        ordering = ['-fecha_creacion']

    def __str__(self):
        return f'{self.titulo} ({self.get_tipo_display()})'

    def nombre_archivo(self):
        if self.archivo:
            return self.archivo.name.split('/')[-1]
        return ''

    def extension(self):
        name = self.nombre_archivo()
        return name.rsplit('.', 1)[-1].lower() if '.' in name else ''

    def descarga_filename(self):
        """Construye un nombre limpio para la descarga forzada:
        Recurso_<Tipo>_<Curso>_<Tema>.<ext>
        """
        import re
        tipo_map = {
            'guia': 'Guia',
            'imagen_ia': 'Imagen',
            'plan_pdf': 'PlanClase',
            'documento': 'Documento',
            'taller': 'Taller',
            'imagen': 'Imagen',
            'quiz': 'Evaluacion',
            'video': 'Video',
            'otro': 'Recurso',
        }
        tipo_lbl = tipo_map.get(self.tipo, 'Recurso')
        curso_lbl = ''
        if self.curso:
            curso_lbl = (self.curso.nivel_academico or self.curso.nombre or '').strip()
        elif self.clase and self.clase.grado_nombre:
            curso_lbl = self.clase.grado_nombre
        tema = (self.titulo or 'recurso').strip()

        def _slug(s):
            s = re.sub(r'[^A-Za-zÁÉÍÓÚáéíóúÑñ0-9]+', '_', s).strip('_')
            return s or 'sin_titulo'

        partes = ['Recurso', tipo_lbl]
        if curso_lbl:
            partes.append(_slug(curso_lbl))
        partes.append(_slug(tema))
        ext = self.extension() or ('pdf' if self.tipo in ('guia', 'plan_pdf', 'documento', 'taller') else 'png')
        # Sufijo con el ID del recurso para garantizar unicidad en el nombre
        # que ve el docente al descargar — dos recursos con mismo título/grado
        # ya no se confunden como "archivo (1).pdf" en la bandeja del navegador.
        base = '_'.join(partes)[:110]
        return f'{base}_{self.id}.{ext}'


class HorarioAcademico(models.Model):
    """Weekly schedule frame for a teacher (one per user)."""
    usuario = models.OneToOneField(User, on_delete=models.CASCADE, related_name='horario_academico')
    hora_inicio_jornada = models.TimeField(default=_default_jornada_inicio)
    hora_fin_jornada = models.TimeField(default=_default_jornada_fin)
    duracion_sesion = models.PositiveSmallIntegerField(default=60, help_text='Minutos por sesión')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Horario Académico'

    def __str__(self):
        return f'Horario de {self.usuario.username}'


class BloqueDescanso(models.Model):
    """A break block within the academic schedule."""
    horario = models.ForeignKey(HorarioAcademico, on_delete=models.CASCADE, related_name='descansos')
    nombre = models.CharField(max_length=100)
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()

    class Meta:
        verbose_name = 'Bloque de Descanso'
        verbose_name_plural = 'Bloques de Descanso'
        ordering = ['hora_inicio']

    def __str__(self):
        return f'{self.nombre} ({self.hora_inicio}–{self.hora_fin})'


@receiver(post_save, sender=User)
def crear_configuracion_usuario(sender, instance, created, **kwargs):
    if created:
        ConfiguracionUsuario.objects.get_or_create(usuario=instance)


@receiver(pre_delete, sender=Recurso)
def limpiar_archivo_recurso(sender, instance, **kwargs):
    """Borra el blob físico cuando se elimina un Recurso por cualquier vía
    (cascada del User, queryset.delete(), admin, comandos de gestión).
    El controlador `eliminar_recurso` ya lo hace explícitamente; este signal
    cubre los casos que pasan por debajo: borrado en cascada y bulk operations.
    Errores en el storage NO bloquean el borrado de la fila — solo se loguean."""
    if instance.archivo:
        try:
            instance.archivo.delete(save=False)
        except Exception:
            # Storage falló o el archivo ya no existía: no bloqueamos el borrado.
            import logging as _logging
            _logging.getLogger('planificador').warning(
                'No se pudo borrar el archivo físico del Recurso id=%s', instance.pk,
            )
