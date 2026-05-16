import re

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.utils import timezone

from .models import MATERIA_CHOICES, Clase, Curso, Grado, Recurso

# Full grade catalogue used in registration and preference settings
NIVEL_ACADEMICO_CHOICES = [
    # Educacion Primaria
    ('1ro Primaria', '1ro Primaria'),
    ('2do Primaria', '2do Primaria'),
    ('3ro Primaria', '3ro Primaria'),
    ('4to Primaria', '4to Primaria'),
    ('5to Primaria', '5to Primaria'),
    ('6to Primaria', '6to Primaria'),
    # Educacion Basica Secundaria
    ('7mo Basica', '7mo Basica'),
    ('8vo Basica', '8vo Basica'),
    ('9no Basica', '9no Basica'),
    # Educacion Media
    ('10mo Media', '10mo Media'),
    ('11no Media', '11no Media'),
]

# Kept for backward compatibility with ClaseForm grado_nombre field
GRADO_CHOICES = [('', 'Selecciona un nivel')] + NIVEL_ACADEMICO_CHOICES

CALENDAR_ID_RE = re.compile(r'^[\w._%+\-]+@([\w\-]+\.)+[\w]{2,}$')


class RegistroForm(UserCreationForm):
    nombre = forms.CharField(
        max_length=150,
        label='Nombre completo',
        widget=forms.TextInput(attrs={
            'placeholder': 'Ej: Maria Garcia',
            'autocomplete': 'name',
        }),
    )
    materia = forms.ChoiceField(
        choices=[('', '— Selecciona tu materia —')] + MATERIA_CHOICES,
        label='Materia principal que impartes',
    )
    grados = forms.MultipleChoiceField(
        choices=NIVEL_ACADEMICO_CHOICES,
        label='Niveles que impartes',
        widget=forms.CheckboxSelectMultiple(),
        help_text='Selecciona uno o mas niveles academicos.',
    )

    class Meta:
        model = User
        fields = ['nombre', 'username', 'materia', 'grados', 'password1', 'password2']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs['placeholder'] = 'Ej: mgarcia'
        self.fields['password1'].widget.attrs['placeholder'] = 'Minimo 8 caracteres'
        self.fields['password2'].widget.attrs['placeholder'] = 'Repite la contrasena'
        self.order_fields(['nombre', 'username', 'materia', 'grados', 'password1', 'password2'])

    def clean_nombre(self):
        nombre = self.cleaned_data['nombre'].strip()
        if not nombre:
            raise forms.ValidationError('El nombre es obligatorio.')
        if any(c.isdigit() for c in nombre):
            raise forms.ValidationError('El nombre no debe contener numeros.')
        return nombre

    def clean_materia(self):
        materia = self.cleaned_data.get('materia', '').strip()
        if not materia:
            raise forms.ValidationError('Selecciona una materia.')
        return materia

    def clean_grados(self):
        grados = self.cleaned_data.get('grados', [])
        if not grados:
            raise forms.ValidationError('Selecciona al menos un nivel.')
        return grados

    def clean_username(self):
        username = self.cleaned_data.get('username', '').strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError('Este nombre de usuario ya está en uso.')
        return username


class ClaseForm(forms.ModelForm):
    grado_nombre = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
    )

    class Meta:
        model = Clase
        fields = ['titulo', 'tipo_clase', 'profesor_nombre', 'grado_nombre', 'fecha', 'hora', 'estado', 'objetivos', 'notas']
        widgets = {
            'titulo': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Ej: Suma y Resta'}),
            'profesor_nombre': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Nombre del profesor'}),
            'fecha': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'hora': forms.TimeInput(attrs={'class': 'form-input', 'type': 'time'}),
            'estado': forms.Select(attrs={'class': 'form-select'}),
            'objetivos': forms.Textarea(attrs={'class': 'form-input', 'rows': 3, 'placeholder': '¿Que aprendera el estudiante al terminar la sesion?'}),
            'notas': forms.Textarea(attrs={'class': 'form-input', 'rows': 5, 'placeholder': 'Materiales, distribucion de tiempo, recordatorios...'}),
        }

    def clean_fecha(self):
        fecha = self.cleaned_data['fecha']
        if fecha.weekday() >= 5:
            raise forms.ValidationError('No se pueden programar clases en fines de semana (sabado o domingo).')
        if fecha < timezone.now().date():
            raise forms.ValidationError('La fecha no puede ser anterior a hoy.')
        return fecha

    def clean(self):
        cleaned = super().clean()
        fecha = cleaned.get('fecha')
        hora = cleaned.get('hora')
        if fecha and hora and fecha == timezone.now().date():
            if hora <= timezone.localtime().time():
                raise forms.ValidationError({
                    'hora': 'La hora ya pasó. Elige una hora futura para una clase de hoy.'
                })
        return cleaned

    def clean_titulo(self):
        return (self.cleaned_data.get('titulo') or '').strip()[:200]

    def clean_objetivos(self):
        return (self.cleaned_data.get('objetivos') or '').strip()[:5000]

    def clean_notas(self):
        return (self.cleaned_data.get('notas') or '').strip()[:10000]

    def clean_profesor_nombre(self):
        return (self.cleaned_data.get('profesor_nombre') or '').strip()[:100]


class CursoForm(forms.ModelForm):
    nivel_academico = forms.ChoiceField(
        choices=[],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    def __init__(self, *args, user_grados=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user_grados is not None and len(user_grados) > 0:
            choices = [('', 'Selecciona un nivel')] + [(g.nombre, g.nombre) for g in user_grados]
        else:
            choices = [('', 'Selecciona un nivel')] + NIVEL_ACADEMICO_CHOICES
        self.fields['nivel_academico'].choices = choices

    class Meta:
        model = Curso
        fields = ['nombre', 'nivel_academico', 'anio']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Ej: 9no A, 10mo B'}),
            'anio': forms.NumberInput(attrs={'class': 'form-input', 'min': 2020, 'max': 2035}),
        }

    def clean_anio(self):
        anio = self.cleaned_data.get('anio')
        if anio is not None and (anio < 2020 or anio > 2035):
            raise forms.ValidationError('El año debe estar entre 2020 y 2035.')
        return anio

    def clean_nombre(self):
        nombre = (self.cleaned_data.get('nombre') or '').strip()
        if not nombre:
            raise forms.ValidationError('El nombre del curso es obligatorio.')
        return nombre


class RecursoForm(forms.ModelForm):
    class Meta:
        model = Recurso
        fields = ['titulo', 'tipo', 'descripcion', 'archivo', 'url_video']
        widgets = {
            'titulo': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Nombre del recurso'}),
            'tipo': forms.Select(attrs={'class': 'form-select'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-input', 'rows': 2, 'placeholder': 'Descripcion opcional...'}),
            'archivo': forms.FileInput(attrs={'class': 'form-input', 'accept': '.pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.png,.jpg,.jpeg,.gif,.mp4,.zip'}),
            'url_video': forms.URLInput(attrs={'class': 'form-input', 'placeholder': 'https://youtube.com/watch?v=...'}),
        }

    def clean_titulo(self):
        titulo = (self.cleaned_data.get('titulo') or '').strip()[:200]
        if not titulo:
            raise forms.ValidationError('El título es obligatorio.')
        return titulo

    def clean_descripcion(self):
        return (self.cleaned_data.get('descripcion') or '').strip()[:5000]

    # Server-side whitelist. Extensions like .html, .svg, .js are dangerous because
    # they can carry inline JS and, when served from /media/, execute in the site's
    # origin → stored XSS. Keep this list narrow; reject everything else.
    ALLOWED_EXTENSIONS = (
        '.pdf', '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx',
        '.png', '.jpg', '.jpeg', '.gif', '.webp',
        '.mp4', '.mp3', '.wav',
        '.zip', '.txt', '.csv',
    )
    MAX_ARCHIVO_SIZE = 16 * 1024 * 1024  # 16 MB

    def clean_archivo(self):
        archivo = self.cleaned_data.get('archivo')
        if not archivo:
            return archivo
        if hasattr(archivo, 'size') and archivo.size > self.MAX_ARCHIVO_SIZE:
            raise forms.ValidationError('El archivo supera el tamaño máximo (16 MB).')
        name = (getattr(archivo, 'name', '') or '').lower()
        if not any(name.endswith(ext) for ext in self.ALLOWED_EXTENSIONS):
            raise forms.ValidationError(
                'Tipo de archivo no permitido. Usa PDF, Office, imagen, audio, video, ZIP, TXT o CSV.'
            )
        # Block dangerous double extensions like .html.pdf or .pdf.exe
        bare = name.rsplit('/', 1)[-1]
        suspicious = ('.html', '.htm', '.svg', '.js', '.exe', '.bat', '.sh', '.php', '.py')
        for s in suspicious:
            if s + '.' in bare:
                raise forms.ValidationError(
                    'El nombre del archivo contiene una extensión sospechosa. Renómbralo.'
                )
        return archivo
