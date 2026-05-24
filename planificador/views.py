import calendar
import json
import logging
from datetime import date, timedelta
from functools import wraps

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import CALENDAR_ID_RE, NIVEL_ACADEMICO_CHOICES, ClaseForm, CursoForm, RecursoForm, RegistroForm
from .models import BloqueDescanso, Clase, ConfiguracionUsuario, Curso, Grado, HorarioAcademico, MATERIA_CHOICES, Nota, Recurso

logger = logging.getLogger('planificador')

ESTADOS_VALIDOS = ('pending', 'in_progress', 'completed')
POR_PAGINA = 10


# ---------------------------------------------------------------------------
# Security helpers
# ---------------------------------------------------------------------------

def _client_ip(request):
    """Best-effort client IP — used as rate-limit key for anonymous users."""
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
    return xff or request.META.get('REMOTE_ADDR', 'unknown')


def rate_limit(key_prefix, max_calls=10, window_sec=60, json_response=True):
    """Per-user (or per-IP) rate limit. Stores counter in Django cache.
    Returns 429 once the bucket is full."""
    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            uid = (
                f'u{request.user.id}' if request.user.is_authenticated
                else f'ip{_client_ip(request)}'
            )
            cache_key = f'rl:{key_prefix}:{uid}'
            count = cache.get(cache_key, 0)
            if count >= max_calls:
                msg = 'Demasiadas peticiones. Espera unos segundos e intenta de nuevo.'
                if json_response:
                    return JsonResponse({'ok': False, 'error': msg}, status=429)
                messages.warning(request, msg)
                return redirect(request.META.get('HTTP_REFERER', 'dashboard'))
            cache.set(cache_key, count + 1, window_sec)
            return view(request, *args, **kwargs)
        return wrapper
    return decorator


def _safe_redirect(request, candidate, fallback):
    """Open-redirect-safe redirect helper. Falls back if the URL is external."""
    if candidate and url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(candidate)
    return redirect(fallback)


_FILE_MAGIC = {
    'pdf':  (b'%PDF-',),
    'jpg':  (b'\xff\xd8\xff',),
    'jpeg': (b'\xff\xd8\xff',),
    'png':  (b'\x89PNG\r\n\x1a\n',),
    'webp': (b'RIFF',),  # also requires 'WEBP' at bytes 8-12
}


def _validate_magic(file_bytes, expected_kind):
    """Returns True if file_bytes start with one of the expected magic-byte
    signatures for the given kind (pdf/jpg/png/webp)."""
    signatures = _FILE_MAGIC.get(expected_kind, ())
    if not signatures:
        return False
    if not any(file_bytes.startswith(sig) for sig in signatures):
        return False
    if expected_kind == 'webp':
        # WEBP requires RIFF header + 'WEBP' marker at offset 8
        return len(file_bytes) >= 12 and file_bytes[8:12] == b'WEBP'
    return True

MESES_ES = ['', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
            'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']

DIAS_ES = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']

# Map Python weekday() (0=Mon) to DIA_CHOICES keys
_WEEKDAY_TO_DIA = {
    0: 'lunes',
    1: 'martes',
    2: 'miercoles',
    3: 'jueves',
    4: 'viernes',
}

PLANTILLAS_CLASE = [
    {
        'tipo': 'normal',
        'nombre': 'Clase Normal',
        'icono': '📋',
        'color': 'indigo',
        'descripcion': 'Estructura tradicional: exposición, práctica y cierre.',
        'badges': ['⏱️ Cronometraje', '📚 Material de apoyo', '✅ Evaluación final'],
        'secciones': [
            {'titulo': 'Objetivo de Aprendizaje', 'icono': '🎯', 'placeholder': 'Describe qué aprenderán los estudiantes...'},
            {'titulo': 'Contenidos', 'icono': '📖', 'placeholder': '1.\n2.\n3.'},
            {'titulo': 'Distribución de Tiempo', 'icono': '⏱️', 'placeholder': 'Inicio: 10 min · Desarrollo: 25 min · Práctica: 15 min · Cierre: 10 min'},
            {'titulo': 'Materiales', 'icono': '📝', 'placeholder': 'Lista de materiales necesarios...'},
            {'titulo': 'Evaluación', 'icono': '✅', 'placeholder': 'Criterios de evaluación...'},
        ],
    },
    {
        'tipo': 'dinamica',
        'nombre': 'Clase Dinámica',
        'icono': '⚡',
        'color': 'pink',
        'descripcion': 'Actividades interactivas, juegos y trabajo en equipo.',
        'badges': ['👥 Grupos', '🎮 Actividad lúdica', '🏆 Rúbrica participación'],
        'secciones': [
            {'titulo': 'Objetivo de Aprendizaje', 'icono': '🎯', 'placeholder': 'Describe el objetivo de la actividad...'},
            {'titulo': 'Actividad Principal', 'icono': '🎮', 'placeholder': 'Nombre y descripción de la actividad...'},
            {'titulo': 'Organización de Grupos', 'icono': '👥', 'placeholder': 'Nº grupos · Roles · Reglas...'},
            {'titulo': 'Distribución de Tiempo', 'icono': '⏱️', 'placeholder': 'Bienvenida: 5 min · Act. 1: 20 min · Act. 2: 20 min · Cierre: 15 min'},
            {'titulo': 'Recursos y Materiales', 'icono': '🧰', 'placeholder': 'Lista de materiales y recursos...'},
            {'titulo': 'Rúbrica de Participación', 'icono': '🏆', 'placeholder': 'Criterios de evaluación...'},
        ],
    },
    {
        'tipo': 'mixta',
        'nombre': 'Clase Mixta',
        'icono': '🔀',
        'color': 'green',
        'descripcion': 'Combina exposición teórica con actividades prácticas.',
        'badges': ['📚 Teoría', '🎮 Taller práctico', '✅ Evaluación integradora'],
        'secciones': [
            {'titulo': 'Objetivo de Aprendizaje', 'icono': '🎯', 'placeholder': 'Describe el objetivo...'},
            {'titulo': 'Bloque Teórico (20 min)', 'icono': '📚', 'placeholder': 'Tema · Puntos clave · Recursos...'},
            {'titulo': 'Bloque Práctico (30 min)', 'icono': '🎮', 'placeholder': 'Actividad · Instrucciones...'},
            {'titulo': 'Distribución de Tiempo', 'icono': '⏱️', 'placeholder': 'Motivación: 5 min · Teoría: 20 min · Práctica: 30 min · Reflexión: 5 min'},
            {'titulo': 'Materiales', 'icono': '📝', 'placeholder': 'Lista de materiales...'},
            {'titulo': 'Evaluación', 'icono': '✅', 'placeholder': 'Criterios de evaluación...'},
        ],
    },
]


def _parse_time(val, default):
    from datetime import datetime as _dt
    try:
        return _dt.strptime(val, '%H:%M').time()
    except (ValueError, TypeError):
        return default


def _session_duration_min(user):
    try:
        return user.horario_academico.duracion_sesion or 60
    except Exception:
        return 60


def _validar_clase_horario(user, fecha, hora, exclude_pk=None):
    """Check schedule rules: jornada bounds, session end fits, break overlap,
    and time-range overlap with other classes. Returns (ok, error_message)."""
    from datetime import datetime as _dt, timedelta as _td
    try:
        horario_obj = user.horario_academico
    except Exception:
        horario_obj = None

    sess_min = _session_duration_min(user)
    new_start_dt = _dt.combine(fecha, hora)
    new_end_dt = new_start_dt + _td(minutes=sess_min)

    if horario_obj:
        if hora < horario_obj.hora_inicio_jornada or hora >= horario_obj.hora_fin_jornada:
            return False, (
                f'La hora debe estar dentro de la jornada '
                f'({horario_obj.hora_inicio_jornada.strftime("%H:%M")}–'
                f'{horario_obj.hora_fin_jornada.strftime("%H:%M")}).'
            )
        jornada_fin_dt = _dt.combine(fecha, horario_obj.hora_fin_jornada)
        if new_end_dt > jornada_fin_dt:
            return False, (
                f'La clase ({sess_min} min) terminaría a las '
                f'{new_end_dt.strftime("%H:%M")}, después del fin de jornada '
                f'({horario_obj.hora_fin_jornada.strftime("%H:%M")}).'
            )
        for bloque in horario_obj.descansos.all():
            b_start = _dt.combine(fecha, bloque.hora_inicio)
            b_end = _dt.combine(fecha, bloque.hora_fin)
            if new_start_dt < b_end and b_start < new_end_dt:
                return False, f'La clase se cruza con el bloque de descanso "{bloque.nombre}".'

    # Lock this user's classes for the day so two near-simultaneous submits
    # can't both pass the overlap check (no-op on SQLite dev, real row lock on
    # Postgres prod). Always called inside a transaction.atomic() block.
    qs = Clase.objects.select_for_update().filter(usuario=user, fecha=fecha)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    for other in qs:
        o_start = _dt.combine(other.fecha, other.hora_inicio)
        o_end = o_start + _td(minutes=sess_min)
        if new_start_dt < o_end and o_start < new_end_dt:
            return False, (
                f'Se solapa con la clase "{other.titulo}" a las '
                f'{other.hora_inicio.strftime("%H:%M")}.'
            )
    return True, None


def _strip_json_fences(raw):
    raw = (raw or '').strip()
    if raw.startswith('```'):
        parts = raw.split('```')
        if len(parts) >= 2:
            raw = parts[1]
            if raw.startswith('json'):
                raw = raw[4:]
            raw = raw.strip()
    return raw


def _groq_generate(system_prompt, user_prompt, max_tokens, temperature=0.7):
    import json as _json
    from django.conf import settings as _settings

    api_key = _settings.GROQ_API_KEY
    if not api_key or api_key == 'TU_API_KEY_AQUI':
        return False, {'error': 'GROQ_API_KEY no configurada en .env. Obtén una gratis en console.groq.com/keys'}, 503

    try:
        from groq import Groq, AuthenticationError, RateLimitError, BadRequestError, APIConnectionError
        # APITimeoutError no existe en todas las versiones del SDK; fallback a TimeoutError
        try:
            from groq import APITimeoutError as _GroqTimeoutError
        except ImportError:
            _GroqTimeoutError = TimeoutError
    except ImportError:
        return False, {'error': 'Falta instalar groq: pip install groq'}, 500

    raw = ''
    try:
        # Timeout duro: si el proveedor cuelga, el worker queda libre en 60s
        # en lugar de bloquearse indefinidamente bajo carga.
        client = Groq(api_key=api_key, timeout=60.0)
        resp = client.chat.completions.create(
            model=_settings.GROQ_MODEL,
            max_tokens=max_tokens,
            temperature=temperature,
            response_format={'type': 'json_object'},
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ],
        )
        raw = _strip_json_fences(resp.choices[0].message.content)
        return True, _json.loads(raw), 200
    except _json.JSONDecodeError as e:
        logger.warning('Groq devolvió JSON inválido: %s | raw=%s', e, raw[:300])
        return False, {'error': 'La IA devolvió una respuesta inválida. Intenta de nuevo.'}, 500
    except AuthenticationError:
        return False, {'error': 'GROQ_API_KEY inválida. Verifica la clave en .env.'}, 401
    except RateLimitError:
        return False, {'error': 'Límite del tier gratuito alcanzado. Espera un minuto e intenta de nuevo.'}, 429
    except BadRequestError as e:
        logger.warning('Groq BadRequest: %s', e)
        return False, {'error': 'Solicitud inválida a la IA. Revisa el contenido enviado.'}, 400
    except APIConnectionError as e:
        logger.warning('Groq APIConnectionError: %s', e)
        return False, {'error': 'Error de conexión con la IA. Intenta de nuevo en unos segundos.'}, 502
    except _GroqTimeoutError:
        logger.warning('Groq timeout: el proveedor no respondió en el plazo')
        return False, {'error': 'La IA tardó demasiado en responder. Intenta de nuevo.'}, 504
    except Exception as e:
        logger.error('Groq error inesperado: %s', e)
        return False, {'error': 'Error inesperado al generar contenido con IA.'}, 500


def _ai_generate(system_prompt, user_prompt, max_tokens, temperature=0.7):
    import json as _json
    from django.conf import settings as _settings

    api_key = _settings.GEMINI_API_KEY
    if not api_key or api_key == 'TU_API_KEY_AQUI':
        return False, {'error': 'GEMINI_API_KEY no configurada en .env. Obtén una gratis en aistudio.google.com/apikey'}, 503

    try:
        import google.generativeai as genai
        from google.api_core import exceptions as _gx
    except ImportError:
        return False, {'error': 'Falta instalar google-generativeai: pip install google-generativeai'}, 500

    raw = ''
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            model_name=_settings.GEMINI_MODEL,
            system_instruction=system_prompt,
            generation_config={
                'max_output_tokens': max_tokens,
                'temperature': temperature,
                'response_mime_type': 'application/json',
            },
        )
        # request_options.timeout libera el worker en 90s si Gemini cuelga.
        # Es generoso porque la guía multipágina puede tardar ~30-45s legítimos.
        resp = model.generate_content(user_prompt, request_options={'timeout': 90})
        raw = _strip_json_fences(resp.text or '')
        return True, _json.loads(raw), 200
    except _json.JSONDecodeError as e:
        logger.warning('Gemini devolvió JSON inválido: %s | raw=%s', e, raw[:300])
        return False, {'error': 'La IA devolvió una respuesta inválida. Intenta de nuevo.'}, 500
    except _gx.Unauthenticated:
        return False, {'error': 'GEMINI_API_KEY inválida. Verifica la clave en .env.'}, 401
    except _gx.ResourceExhausted:
        return False, {'error': 'Límite del tier gratuito alcanzado. Espera un minuto e intenta de nuevo.'}, 429
    except _gx.DeadlineExceeded:
        logger.warning('Gemini timeout: el proveedor no respondió en 90s')
        return False, {'error': 'La IA tardó demasiado en responder. Intenta de nuevo.'}, 504
    except _gx.InvalidArgument as e:
        logger.warning('Gemini InvalidArgument: %s', e)
        return False, {'error': 'Solicitud inválida a la IA. Revisa el contenido enviado.'}, 400
    except Exception as e:
        logger.error('Gemini error inesperado: %s', e)
        return False, {'error': 'Error inesperado al generar contenido con IA.'}, 500


def ai_generate(system_prompt, user_prompt, max_tokens=2048, temperature=0.7):
    """Dispatch to configured AI provider. Returns (ok, payload, http_status)."""
    from django.conf import settings as _settings
    provider = _settings.AI_PROVIDER
    if provider == 'gemini':
        return _ai_generate(system_prompt, user_prompt, max_tokens, temperature)
    return _groq_generate(system_prompt, user_prompt, max_tokens, temperature)


# Backwards-compat alias for old callers
gemini_generate = ai_generate


def get_user_materia(user):
    """Return the teacher's primary subject from their profile config."""
    try:
        return user.configuracion.materia
    except ConfiguracionUsuario.DoesNotExist:
        return ''


# ==================== AUTH ====================

def landing(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'landing.html')


def privacidad(request):
    """Public privacy policy — required by Google OAuth verification."""
    return render(request, 'privacidad.html')


def terminos(request):
    """Public terms of service — required by Google OAuth verification."""
    return render(request, 'terminos.html')


def login_view(request):
    next_url = request.GET.get('next') or request.POST.get('next') or ''

    if request.user.is_authenticated:
        return _safe_redirect(request, next_url, 'dashboard')

    LOGIN_MAX_ATTEMPTS = 5
    LOGIN_WINDOW = 15 * 60  # 15 min lockout window

    error = None
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')

        # Throttle by IP + username to mitigate credential stuffing / brute force
        ip = _client_ip(request)
        ip_key = f'login_attempts:ip:{ip}'
        user_key = f'login_attempts:user:{username.lower()}'
        ip_count = cache.get(ip_key, 0)
        user_count = cache.get(user_key, 0)
        if max(ip_count, user_count) >= LOGIN_MAX_ATTEMPTS:
            logger.warning('Login throttle: ip=%s user=%s attempts=%s/%s',
                           ip, username, ip_count, user_count)
            error = 'Demasiados intentos. Espera 15 minutos antes de volver a intentarlo.'
            return render(request, 'login.html', {'error': error, 'next': next_url})

        user = authenticate(request, username=username, password=password)
        if user is not None:
            cache.delete(ip_key)
            cache.delete(user_key)
            login(request, user)
            messages.success(request, f'¡Bienvenido de vuelta, {user.username}!')
            return _safe_redirect(request, next_url, 'dashboard')
        else:
            cache.set(ip_key, ip_count + 1, LOGIN_WINDOW)
            cache.set(user_key, user_count + 1, LOGIN_WINDOW)
            logger.info('Login fallido: user=%s ip=%s', username, ip)
            error = 'Usuario o contraseña incorrectos'

    return render(request, 'login.html', {'error': error, 'next': next_url})


def logout_view(request):
    logout(request)
    messages.success(request, '¡Hasta pronto!')
    return redirect('login')


def google_login(request):
    """Bridge view: hands off to django-allauth's Google OAuth flow.
    - When the user is authenticated, sends them through ?process=connect so the
      Google account links to their existing user instead of creating a new one.
    - When anonymous, runs the standard login/signup flow."""
    from django.conf import settings as _cfg
    if 'allauth.socialaccount.providers.google' not in getattr(_cfg, 'INSTALLED_APPS', []):
        messages.error(
            request,
            'El inicio de sesión con Google aún no está activado. '
            'Pídele al administrador instalar django-allauth y configurar las credenciales.'
        )
        return redirect('login')
    # Validate that OAuth client credentials are actually present — otherwise
    # allauth raises a 500 mid-flow with a confusing template error.
    prov = _cfg.SOCIALACCOUNT_PROVIDERS.get('google', {}).get('APP', {})
    if not (prov.get('client_id') and prov.get('secret')):
        messages.error(
            request,
            'Google OAuth no está configurado en el servidor. '
            'Falta GOOGLE_OAUTH_CLIENT_ID o GOOGLE_OAUTH_CLIENT_SECRET en el .env.'
        )
        return redirect('login' if not request.user.is_authenticated else '/ajustes/?s=google_calendar')
    base = '/accounts/google/login/'
    if request.user.is_authenticated:
        # Pass next explicitly — allauth >=65 prefers this over SOCIALACCOUNT_CONNECT_REDIRECT_URL
        from urllib.parse import quote as _quote
        next_url = _quote('/ajustes/?s=google_calendar', safe='/')
        return redirect(f'{base}?process=connect&next={next_url}')
    return redirect(base)


# ==================== DASHBOARD ====================

@login_required
def dashboard(request):
    today = timezone.localdate()  # respects TIME_ZONE; avoids UTC drift on cloud servers
    clases_qs = Clase.objects.filter(usuario=request.user)
    stats = clases_qs.aggregate(
        total=Count('id'),
        pending=Count('id', filter=Q(estado='pending')),
        in_progress=Count('id', filter=Q(estado='in_progress')),
        completed=Count('id', filter=Q(estado='completed')),
    )

    # Workload heatmap: carga de trabajo del mes actual
    workload_counts = {}
    workload_titulos = {}     # day -> list of clase titles
    workload_objetivos = {}   # day -> list of (titulo, objetivo)
    workload_minutos = {}     # day -> total minutes
    try:
        sess_min = request.user.horario_academico.duracion_sesion or 60
    except Exception:
        sess_min = 60
    month_clases = clases_qs.filter(
        fecha__year=today.year, fecha__month=today.month
    ).only('fecha', 'titulo', 'objetivos').order_by('fecha', 'hora_inicio')
    for cl in month_clases:
        d = cl.fecha.day
        workload_counts[d] = workload_counts.get(d, 0) + 1
        workload_minutos[d] = workload_minutos.get(d, 0) + sess_min
        workload_titulos.setdefault(d, []).append(cl.titulo)
        # Store only truncated objetivo to avoid loading 200KB+ of text into memory
        obj_truncated = (cl.objetivos or '').strip()[:160]
        if obj_truncated:
            workload_objetivos.setdefault(d, []).append((cl.titulo, obj_truncated))
    max_load = max(workload_counts.values()) if workload_counts else 0
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    dias_semana = ['L', 'M', 'X', 'J', 'V', 'S', 'D']
    first_weekday = date(today.year, today.month, 1).weekday()
    workload_cells = [{'empty': True} for _ in range(first_weekday)]
    for d in range(1, days_in_month + 1):
        count = workload_counts.get(d, 0)
        level = 0
        if max_load > 0 and count > 0:
            ratio = count / max_load
            if ratio >= 0.75:
                level = 4
            elif ratio >= 0.5:
                level = 3
            elif ratio >= 0.25:
                level = 2
            else:
                level = 1
        # Build tooltip-friendly summary
        titulos = workload_titulos.get(d, [])
        objetivos_list = workload_objetivos.get(d, [])
        minutos = workload_minutos.get(d, 0)
        horas_str = f'{minutos // 60}h {minutos % 60:02d}min' if minutos else ''
        # Objetivo summary: first non-empty objective, truncated
        obj_resumen = ''
        for _t, _o in objetivos_list:
            if _o.strip():
                obj_resumen = _o.strip()[:140]
                break
        if not obj_resumen and titulos:
            obj_resumen = 'Temas: ' + ', '.join(titulos[:3])[:140]
        workload_cells.append({
            'day': d,
            'count': count,
            'level': level,
            'is_today': d == today.day,
            'empty': False,
            'horas': horas_str,
            'objetivo': obj_resumen or 'Sin clases programadas',
            'titulos_csv': ', '.join(titulos[:4]),
        })

    dia_hoy = _WEEKDAY_TO_DIA.get(today.weekday())
    # Build a map grado_nombre → earliest upcoming pending class (single query, avoids N+1).
    # Only future/today classes count as "próximas" — past pendings are excluded.
    _pending = clases_qs.filter(
        estado='pending', fecha__gte=today
    ).order_by('fecha', 'hora_inicio').only('id', 'titulo', 'grado_nombre', 'fecha', 'hora_inicio')
    _primera_por_grado = {}
    for _cl in _pending:
        if _cl.grado_nombre and _cl.grado_nombre not in _primera_por_grado:
            _primera_por_grado[_cl.grado_nombre] = _cl
    cursos_hoy = []
    for curso in Curso.objects.filter(usuario=request.user):
        clase_proxima = _primera_por_grado.get(curso.nombre)
        if clase_proxima:
            cursos_hoy.append({
                'curso': curso,
                'clase_proxima': clase_proxima,
            })

    # Próximas clases (siguiente semana)
    proximas = clases_qs.filter(
        fecha__gte=today, estado='pending',
    ).order_by('fecha', 'hora_inicio')[:5]

    context = {
        'stats': stats,
        # Kanban columns: pending/in-progress show the SOONEST classes first
        # (the model default orders by -fecha, so override it here); completed
        # shows the most recently finished first.
        'clases_pending': clases_qs.filter(estado='pending').order_by('fecha', 'hora_inicio')[:5],
        'clases_in_progress': clases_qs.filter(estado='in_progress').order_by('fecha', 'hora_inicio')[:5],
        'clases_completed': clases_qs.filter(estado='completed').order_by('-fecha', '-hora_inicio')[:5],
        'next_class': clases_qs.filter(estado='in_progress').order_by('fecha', 'hora_inicio').first(),
        'user_materia': get_user_materia(request.user),
        'workload_cells': workload_cells,
        'workload_total': sum(workload_counts.values()),
        'workload_max': max_load,
        'workload_peak_day': max(workload_counts, key=workload_counts.get) if workload_counts else None,
        'workload_dias_semana': dias_semana,
        'workload_month_name': MESES_ES[today.month],
        'cursos_hoy': cursos_hoy,
        'dia_hoy_label': dict([
            ('lunes', 'Lunes'), ('martes', 'Martes'), ('miercoles', 'Miércoles'),
            ('jueves', 'Jueves'), ('viernes', 'Viernes'),
        ]).get(dia_hoy, ''),
        'proximas_clases': proximas,
        'page': 'dashboard',
    }
    return render(request, 'index.html', context)


# ==================== CLASES ====================

@login_required
def listar_clases(request):
    q = request.GET.get('q', '').strip()
    clases = Clase.objects.filter(usuario=request.user)
    if q:
        clases = clases.filter(Q(titulo__icontains=q) | Q(materia__icontains=q) | Q(profesor_nombre__icontains=q))

    paginator = Paginator(clases, POR_PAGINA)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'clases/listar.html', {
        'clases': page_obj, 'page_obj': page_obj, 'q': q, 'page': 'clases',
        'today': timezone.localdate(),
    })


@login_required
def crear_clase(request):
    cursos = Curso.objects.filter(usuario=request.user)
    # Block early on BOTH GET and POST: otherwise the teacher fills the whole
    # form and loses it on submit because the class needs a curso.
    if not cursos.exists():
        messages.error(request, 'Primero debes crear un curso antes de planificar una clase.')
        return redirect('crear_curso')
    if request.method == 'POST':
        form = ClaseForm(request.POST)
        if form.is_valid():
            try:
                clase = form.save(commit=False)
                clase.usuario = request.user
                clase.materia = get_user_materia(request.user)

                with transaction.atomic():
                    ok, err = _validar_clase_horario(request.user, clase.fecha, clase.hora_inicio)
                    if not ok:
                        messages.error(request, err)
                        raise ValueError('horario')
                    clase.save()

                # Step 3: attach resource if provided — route through RecursoForm
                # so that extension whitelist, size cap and URL validation run.
                rec_titulo = request.POST.get('rec_titulo', '').strip()
                rec_url = request.POST.get('rec_url', '').strip()
                rec_archivo = request.FILES.get('rec_archivo')

                if rec_titulo and (rec_archivo or rec_url):
                    rec_form = RecursoForm(
                        data={
                            'titulo': rec_titulo,
                            'tipo': request.POST.get('rec_tipo', 'documento'),
                            'descripcion': '',
                            'url_video': rec_url,
                        },
                        files={'archivo': rec_archivo} if rec_archivo else None,
                    )
                    if rec_form.is_valid():
                        recurso = rec_form.save(commit=False)
                        recurso.usuario = request.user
                        recurso.clase = clase
                        recurso.save()
                    else:
                        # Don't abort the class — surface the resource error and continue
                        first_err = next(iter(rec_form.errors.values()), [''])[0]
                        messages.warning(
                            request,
                            f'La clase se guardó pero el recurso adjunto no: {first_err}'
                        )

                logger.info('Clase creada: id=%s "%s" por %s', clase.id, clase.titulo, request.user.username)
                messages.success(request, f'Clase "{clase.titulo}" planificada con éxito.')
                ok, sync_msg = _sync_gcal(clase, 'create', request.user)
                if sync_msg:
                    if ok:
                        messages.success(request, sync_msg)
                    else:
                        messages.warning(request, sync_msg)
                # Honor ?next= for explicit destinations (whitelisted, no open redirects).
                next_url = request.POST.get('next') or request.GET.get('next')
                if next_url in ('dashboard', 'listar_clases', 'planificador'):
                    return redirect(next_url)
                return redirect('ver_clase', id=clase.id)
            except ValueError:
                pass  # message already added above; fall through to re-render
            except IntegrityError:
                messages.error(request, 'Error al guardar la clase. Inténtalo de nuevo.')
        else:
            # Show the FIRST specific error message per field so the user knows what's wrong
            for field, errs in form.errors.items():
                if errs:
                    label = field if field != '__all__' else 'Formulario'
                    messages.error(request, f'{label}: {errs[0]}')
    else:
        initial = {}
        pre_fecha = request.GET.get('fecha', '').strip()
        pre_hora = request.GET.get('hora', '').strip()
        if pre_fecha:
            initial['fecha'] = pre_fecha
        if pre_hora:
            initial['hora_inicio'] = pre_hora
        form = ClaseForm(initial=initial)

    preselected = request.GET.get('tipo', '').strip()
    if preselected not in ('normal', 'dinamica', 'mixta'):
        preselected = ''
    preset_curso = request.GET.get('curso', '').strip()
    plantillas_content = {}
    for p in PLANTILLAS_CLASE:
        obj_sec = next((s for s in p['secciones'] if 'Objetivo' in s['titulo']), None)
        otras = [s for s in p['secciones'] if 'Objetivo' not in s['titulo']]
        plantillas_content[p['tipo']] = {
            'objetivos': (obj_sec['placeholder'] if obj_sec else ''),
            'notas': '\n\n'.join(
                s['titulo'].upper() + ':\n' + s['placeholder'] for s in otras
            ),
        }
    return render(request, 'clases/crear.html', {
        'form': form,
        'form_errors': bool(form.errors),
        'page': 'clases',
        'cursos': cursos,
        'preselected_tipo': preselected,
        'preset_curso': preset_curso,
        'plantillas_json': json.dumps(plantillas_content),
    })


@login_required
def ver_clase(request, id):
    """Vista de detalle (panel de control) de una clase específica.
    Trae la clase + recursos vinculados en una sola consulta optimizada.
    Verifica propiedad estricta: si la clase no pertenece al docente
    autenticado, responde 404 (no revela existencia del recurso ajeno).
    """
    clase = get_object_or_404(
        Clase.objects.prefetch_related('recursos'),
        id=id, usuario=request.user,
    )

    # Reparto pedagógico de los 3 momentos sobre la duración configurada
    duracion_total = _session_duration_min(request.user)
    def _round5(n):
        return int(round(n / 5.0) * 5) or 5
    inicio_min = _round5(duracion_total * 0.20)
    desarrollo_min = _round5(duracion_total * 0.55)
    cierre_min = duracion_total - inicio_min - desarrollo_min

    # Estado temporal: hoy / pasada / futura
    hoy = timezone.localdate()
    if clase.fecha == hoy:
        temporalidad = 'hoy'
    elif clase.fecha < hoy:
        temporalidad = 'pasada'
    else:
        temporalidad = 'futura'

    # Curso asociado a la clase (para vincular recursos)
    curso_relacionado = None
    if clase.grado_nombre:
        curso_relacionado = Curso.objects.filter(
            usuario=request.user, nombre=clase.grado_nombre
        ).first()

    # Recursos del docente que NO están aún enlazados a esta clase
    # (para el selector "Vincular recurso existente")
    recursos_disponibles = Recurso.objects.filter(
        usuario=request.user
    ).exclude(clase=clase).order_by('-fecha_creacion')[:50]

    return render(request, 'clases/ver.html', {
        'page': 'clases',
        'clase': clase,
        'recursos': clase.recursos.all(),
        'recursos_disponibles': recursos_disponibles,
        'curso_relacionado': curso_relacionado,
        'duracion_total': duracion_total,
        'inicio_min': inicio_min,
        'desarrollo_min': desarrollo_min,
        'cierre_min': cierre_min,
        'temporalidad': temporalidad,
        'hoy': hoy,
    })


@login_required
@rate_limit('clase_vincular', max_calls=30, window_sec=60)
def vincular_recurso_clase(request, clase_id):
    """Vincula o desvincula un Recurso a una Clase. Ambos deben pertenecer
    al usuario autenticado. POST con action=link|unlink y recurso_id."""
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Método no permitido'}, status=405)
    clase = get_object_or_404(Clase, id=clase_id, usuario=request.user)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'JSON inválido'}, status=400)

    action = (data.get('action') or 'link').strip()
    try:
        recurso_id = int(data.get('recurso_id'))
    except (TypeError, ValueError):
        return JsonResponse({'ok': False, 'error': 'recurso_id inválido'}, status=400)

    recurso = get_object_or_404(Recurso, id=recurso_id, usuario=request.user)

    if action == 'link':
        recurso.clase = clase
        # Sincroniza el curso del recurso con el grado de la clase para
        # mantener la separación estricta A/B coherente: si la clase es
        # 3°A, el recurso queda asignado al curso de 3°A. Si el grado
        # de la clase no matchea ningún curso del docente, se deja como
        # estaba (no se borra la asociación previa).
        if clase.grado_nombre:
            curso_match = Curso.objects.filter(
                usuario=request.user, nombre=clase.grado_nombre
            ).first()
            if curso_match is not None:
                recurso.curso = curso_match
                recurso.save(update_fields=['clase', 'curso'])
            else:
                recurso.save(update_fields=['clase'])
        else:
            recurso.save(update_fields=['clase'])
    elif action == 'unlink':
        if recurso.clase_id == clase.id:
            recurso.clase = None
            recurso.save(update_fields=['clase'])
        else:
            return JsonResponse({'ok': False, 'error': 'El recurso no está vinculado a esta clase.'}, status=400)
    else:
        return JsonResponse({'ok': False, 'error': 'Acción no válida'}, status=400)

    return JsonResponse({'ok': True, 'recurso_id': recurso.id, 'action': action})


@login_required
def editar_clase(request, id):
    clase = get_object_or_404(Clase, id=id, usuario=request.user)
    # Capture the stored schedule BEFORE the form mutates the instance, so we
    # can tell whether the teacher actually rescheduled the class.
    orig_fecha, orig_hora = clase.fecha, clase.hora_inicio

    if request.method == 'POST':
        form = ClaseForm(request.POST, instance=clase)
        if form.is_valid():
            try:
                updated = form.save(commit=False)

                with transaction.atomic():
                    # Only re-validate jornada / overlap when the class is being
                    # moved. Editing notes/objectives of a past class keeps the
                    # same date & time and must not be blocked.
                    reprogramada = (updated.fecha, updated.hora_inicio) != (orig_fecha, orig_hora)
                    if reprogramada:
                        ok, err = _validar_clase_horario(
                            request.user, updated.fecha, updated.hora_inicio, exclude_pk=clase.pk
                        )
                        if not ok:
                            messages.error(request, err)
                            raise ValueError('horario')
                    updated.save()
                logger.info('Clase editada: id=%s por %s', id, request.user.username)
                messages.success(request, 'Clase actualizada correctamente.')
                ok, sync_msg = _sync_gcal(updated, 'update', request.user)
                if sync_msg:
                    if ok:
                        messages.success(request, sync_msg)
                    else:
                        messages.warning(request, sync_msg)
                return redirect('listar_clases')
            except ValueError:
                pass  # message already added above; fall through to re-render
            except IntegrityError:
                messages.error(request, 'Error al guardar los cambios.')
        else:
            for field, errs in form.errors.items():
                if errs:
                    label = field if field != '__all__' else 'Formulario'
                    messages.error(request, f'{label}: {errs[0]}')
    else:
        form = ClaseForm(instance=clase)

    return render(request, 'clases/editar.html', {'form': form, 'clase': clase, 'page': 'clases'})


@login_required
def eliminar_clase(request, id):
    if request.method != 'POST':
        return redirect('listar_clases')
    clase = get_object_or_404(Clase, id=id, usuario=request.user)
    try:
        titulo = clase.titulo
        # Snapshot needed for GCal cleanup AFTER local delete succeeds
        clase_snapshot = clase
        clase.delete()
        logger.info('Clase eliminada: id=%s "%s" por %s', id, titulo, request.user.username)
        # Best-effort GCal cleanup; failures don't block the local delete
        try:
            _sync_gcal(clase_snapshot, 'delete', request.user)
        except Exception as gcal_e:
            logger.warning('GCal delete falló para clase id=%s: %s', id, gcal_e)
        messages.success(request, 'Clase eliminada correctamente')
    except Exception as e:
        logger.error('Error eliminando clase id=%s: %s', id, e)
        messages.error(request, 'No se pudo eliminar la clase.')
    return redirect('listar_clases')


@login_required
def cambiar_estado_clase(request, id, estado):
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if request.method != 'POST':
        if is_ajax:
            return JsonResponse({'ok': False, 'error': 'Método no permitido'}, status=405)
        return _safe_redirect(request, request.META.get('HTTP_REFERER'), 'dashboard')

    clase = get_object_or_404(Clase, id=id, usuario=request.user)

    if estado not in ESTADOS_VALIDOS:
        if is_ajax:
            return JsonResponse({'ok': False, 'error': 'Estado inválido'}, status=400)
        return _safe_redirect(request, request.META.get('HTTP_REFERER'), 'dashboard')

    today = timezone.localdate()
    if estado == 'in_progress' and clase.fecha != today:
        msg = 'Solo puedes iniciar una clase el día que está programada.'
        if is_ajax:
            return JsonResponse({'ok': False, 'error': msg}, status=400)
        messages.error(request, msg)
        return _safe_redirect(request, request.META.get('HTTP_REFERER'), 'dashboard')

    clase.estado = estado
    clase.save(update_fields=['estado', 'updated_at'])
    logger.info('Estado clase id=%s → %s por %s', clase.id, estado, request.user.username)

    if is_ajax:
        return JsonResponse({'ok': True, 'estado': estado, 'label': clase.get_estado_display_spanish()})

    if estado == 'pending':
        # Reciclar → llevar al editor para que actualice fecha, hora y tema
        return redirect(f"{reverse('editar_clase', args=[clase.id])}?reciclada=1")

    messages.success(request, f'Estado actualizado a {clase.get_estado_display_spanish()}')
    return _safe_redirect(request, request.META.get('HTTP_REFERER'), 'dashboard')


# ==================== REGISTRO ====================

def registro(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        form = RegistroForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.first_name = form.cleaned_data['nombre']
            try:
                user.save()
            except IntegrityError:
                messages.error(request, 'El nombre de usuario ya está en uso. Por favor elige otro.')
                return render(request, 'registro.html', {'form': form, 'next': request.GET.get('next', '')})
            except Exception as e:
                logger.error('Error inesperado al crear usuario %s: %s', form.cleaned_data.get('username'), e)
                messages.error(request, 'No se pudo crear la cuenta. Intenta de nuevo.')
                return render(request, 'registro.html', {'form': form, 'next': request.GET.get('next', '')})
            try:
                config, _ = ConfiguracionUsuario.objects.get_or_create(usuario=user)
                config.materia = form.cleaned_data['materia']
                config.save()
                for grado_nombre in form.cleaned_data['grados']:
                    grado, _ = Grado.objects.get_or_create(nombre=grado_nombre)
                    config.grados.add(grado)
            except Exception as e:
                logger.error('Error sincronizando configuración para %s: %s', user.username, e)
                messages.warning(request, 'Cuenta creada. No se pudieron sincronizar algunos ajustes; edítalos desde Configuración.')
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            logger.info('Nuevo usuario registrado: %s', user.username)
            next_url = request.GET.get('next') or request.POST.get('next') or ''
            if next_url:
                return _safe_redirect(request, next_url, 'bienvenida')
            return redirect('bienvenida')
    else:
        form = RegistroForm()
    return render(request, 'registro.html', {
        'form': form,
        'next': request.GET.get('next', ''),
    })


@login_required
def bienvenida(request):
    return render(request, 'bienvenida.html', {'page': 'bienvenida'})


# ==================== CURSOS ====================

@login_required
def listar_cursos(request):
    cursos = Curso.objects.filter(usuario=request.user)
    return render(request, 'cursos/listar.html', {
        'cursos': cursos, 'page': 'cursos',
    })


@login_required
def crear_curso(request):
    try:
        user_grados = list(request.user.configuracion.grados.all())
    except Exception:
        user_grados = []

    if request.method == 'POST':
        form = CursoForm(request.POST, user_grados=user_grados)
        if not form.is_valid():
            messages.error(request, 'Revisa los campos obligatorios antes de guardar.')
            return render(request, 'cursos/crear.html', {'form': form, 'page': 'cursos'})

        curso = form.save(commit=False)
        curso.usuario = request.user
        curso.materia = get_user_materia(request.user)
        try:
            curso.save()
        except IntegrityError:
            messages.error(request, f'Ya tienes un curso llamado "{curso.nombre}". Elige otro nombre.')
            return render(request, 'cursos/crear.html', {'form': form, 'page': 'cursos'})
        except Exception as e:
            logger.error('Error guardando curso: %s', e)
            messages.error(request, 'Ocurrio un error al guardar el curso. Intentalo de nuevo.')
            return render(request, 'cursos/crear.html', {'form': form, 'page': 'cursos'})

        messages.success(request, f"Curso '{curso.nombre}' creado correctamente.")
        return redirect('ver_curso', id=curso.id)
    else:
        form = CursoForm(user_grados=user_grados)
    return render(request, 'cursos/crear.html', {'form': form, 'page': 'cursos'})


@login_required
def ver_curso(request, id):
    curso = get_object_or_404(Curso, id=id, usuario=request.user)

    # Filter by curso.nombre so each section (A/B) shows only its own classes
    clases = Clase.objects.filter(
        usuario=request.user,
        grado_nombre=curso.nombre,
    ).order_by('-fecha', '-hora_inicio')

    return render(request, 'cursos/detalle.html', {
        'curso': curso,
        'clases': clases,
        'page': 'cursos',
    })


@login_required
def eliminar_curso(request, id):
    if request.method != 'POST':
        return redirect('listar_cursos')
    curso = get_object_or_404(Curso, id=id, usuario=request.user)
    nombre = curso.nombre
    # Orphan-class cleanup: classes are linked by grado_nombre string (no FK),
    # so we must clear that reference manually to avoid orphan filtering.
    Clase.objects.filter(usuario=request.user, grado_nombre=nombre).update(grado_nombre='')
    curso.delete()
    messages.success(request, f'Curso "{nombre}" eliminado.')
    return redirect('listar_cursos')


# ==================== NOTAS ====================

@login_required
def notas(request):
    notas_list = Nota.objects.filter(usuario=request.user).order_by('-fecha_creacion')

    if request.method == 'POST':
        titulo = request.POST.get('titulo', '').strip()[:200]
        contenido = request.POST.get('contenido', '').strip()[:10000]
        if titulo and contenido:
            Nota.objects.create(titulo=titulo, contenido=contenido, usuario=request.user)
            messages.success(request, '¡Nota guardada!')
            return redirect('notas')
        else:
            messages.error(request, 'El título y el contenido son obligatorios para guardar una nota.')

    return render(request, 'notas.html', {'notas': notas_list, 'page': 'notas'})


@login_required
def eliminar_nota(request, id):
    if request.method != 'POST':
        return redirect('notas')
    nota = get_object_or_404(Nota, id=id, usuario=request.user)
    try:
        nota.delete()
        messages.success(request, 'Nota eliminada correctamente')
    except Exception as e:
        logger.error('Error eliminando nota id=%s: %s', id, e)
        messages.error(request, 'No se pudo eliminar la nota.')
    return redirect('notas')


# ==================== CALENDARIO ====================

@login_required
def calendario(request):
    today = timezone.localdate()
    try:
        year = int(request.GET.get('year', today.year))
        month = int(request.GET.get('month', today.month))
    except (ValueError, TypeError):
        year, month = today.year, today.month

    year = max(2020, min(2035, year))
    month = max(1, min(12, month))

    clases = Clase.objects.filter(
        usuario=request.user,
        fecha__year=year,
        fecha__month=month,
    ).order_by('fecha', 'hora_inicio')

    clases_por_dia = {}
    for clase in clases:
        clases_por_dia.setdefault(clase.fecha.day, []).append(clase)

    weeks_raw = calendar.monthcalendar(year, month)
    calendar_data = []
    for week in weeks_raw:
        week_data = []
        for day in week:
            week_data.append({
                'day': day,
                'clases': clases_por_dia.get(day, []) if day else [],
                'is_today': (day == today.day and month == today.month and year == today.year),
            })
        calendar_data.append(week_data)

    prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
    next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)

    return render(request, 'calendario.html', {
        'page': 'calendario',
        'year': year,
        'month': month,
        'month_name': MESES_ES[month],
        'dias_es': DIAS_ES,
        'calendar_data': calendar_data,
        'clases': clases,
        'today': today,
        'prev_year': prev_year,
        'prev_month': prev_month,
        'next_year': next_year,
        'next_month': next_month,
    })


# ==================== OTRAS PÁGINAS ====================

@login_required
def planificador(request):
    q = request.GET.get('q', '').strip()
    estado_filtro = request.GET.get('estado', 'all')

    clases = Clase.objects.filter(usuario=request.user).order_by('fecha', 'hora_inicio')
    if q:
        clases = clases.filter(Q(titulo__icontains=q) | Q(materia__icontains=q))
    if estado_filtro and estado_filtro != 'all':
        clases = clases.filter(estado=estado_filtro)

    return render(request, 'planificador.html', {
        'clases': clases, 'q': q, 'estado_filtro': estado_filtro, 'page': 'planificador',
        'today': timezone.localdate(),
    })


GRADO_NOMBRES = [v for v, _ in NIVEL_ACADEMICO_CHOICES]

_SECCION_A_TAB = {
    'perfil': 'perfil',
    'contrasena': 'seguridad',
    'preferencias': 'preferencias',
    'personalizacion': 'personalizacion',
    'google_calendar': 'google_calendar',
}


@login_required
def ajustes(request):
    config, _ = ConfiguracionUsuario.objects.get_or_create(usuario=request.user)

    if request.method == 'POST':
        seccion = request.POST.get('seccion')

        if seccion == 'perfil':
            request.user.first_name = request.POST.get('first_name', '').strip()
            request.user.last_name = request.POST.get('last_name', '').strip()
            email = request.POST.get('email', '').strip()
            if email:
                request.user.email = email
            request.user.save()
            config.nombre_institucion = request.POST.get('nombre_institucion', '').strip()
            config.cargo = request.POST.get('cargo', '').strip()
            config.save()
            messages.success(request, 'Cambios en el perfil actualizados correctamente.')

        elif seccion == 'contrasena':
            from django.contrib.auth import update_session_auth_hash
            actual = request.POST.get('password_actual', '')
            nueva = request.POST.get('password_nueva', '')
            confirmar = request.POST.get('password_confirmar', '')
            from django.core.exceptions import ValidationError as _VE
            from django.contrib.auth.password_validation import validate_password
            if not request.user.check_password(actual):
                messages.error(request, 'La contraseña actual es incorrecta.')
            elif nueva != confirmar:
                messages.error(request, 'Las contraseñas nuevas no coinciden.')
            elif len(nueva) < 8:
                messages.error(request, 'La contraseña debe tener al menos 8 caracteres.')
            else:
                try:
                    validate_password(nueva, user=request.user)
                except _VE as ve:
                    messages.error(request, ' '.join(ve.messages))
                else:
                    request.user.set_password(nueva)
                    request.user.save()
                    update_session_auth_hash(request, request.user)
                    messages.success(request, 'Contraseña actualizada correctamente.')

        elif seccion == 'preferencias':
            grado_nombres = request.POST.getlist('grados')
            config.grados.clear()
            for gn in grado_nombres:
                gn = gn.strip()
                if gn:
                    grado_obj, _ = Grado.objects.get_or_create(nombre=gn)
                    config.grados.add(grado_obj)
            config.notif_clases = request.POST.get('notif_clases') == 'on'
            config.notif_tareas = request.POST.get('notif_tareas') == 'on'
            config.notif_resumen = request.POST.get('notif_resumen') == 'on'
            config.recibir_recordatorio_email = 'recibir_recordatorio_email' in request.POST
            from datetime import time as _time
            hora_str = (request.POST.get('hora_recordatorio_preferida') or '').strip()
            if hora_str:
                try:
                    h, m = [int(x) for x in hora_str.split(':')]
                    config.hora_recordatorio_preferida = _time(h, m)
                except (ValueError, AttributeError):
                    pass
            config.save()
            messages.success(request, 'Preferencias de clase guardadas.')

        elif seccion == 'personalizacion':
            color = request.POST.get('color_scheme', 'default')
            if color in [c[0] for c in ConfiguracionUsuario.COLORES]:
                config.color_scheme = color
            config.save()
            messages.success(request, 'Personalización guardada.')

        elif seccion == 'google_calendar':
            cal_id = request.POST.get('google_calendar_id', '').strip()
            if cal_id and not CALENDAR_ID_RE.match(cal_id):
                messages.error(request, 'El ID del calendario no tiene un formato válido.')
            else:
                config.google_calendar_id = cal_id
                config.save()
                messages.success(request, 'Google Calendar configurado.')

        tab = _SECCION_A_TAB.get(seccion, 'perfil')
        return redirect(f"{request.path}?s={tab}")

    seccion_activa = request.GET.get('s', 'perfil')
    grados_del_usuario = set(config.grados.values_list('nombre', flat=True))

    # Google Calendar connection status — also flag stale/revoked tokens so the UI
    # can prompt the user to re-link instead of silently failing on every sync.
    gcal_conectado = False
    gcal_email = ''
    gcal_clases_sin_sync = 0
    gcal_needs_reauth = False
    try:
        from allauth.socialaccount.models import SocialToken
        token = SocialToken.objects.select_related('account').filter(
            account__user=request.user, account__provider='google'
        ).first()
        if token:
            gcal_conectado = True
            gcal_email = (token.account.extra_data or {}).get('email', request.user.email)
            gcal_clases_sin_sync = Clase.objects.filter(
                usuario=request.user, google_event_id=''
            ).count()
            # No refresh token means the user logged in without offline access:
            # any future API call will fail with 'no_refresh'. Surface this now.
            if not token.token_secret:
                gcal_needs_reauth = True
    except Exception as e:
        logger.warning('ajustes: gcal status check fallo user=%s: %s', request.user.id, e)

    return render(request, 'ajustes.html', {
        'page': 'ajustes',
        'config': config,
        'seccion_activa': seccion_activa,
        'grados_disponibles': GRADO_NOMBRES,
        'grados_del_usuario': grados_del_usuario,
        'user_materia': get_user_materia(request.user),
        'gcal_conectado': gcal_conectado,
        'gcal_email': gcal_email,
        'gcal_clases_sin_sync': gcal_clases_sin_sync,
        'gcal_needs_reauth': gcal_needs_reauth,
    })


@login_required
def perfil(request):
    config, _ = ConfiguracionUsuario.objects.get_or_create(usuario=request.user)

    if request.method == 'POST':
        u = request.user
        new_email = request.POST.get('email', '').strip()
        if new_email and new_email != u.email:
            if User.objects.exclude(pk=u.pk).filter(email__iexact=new_email).exists():
                messages.error(request, 'Ese correo ya está registrado por otra cuenta.')
                return redirect('perfil')
        u.first_name = request.POST.get('first_name', '').strip()
        u.last_name = request.POST.get('last_name', '').strip()
        u.email = new_email
        u.save()
        config.cargo = request.POST.get('cargo', '').strip()
        config.nombre_institucion = request.POST.get('nombre_institucion', '').strip()
        config.materia = request.POST.get('materia', '').strip()
        config.save()
        messages.success(request, 'Cambios en el perfil actualizados correctamente.')
        return redirect('perfil')

    from django.db.models import Count as _Count, Q as _Q
    clases_qs = Clase.objects.filter(usuario=request.user)
    stats = clases_qs.aggregate(
        total=_Count('id'),
        completadas=_Count('id', filter=_Q(estado='completed')),
        pendientes=_Count('id', filter=_Q(estado='pending')),
        en_progreso=_Count('id', filter=_Q(estado='in_progress')),
    )

    filled = [
        request.user.first_name, request.user.last_name,
        request.user.email, config.cargo,
        config.nombre_institucion, config.materia,
    ]
    completeness = int(sum(1 for f in filled if f) / len(filled) * 100)
    completeness_remaining = 100 - completeness

    return render(request, 'perfil.html', {
        'page': 'perfil',
        'config': config,
        'completeness_remaining': completeness_remaining,
        'clases_count': stats['total'],
        'clases_completadas': stats['completadas'],
        'clases_pendientes': stats['pendientes'],
        'clases_en_progreso': stats['en_progreso'],
        'cursos_count': Curso.objects.filter(usuario=request.user).count(),
        'notas_count': Nota.objects.filter(usuario=request.user).count(),
        'recursos_count': Recurso.objects.filter(usuario=request.user).count(),
        'clases_recientes': clases_qs.order_by('-fecha_creacion')[:6],
        'completeness': completeness,
        'materia_choices': MATERIA_CHOICES,
    })


# ==================== RECURSOS ====================

@login_required
def listar_recursos(request):
    CATEGORIAS = {
        'documentos': ['documento', 'taller'],
        'multimedia': ['video', 'imagen'],
    }
    categoria = request.GET.get('cat', 'todos')
    q = (request.GET.get('q') or '').strip()

    recursos = Recurso.objects.filter(usuario=request.user).select_related('clase')
    if categoria in CATEGORIAS:
        recursos = recursos.filter(tipo__in=CATEGORIAS[categoria])
    if q:
        recursos = recursos.filter(
            Q(titulo__icontains=q) | Q(descripcion__icontains=q)
        )

    return render(request, 'recursos.html', {
        'page': 'recursos',
        'recursos': recursos,
        'form': RecursoForm(),
        'categoria': categoria,
        'q': q,
        'user_materia': get_user_materia(request.user),
        'cursos': Curso.objects.filter(usuario=request.user),
    })


@login_required
def crear_recurso(request):
    if request.method == 'POST':
        form = RecursoForm(request.POST, request.FILES)
        if form.is_valid():
            recurso = form.save(commit=False)
            recurso.usuario = request.user
            recurso.save()
            messages.success(request, '¡Recurso guardado correctamente!')
            return redirect('listar_recursos')
        else:
            messages.error(request, 'Revisa los campos del formulario.')
    return redirect('listar_recursos')


@login_required
def eliminar_recurso(request, id):
    if request.method != 'POST':
        return redirect('listar_recursos')
    recurso = get_object_or_404(Recurso, id=id, usuario=request.user)
    archivo_field = recurso.archivo if recurso.archivo else None
    # DB delete first; only purge the physical file if the row really went away,
    # avoiding the "ghost row pointing to a missing file" failure mode.
    try:
        with transaction.atomic():
            recurso.delete()
    except Exception as e:
        logger.error('Error eliminando recurso id=%s: %s', id, e)
        messages.error(request, 'No se pudo eliminar el recurso.')
        return redirect('listar_recursos')
    if archivo_field:
        try:
            archivo_field.delete(save=False)
        except Exception as e:
            logger.warning('Recurso id=%s eliminado pero el archivo no se borró: %s', id, e)
    messages.success(request, 'Recurso eliminado.')
    return redirect('listar_recursos')


# ==================== API ====================

@login_required
def guardar_preferencia(request):
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)

    config, _ = ConfiguracionUsuario.objects.get_or_create(usuario=request.user)
    tema = request.POST.get('tema', '').strip()
    color = request.POST.get('color', '').strip()

    if tema in ('light', 'dark'):
        config.tema = tema
    if color in ('default', 'blue', 'green', 'orange', 'pink'):
        config.color_scheme = color
    config.save()

    return JsonResponse({'ok': True})


# ==================== GOOGLE CALENDAR SYNC ====================

def _get_gcal_service(user):
    """Returns (service, error_code).

    Error codes (machine-readable, never user-facing):
      'no_deps'         — google libs missing
      'no_google_account' — user hasn't linked Google
      'no_oauth_config' — OAuth client_id/secret missing in env
      'no_refresh'      — no refresh_token (must re-link with prompt=consent)
      'token_revoked'   — refresh failed; SocialToken purged
      'api_error'       — Calendar API build failed (transient)
    """
    try:
        from allauth.socialaccount.models import SocialToken
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request as GRequest
        from google.auth.exceptions import RefreshError
        from googleapiclient.discovery import build
    except ImportError as e:
        logger.error('GCal deps missing: %s', e)
        return None, 'no_deps'

    try:
        token_obj = SocialToken.objects.select_related('app').get(
            account__user=user, account__provider='google'
        )
    except SocialToken.DoesNotExist:
        return None, 'no_google_account'
    except Exception as e:
        logger.warning('SocialToken lookup error user=%s: %s', user.id, e)
        return None, 'no_google_account'

    # OAuth client credentials: prefer DB SocialApp, fall back to settings-based config.
    from django.conf import settings as _cfg
    if token_obj.app and token_obj.app.client_id:
        client_id = token_obj.app.client_id
        client_secret = token_obj.app.secret
    else:
        prov = _cfg.SOCIALACCOUNT_PROVIDERS.get('google', {}).get('APP', {})
        client_id = prov.get('client_id', '')
        client_secret = prov.get('secret', '')
    if not client_id or not client_secret:
        logger.error('GCal: GOOGLE_OAUTH_CLIENT_ID/SECRET not configured in env')
        return None, 'no_oauth_config'

    creds = Credentials(
        token=token_obj.token,
        refresh_token=token_obj.token_secret or None,
        token_uri='https://oauth2.googleapis.com/token',
        client_id=client_id,
        client_secret=client_secret,
        scopes=['https://www.googleapis.com/auth/calendar.events'],
    )

    if not creds.valid:
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(GRequest())
                # Persist the rotated access token for the next call
                token_obj.token = creds.token
                update_fields = ['token']
                # Some refreshes also rotate the refresh token (rare, but Google may)
                if creds.refresh_token and creds.refresh_token != token_obj.token_secret:
                    token_obj.token_secret = creds.refresh_token
                    update_fields.append('token_secret')
                token_obj.save(update_fields=update_fields)
            except RefreshError as e:
                # Refresh token revoked or expired — purge it so the user re-links cleanly
                logger.warning('GCal RefreshError user=%s — purging token: %s', user.id, e)
                token_obj.delete()
                return None, 'token_revoked'
            except Exception as e:
                logger.error('GCal refresh inesperado user=%s: %s', user.id, e)
                return None, 'token_revoked'
        else:
            # No refresh token at all → user logged in without granting offline access
            return None, 'no_refresh'

    try:
        # cache_discovery=False avoids a noisy "file_cache" warning under newer
        # google-api-python-client; discovery doc is small (~50KB) so re-fetching
        # per request is acceptable here. For high-volume use, swap to a memory cache.
        service = build('calendar', 'v3', credentials=creds, cache_discovery=False)
        return service, None
    except Exception as e:
        logger.error('GCal build() failed user=%s: %s', user.id, e)
        return None, 'api_error'


def _build_gcal_event(clase):
    from datetime import datetime, timedelta
    from django.utils import timezone as tz_utils
    from django.conf import settings as _settings

    dt_start = tz_utils.make_aware(datetime.combine(clase.fecha, clase.hora_inicio))
    # Use teacher's session duration if configured, fallback to 60 min
    duration_min = 60
    try:
        duration_min = clase.usuario.horario_academico.duracion_sesion or 60
    except Exception:
        pass
    dt_end = dt_start + timedelta(minutes=duration_min)

    desc_parts = []
    if clase.objetivos:
        desc_parts.append(f'Objetivos:\n{clase.objetivos}')
    if clase.notas:
        desc_parts.append(f'Notas:\n{clase.notas}')
    description = '\n\n'.join(desc_parts) or 'Clase planificada en SkedyClass.'

    tz_name = getattr(_settings, 'TIME_ZONE', 'America/Bogota')
    curso_label = clase.grado_nombre or clase.materia or 'SkedyClass'
    # Reminder summary surfaces the topic in the popup itself
    summary = f'Clase: {curso_label} — {clase.titulo}'
    return {
        'summary': summary,
        'description': description,
        'start': {'dateTime': dt_start.isoformat(), 'timeZone': tz_name},
        'end': {'dateTime': dt_end.isoformat(), 'timeZone': tz_name},
        'reminders': {
            'useDefault': False,
            'overrides': [
                {'method': 'popup', 'minutes': 30},
                {'method': 'email', 'minutes': 30},
            ],
        },
    }


def _gcal_cal_id(user):
    try:
        cal_id = user.configuracion.google_calendar_id
        return cal_id if cal_id else 'primary'
    except Exception:
        return 'primary'


_GCAL_USER_MSG = {
    'no_deps': 'Falta la librería de Google. Avisa al administrador.',
    'no_google_account': None,  # silent: user simply hasn't linked Google
    'no_oauth_config': 'Google OAuth no está configurado. Avisa al administrador.',
    'no_refresh': 'Re-vincula tu cuenta Google para sincronizar tu calendario.',
    'token_revoked': 'Tu sesión con Google expiró. Re-vincula tu cuenta para continuar.',
    'api_error': 'Error temporal con Google Calendar. Intenta de nuevo en unos minutos.',
}


def _gcal_user_msg(error_code):
    """Map a `_get_gcal_service` error code to a user-facing message."""
    return _GCAL_USER_MSG.get(error_code, 'Error de conexión con Google Calendar.')


def _sync_gcal(clase, action, user, service=None, cal_id=None):
    """Sync a class with GCal. Returns (success, toast_msg|None).
    Pass `service` and `cal_id` to reuse them across multiple syncs."""
    if service is None:
        service, error = _get_gcal_service(user)
        if error:
            if error == 'no_google_account':
                return False, None  # silent — user hasn't linked Google
            return False, _gcal_user_msg(error)
    if cal_id is None:
        cal_id = _gcal_cal_id(user)

    body = _build_gcal_event(clase)

    # Distinguish 404 (event vanished, safe to recreate) from other errors.
    try:
        from googleapiclient.errors import HttpError
    except ImportError:
        HttpError = Exception  # type: ignore

    try:
        if action == 'create':
            result = service.events().insert(calendarId=cal_id, body=body).execute()
            eid = result.get('id', '')
            if eid:
                Clase.objects.filter(pk=clase.pk).update(google_event_id=eid)
                clase.google_event_id = eid
            clase._gcal_html_link = result.get('htmlLink', '')
            return True, 'Clase sincronizada con tu Google Calendar.'

        elif action == 'update':
            if clase.google_event_id:
                try:
                    service.events().patch(
                        calendarId=cal_id, eventId=clase.google_event_id, body=body
                    ).execute()
                    return True, 'Actualizando eventos en la nube…'
                except HttpError as he:
                    status = getattr(getattr(he, 'resp', None), 'status', None)
                    if status in (404, 410):
                        # Event deleted from GCal — safe to recreate
                        result = service.events().insert(calendarId=cal_id, body=body).execute()
                        eid = result.get('id', '')
                        if eid:
                            Clase.objects.filter(pk=clase.pk).update(google_event_id=eid)
                            clase.google_event_id = eid
                        return True, 'Evento recreado en Google Calendar.'
                    # Other HTTP errors: do NOT duplicate — surface the error
                    logger.error('GCal patch fallo (status=%s) clase=%s: %s', status, clase.id, he)
                    return False, 'No se pudo actualizar el evento en Google Calendar.'
            else:
                result = service.events().insert(calendarId=cal_id, body=body).execute()
                eid = result.get('id', '')
                if eid:
                    Clase.objects.filter(pk=clase.pk).update(google_event_id=eid)
                    clase.google_event_id = eid
                return True, 'Clase sincronizada con tu Google Calendar.'

        elif action == 'delete':
            if clase.google_event_id:
                try:
                    service.events().delete(
                        calendarId=cal_id, eventId=clase.google_event_id
                    ).execute()
                except HttpError as he:
                    status = getattr(getattr(he, 'resp', None), 'status', None)
                    if status in (404, 410):
                        # Already deleted on GCal — that's fine
                        return True, None
                    logger.error('GCal delete fallo (status=%s) clase=%s: %s', status, clase.id, he)
                    return False, 'No se pudo eliminar el evento en Google Calendar.'
            return True, None

    except Exception as e:
        logger.error('GCal sync error action=%s clase=%s: %s', action, clase.id, e)
        return False, 'Error de conexión con Google, intenta re-vincular tu cuenta.'

    return False, None


@login_required
@rate_limit('gcal_sync_one', max_calls=20, window_sec=60, json_response=False)
def gcal_sync_clase(request, id):
    """Manually sync a single class to Google Calendar. POST-only:
    this endpoint modifies remote state in Google so it must not be GET-reachable
    (CSRF + accidental triggers via prefetch/img-tag/email-preview)."""
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if request.method != 'POST':
        if is_ajax:
            return JsonResponse({'ok': False, 'error': 'Método no permitido'}, status=405)
        return _safe_redirect(request, request.META.get('HTTP_REFERER'), 'planificador')
    clase = get_object_or_404(Clase, id=id, usuario=request.user)
    action = 'update' if clase.google_event_id else 'create'
    ok, msg = _sync_gcal(clase, action, request.user)
    html_link = getattr(clase, '_gcal_html_link', '')
    if msg:
        if ok:
            messages.success(request, msg)
        else:
            messages.error(request, msg)
    elif not ok:
        messages.warning(request, 'Vincula tu cuenta Google para sincronizar clases con el calendario.')
    if is_ajax:
        return JsonResponse({'ok': ok, 'message': msg or '', 'event_id': clase.google_event_id, 'html_link': html_link})
    return _safe_redirect(request, request.META.get('HTTP_REFERER'), 'planificador')


@login_required
def gcal_eventos_api(request):
    """Return Google Calendar events for a month (for bidirectional overlay)."""
    import calendar as _cal

    _today = timezone.localdate()
    try:
        year = int(request.GET.get('year', _today.year))
        month = int(request.GET.get('month', _today.month))
    except (ValueError, TypeError):
        year, month = _today.year, _today.month

    service, error = _get_gcal_service(request.user)
    if error == 'no_google_account':
        return JsonResponse({'ok': True, 'eventos': [], 'connected': False})
    if error in ('no_refresh', 'token_revoked'):
        return JsonResponse({
            'ok': False,
            'error': _gcal_user_msg(error),
            'needs_reauth': True,
        })
    if error:
        return JsonResponse({'ok': False, 'error': _gcal_user_msg(error)})

    from datetime import datetime as _dt
    from django.utils import timezone as _tz
    first_day = date(year, month, 1)
    last_day = date(year, month, _cal.monthrange(year, month)[1])
    time_min = _tz.make_aware(_dt.combine(first_day, _dt.min.time())).isoformat()
    time_max = _tz.make_aware(_dt.combine(last_day, _dt.max.time().replace(microsecond=0))).isoformat()

    try:
        cal_id = _gcal_cal_id(request.user)
        result = service.events().list(
            calendarId=cal_id,
            timeMin=time_min,
            timeMax=time_max,
            maxResults=50,
            singleEvents=True,
            orderBy='startTime',
        ).execute()

        # Build set of synced event IDs to detect GCal-only events
        synced_ids = set(
            Clase.objects.filter(
                usuario=request.user
            ).exclude(google_event_id='').values_list('google_event_id', flat=True)
        )

        from datetime import datetime as _dt
        eventos = []
        for item in result.get('items', []):
            start = item.get('start', {})
            dt_str = start.get('dateTime') or start.get('date', '')
            try:
                if 'T' in dt_str:
                    # Python 3.11+ fromisoformat handles offsets like +05:00 or Z natively.
                    # For older formats, normalize trailing 'Z' to '+00:00' before parsing.
                    normalized = dt_str.replace('Z', '+00:00') if dt_str.endswith('Z') else dt_str
                    dt = _dt.fromisoformat(normalized)
                    day = dt.day
                    time_str = dt.strftime('%H:%M')
                elif dt_str:
                    parts = dt_str.split('-')
                    day = int(parts[2]) if len(parts) >= 3 else 0
                    time_str = ''
                else:
                    day = 0
                    time_str = ''
            except (ValueError, IndexError, TypeError):
                day = 0
                time_str = ''

            eventos.append({
                'id': item.get('id', ''),
                'titulo': item.get('summary', 'Sin título'),
                'day': day,
                'time': time_str,
                'is_skedyclass': item.get('id', '') in synced_ids,
            })

        return JsonResponse({'ok': True, 'eventos': eventos, 'connected': True})
    except Exception as e:
        logger.error('gcal_eventos_api fallo: %s', e)
        return JsonResponse({'ok': False, 'error': 'Error al cargar eventos de Google Calendar.'})


@login_required
def gcal_disconnect(request):
    """Unlink the user's Google account from SkedyClass.
    - Deletes the local SocialToken + SocialAccount (revokes our access).
    - Clears google_event_id on the user's classes so the UI marks them as un-synced.
    - The events themselves stay in the user's Google Calendar (we only drop our pointer).
    - To fully revoke our app's grant, user must also visit myaccount.google.com/permissions."""
    if request.method != 'POST':
        return redirect('/ajustes/?s=google_calendar')
    try:
        from allauth.socialaccount.models import SocialToken, SocialAccount
    except ImportError:
        messages.error(request, 'Google no está disponible en este servidor.')
        return redirect('/ajustes/?s=google_calendar')
    with transaction.atomic():
        SocialToken.objects.filter(
            account__user=request.user, account__provider='google'
        ).delete()
        SocialAccount.objects.filter(
            user=request.user, provider='google'
        ).delete()
        Clase.objects.filter(usuario=request.user).exclude(
            google_event_id=''
        ).update(google_event_id='')
    logger.info('Usuario desvinculó Google: %s', request.user.username)
    messages.success(
        request,
        'Cuenta Google desvinculada. Los eventos existentes permanecen en tu calendario. '
        'Para revocar el permiso totalmente, visita myaccount.google.com/permissions.'
    )
    return redirect('/ajustes/?s=google_calendar')


@login_required
@rate_limit('gcal_sync_all', max_calls=3, window_sec=60, json_response=False)
def gcal_sync_all(request):
    """Sync all non-synced classes to Google Calendar."""
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Método no permitido'}, status=405)

    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    # Build the GCal service ONCE and reuse it for every class
    service, err = _get_gcal_service(request.user)
    if err:
        if err == 'no_google_account':
            messages.warning(request, 'Vincula tu cuenta Google para sincronizar clases.')
        else:
            messages.warning(request, _gcal_user_msg(err))
        if is_ajax:
            return JsonResponse({'ok': False, 'error': err, 'needs_reauth': err in ('no_refresh', 'token_revoked')})
        return redirect('/ajustes/?s=google_calendar')

    cal_id = _gcal_cal_id(request.user)
    total_pending = Clase.objects.filter(usuario=request.user, google_event_id='').count()
    BATCH = 50
    clases_sin_sync = Clase.objects.filter(usuario=request.user, google_event_id='')[:BATCH]

    synced = 0
    errors = 0
    for clase in clases_sin_sync:
        ok, _ = _sync_gcal(clase, 'create', request.user, service=service, cal_id=cal_id)
        if ok:
            synced += 1
        else:
            errors += 1
            if errors >= 3:
                break  # Stop if hitting repeated API errors

    if synced > 0:
        plural = 's' if synced != 1 else ''
        messages.success(request, f'{synced} clase{plural} sincronizada{plural} con Google Calendar.')
    if errors > 0:
        plural = 's' if errors != 1 else ''
        messages.warning(request, f'{errors} clase{plural} no pudo sincronizarse. Verifica los permisos de Google.')
    remaining = total_pending - synced
    if remaining > 0 and errors == 0:
        messages.info(request, f'Quedan {remaining} clases por sincronizar. Ejecuta de nuevo para continuar.')
    if synced == 0 and errors == 0:
        messages.info(request, 'Todas las clases ya están sincronizadas.')

    if is_ajax:
        return JsonResponse({'ok': True, 'synced': synced, 'errors': errors, 'remaining': max(0, remaining)})
    return redirect('/ajustes/?s=google_calendar')


# ==================== HORARIO ACADÉMICO ====================

@login_required
def horario(request):
    from datetime import datetime as _dt, timedelta as _td

    horario_obj, _ = HorarioAcademico.objects.get_or_create(usuario=request.user)
    descansos = list(horario_obj.descansos.all())

    today = timezone.localdate()
    try:
        week_offset = int(request.GET.get('semana', 0))
    except (ValueError, TypeError):
        week_offset = 0

    monday = today - _td(days=today.weekday()) + _td(weeks=week_offset)

    dias = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes']
    dias_labels = {
        'lunes': 'Lunes', 'martes': 'Martes', 'miercoles': 'Miércoles',
        'jueves': 'Jueves', 'viernes': 'Viernes',
    }
    _DIA_TO_WD = {'lunes': 0, 'martes': 1, 'miercoles': 2, 'jueves': 3, 'viernes': 4}
    week_dates = {dia: monday + _td(days=wd) for dia, wd in _DIA_TO_WD.items()}

    # Time slots
    base_dt = _dt.combine(today, horario_obj.hora_inicio_jornada)
    end_dt = _dt.combine(today, horario_obj.hora_fin_jornada)
    slot_delta = _td(minutes=horario_obj.duracion_sesion)
    slots = []
    curr = base_dt
    while curr < end_dt:
        slots.append(curr.time())
        curr += slot_delta

    # Break slots
    descanso_slots = set()
    for d in descansos:
        t = _dt.combine(today, d.hora_inicio)
        t_end = _dt.combine(today, d.hora_fin)
        while t < t_end and t < end_dt:
            descanso_slots.add(t.time())
            t += slot_delta

    def _find_slot(hora_val):
        for s in slots:
            s_end = (_dt.combine(today, s) + slot_delta).time()
            if hora_val >= s and hora_val < s_end:
                return s
        return None

    # Clases for this week
    week_end_date = monday + _td(days=4)
    clases_week = list(Clase.objects.filter(
        usuario=request.user,
        fecha__range=(monday, week_end_date),
    ).order_by('fecha', 'hora_inicio'))

    clase_grid = {}
    for clase in clases_week:
        dia = _WEEKDAY_TO_DIA.get(clase.fecha.weekday())
        if not dia:
            continue
        slot = _find_slot(clase.hora_inicio)
        if slot:
            clase_grid.setdefault((dia, slot), []).append(clase)

    cursos = list(Curso.objects.filter(usuario=request.user).order_by('nombre'))

    has_conflicts = any(len(v) > 1 for v in clase_grid.values())

    # Pre-build grid rows for template (avoids dict-key lookups in template)
    grid_rows = []
    for slot in slots:
        slot_str = slot.strftime('%H:%M')
        is_descanso = slot in descanso_slots
        cells = []
        for dia in dias:
            fecha_dia = week_dates[dia]
            clases_in = clase_grid.get((dia, slot), [])
            cells.append({
                'dia': dia,
                'fecha': fecha_dia,
                'fecha_iso': fecha_dia.isoformat(),
                'slot': slot_str,
                'clases': clases_in,
                'is_conflict': len(clases_in) > 1,
                'is_today': fecha_dia == today,
                'is_descanso': is_descanso,
            })
        grid_rows.append({
            'slot': slot_str,
            'is_descanso': is_descanso,
            'cells': cells,
        })

    # Pre-built column headers: [{dia, label, fecha, is_today}]
    dias_info = [
        {
            'dia': dia,
            'label': dias_labels[dia],
            'fecha': week_dates[dia],
            'fecha_fmt': week_dates[dia].strftime('%d/%m'),
            'is_today': week_dates[dia] == today,
        }
        for dia in dias
    ]

    friday = monday + _td(days=4)

    return render(request, 'horario.html', {
        'page': 'horario',
        'horario': horario_obj,
        'descansos': descansos,
        'grid_rows': grid_rows,
        'dias': dias,
        'dias_info': dias_info,
        'week_offset': week_offset,
        'monday': monday,
        'friday': friday,
        'today': today,
        'has_conflicts': has_conflicts,
        'clases_count': len(clases_week),
        'cursos': cursos,
        'materia_choices': MATERIA_CHOICES,
        'week_offset_prev': week_offset - 1,
        'week_offset_next': week_offset + 1,
    })


@login_required
def guardar_horario(request):
    if request.method != 'POST':
        return redirect('horario')
    import datetime
    horario_obj, _ = HorarioAcademico.objects.get_or_create(usuario=request.user)
    hora_inicio = _parse_time(request.POST.get('hora_inicio'), datetime.time(6, 0))
    hora_fin = _parse_time(request.POST.get('hora_fin'), datetime.time(14, 0))
    if hora_fin <= hora_inicio:
        messages.error(request, 'La hora de fin de jornada debe ser posterior a la hora de inicio.')
        return redirect('horario')
    horario_obj.hora_inicio_jornada = hora_inicio
    horario_obj.hora_fin_jornada = hora_fin
    try:
        duracion = int(request.POST.get('duracion', 60))
        horario_obj.duracion_sesion = max(15, min(180, duracion))
    except (ValueError, TypeError):
        horario_obj.duracion_sesion = 60
    horario_obj.save()
    messages.success(request, 'Horario sincronizado con éxito.')
    return redirect('horario')


@login_required
def guardar_bloque(request):
    if request.method != 'POST':
        return redirect('horario')
    import datetime
    horario_obj, _ = HorarioAcademico.objects.get_or_create(usuario=request.user)
    nombre = (request.POST.get('nombre') or '').strip()[:100]
    if not nombre:
        messages.error(request, 'El bloque de descanso necesita un nombre.')
        return redirect('horario')
    h_inicio = _parse_time(request.POST.get('hora_inicio'), datetime.time(10, 0))
    h_fin = _parse_time(request.POST.get('hora_fin'), datetime.time(10, 30))
    if h_inicio >= h_fin:
        messages.error(request, 'La hora de inicio debe ser anterior a la hora de fin.')
        return redirect('horario')
    if h_inicio < horario_obj.hora_inicio_jornada or h_fin > horario_obj.hora_fin_jornada:
        messages.error(
            request,
            f'El bloque debe estar dentro de la jornada '
            f'({horario_obj.hora_inicio_jornada.strftime("%H:%M")}–{horario_obj.hora_fin_jornada.strftime("%H:%M")}).'
        )
        return redirect('horario')
    BloqueDescanso.objects.create(horario=horario_obj, nombre=nombre, hora_inicio=h_inicio, hora_fin=h_fin)
    messages.success(request, f'Bloque "{nombre}" agregado.')
    return redirect('horario')


@login_required
def eliminar_bloque(request, id):
    if request.method != 'POST':
        return redirect('horario')
    bloque = get_object_or_404(BloqueDescanso, id=id, horario__usuario=request.user)
    nombre = bloque.nombre
    bloque.delete()
    messages.success(request, f'Bloque "{nombre}" eliminado.')
    return redirect('horario')


# ==================== ASISTENTE IA ====================

@login_required
def asistente(request):
    clases = Clase.objects.filter(usuario=request.user).order_by('-fecha_creacion')
    return render(request, 'asistente.html', {
        'page': 'asistente',
        'clases': clases,
        'tiene_clases': clases.exists(),
    })


@login_required
@rate_limit('asistente', max_calls=10, window_sec=60)
def asistente_api(request):
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Método no permitido'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'JSON inválido'}, status=400)

    clase_id = data.get('clase_id')
    clase_manual = data.get('clase_manual', {})
    contexto = data.get('contexto', '').strip()
    nivel = data.get('nivel', 'Secundaria')

    teacher_materia = get_user_materia(request.user)

    if clase_id:
        try:
            clase = Clase.objects.get(id=clase_id, usuario=request.user)
            class_info = {
                'titulo': clase.titulo,
                'materia': clase.materia or teacher_materia,
                'tema_notas': clase.notas or '',
                'grado': clase.grado_nombre or '',
                'tipo': (clase.get_tipo_clase_display() if clase.tipo_clase else 'Normal'),
            }
        except Clase.DoesNotExist:
            return JsonResponse({'ok': False, 'error': 'Clase no encontrada'}, status=404)
    else:
        class_info = {
            'titulo': clase_manual.get('titulo', 'Sin título'),
            'materia': clase_manual.get('materia', '') or teacher_materia,
            'tema_notas': clase_manual.get('objetivos', ''),
            'grado': '',
            'tipo': 'Normal',
        }

    notas_usuario = Nota.objects.filter(usuario=request.user).order_by('-fecha_creacion')[:3]
    notas_ctx = '\n'.join(f"- {n.titulo}: {n.contenido[:200]}" for n in notas_usuario) if notas_usuario else 'Ninguna.'

    prompt_usuario = (
        f"Clase: {class_info['titulo']}\n"
        f"Materia: {class_info['materia']}\n"
        f"Nivel educativo: {nivel}\n"
        f"Grado/Grupo: {class_info['grado']}\n"
        f"Tipo de clase: {class_info['tipo']}\n"
        f"Notas/Ideas del docente sobre el tema: {class_info['tema_notas'] or 'No especificadas.'}\n"
        f"Contexto adicional del docente: {contexto or 'No especificado.'}\n"
        f"Notas personales recientes del docente:\n{notas_ctx}"
    )

    materia_docente = class_info['materia'] or teacher_materia
    filtro_materia = (
        f"IMPORTANTE: Este docente enseña {materia_docente}. "
        f"TODAS las actividades, recursos y sugerencias deben ser EXCLUSIVAMENTE para la materia {materia_docente}. "
        f"No sugieras contenido de otras materias. "
    ) if materia_docente else ""

    system_prompt = (
        "Eres un asistente pedagógico especializado en apoyo docente. "
        f"{filtro_materia}"
        "Tu tarea es generar propuestas de clase completas, creativas y prácticas. "
        "Responde ÚNICAMENTE con un objeto JSON válido, sin texto extra ni markdown. "
        "El JSON debe tener exactamente esta estructura:\n"
        "{\n"
        '  "actividades": {\n'
        '    "inicio": {"titulo": "...", "descripcion": "...", "duracion": "X min", "materiales": "..."},\n'
        '    "desarrollo": {"titulo": "...", "descripcion": "...", "duracion": "X min", "materiales": "..."},\n'
        '    "cierre": {"titulo": "...", "descripcion": "...", "duracion": "X min", "materiales": "..."}\n'
        '  },\n'
        '  "evaluacion": {"titulo": "...", "descripcion": "...", "instrumento": "..."},\n'
        '  "recursos": [\n'
        '    {"tipo": "libro|video|herramienta|actividad|web", "titulo": "...", "descripcion": "..."},\n'
        '    {"tipo": "...", "titulo": "...", "descripcion": "..."},\n'
        '    {"tipo": "...", "titulo": "...", "descripcion": "..."}\n'
        '  ],\n'
        '  "mensaje": "Mensaje empático y motivacional para el docente (máx 2 oraciones)"\n'
        "}\n"
        "Usa tono profesional, creativo y empático. Adapta todo al nivel educativo indicado."
    )

    ok, payload, status = ai_generate(system_prompt, prompt_usuario, max_tokens=2048)
    if ok:
        return JsonResponse({'ok': True, 'data': payload})
    return JsonResponse({'ok': False, **payload}, status=status)


# ==================== CREAR CLASE CON IA (Plantilla 4) ====================

# Methodology → tone instruction injected into the LLM prompt so the generated
# Ficha del Estudiante / Guía del Docente matches the chosen teaching style.
_METODOLOGIA_TONO = {
    'normal': (
        'Metodología NORMAL (estructura académica estándar): redacta con rigor '
        'técnico-formal. Secuencia expositiva clásica: activación de saberes → '
        'desarrollo conceptual → práctica guiada → cierre evaluativo.'
    ),
    'dinamica': (
        'Metodología DINÁMICA (práctica y participativa): prioriza aprendizaje '
        'activo — trabajo colaborativo, juego didáctico, manipulación y '
        'construcción por parte del estudiante. Tono motivador pero técnico.'
    ),
    'mixta': (
        'Metodología MIXTA (híbrida): equilibra un bloque teórico formal con un '
        'bloque práctico aplicado. Articula explícitamente la transferencia '
        'teoría → aplicación.'
    ),
}


@login_required
@rate_limit('clase_ia_plan', max_calls=8, window_sec=60)
def clase_ia_plan(request):
    """Genera Objetivos + Observaciones para el wizard de creación de clase.

    Recibe tema, metodología, curso y día/hora; valida contra el Horario
    Académico (jornada, solapamiento, fin de semana, fecha pasada) reusando la
    misma lógica del formulario, y devuelve texto pedagógico alineado a la
    Taxonomía de Bloom. No persiste nada: el guardado real lo hace crear_clase.
    """
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Método no permitido'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'JSON inválido'}, status=400)

    tema = (data.get('tema') or '').strip()[:300]
    metodologia = (data.get('metodologia') or 'normal').strip().lower()
    curso_id = data.get('curso_id')
    fecha_str = (data.get('fecha') or '').strip()
    hora_str = (data.get('hora') or '').strip()

    if not tema:
        return JsonResponse({'ok': False, 'error': 'Indica el tema de la clase.'}, status=400)
    if metodologia not in _METODOLOGIA_TONO:
        return JsonResponse({'ok': False, 'error': 'Metodología no válida.'}, status=400)

    try:
        curso = Curso.objects.get(id=curso_id, usuario=request.user)
    except (Curso.DoesNotExist, ValueError, TypeError):
        return JsonResponse({'ok': False, 'error': 'Selecciona un curso válido.'}, status=400)

    # --- Validación de día/hora (misma lógica que ClaseForm + horario) ---
    from datetime import datetime as _dt
    try:
        fecha = _dt.strptime(fecha_str, '%Y-%m-%d').date()
        hora = _dt.strptime(hora_str, '%H:%M').time()
    except (ValueError, TypeError):
        return JsonResponse({'ok': False, 'error': 'Día u hora con formato inválido.'}, status=400)

    if fecha.weekday() >= 5:
        return JsonResponse({'ok': False, 'error': 'No se pueden programar clases en fin de semana.'}, status=400)
    if fecha < timezone.now().date():
        return JsonResponse({'ok': False, 'error': 'La fecha no puede ser anterior a hoy.'}, status=400)
    if fecha == timezone.now().date() and hora <= timezone.localtime().time():
        return JsonResponse({'ok': False, 'error': 'La hora ya pasó. Elige una hora futura para hoy.'}, status=400)

    # _validar_clase_horario usa select_for_update → debe ir dentro de atomic.
    try:
        with transaction.atomic():
            ok_h, err_h = _validar_clase_horario(request.user, fecha, hora)
        if not ok_h:
            return JsonResponse({'ok': False, 'error': err_h}, status=400)
    except Exception as e:
        logger.warning('clase_ia_plan: validación horario falló: %s', e)

    materia = get_user_materia(request.user) or 'General'
    grupo = curso.nombre
    nivel = curso.nivel_academico or 'No especificado'
    tono = _METODOLOGIA_TONO[metodologia]

    system_prompt = (
        'Eres un asesor pedagógico experto en diseño curricular y en la '
        'Taxonomía de Bloom revisada (Recordar, Comprender, Aplicar, Analizar, '
        'Evaluar, Crear). Generas la planificación de una sesión de clase. '
        f'{tono} '
        f'La sesión es de la materia {materia}, para el grupo {grupo} '
        f'(nivel: {nivel}). '
        'Responde ÚNICAMENTE con un objeto JSON válido, sin markdown ni texto '
        'extra, con esta estructura EXACTA:\n'
        '{\n'
        '  "objetivos": "Texto con 2 a 4 objetivos de aprendizaje redactados '
        'con verbos de la Taxonomía de Bloom (uno por línea, con guion). '
        'Lenguaje técnico-pedagógico.",\n'
        '  "observaciones": "Texto con la secuencia metodológica, la '
        'distribución de tiempo aproximada, materiales/recursos y '
        'recomendaciones de evaluación, coherente con la metodología indicada."\n'
        '}'
    )
    user_prompt = (
        f'Tema de la clase: {tema}\n'
        f'Materia: {materia}\nGrupo: {grupo}\nNivel: {nivel}\n'
        f'Metodología seleccionada: {metodologia}\n'
        'Redacta los objetivos y las observaciones para esta sesión.'
    )

    ok, payload, status = ai_generate(system_prompt, user_prompt, max_tokens=1200)
    if not ok:
        return JsonResponse({'ok': False, **payload}, status=status)

    # El LLM puede devolver un JSON que no sea un objeto (array/string); no
    # asumas .get sobre algo que no es dict → evita un AttributeError → 500.
    if not isinstance(payload, dict):
        logger.warning('clase_ia_plan: payload IA no es dict: %r', type(payload))
        return JsonResponse(
            {'ok': False, 'error': 'La IA devolvió un formato inesperado. Intenta de nuevo.'},
            status=502,
        )

    objetivos = (payload.get('objetivos') or '').strip()
    observaciones = (payload.get('observaciones') or payload.get('notas') or '').strip()
    if not objetivos and not observaciones:
        return JsonResponse(
            {'ok': False, 'error': 'La IA no devolvió contenido utilizable. Intenta de nuevo.'},
            status=502,
        )

    logger.info('clase_ia_plan OK user=%s tema="%s" metodo=%s',
                request.user.username, tema[:60], metodologia)
    return JsonResponse({
        'ok': True,
        'objetivos': objetivos[:5000],
        'notas': observaciones[:10000],
        'titulo': tema[:200],
        'tipo_clase': metodologia,
        'curso_id': curso.id,
        'grado_nombre': curso.nombre,
        'fecha': fecha_str,
        'hora_inicio': hora_str,
    })


# ==================== AI PEDAGOGICAL LAB ====================

LAB_MODOS = {
    'quiz': {
        'label': 'Evaluación Diagnóstica',
        'icon': 'quiz',
        'descripcion': 'Instrumento diagnóstico de 5 ítems que activan los niveles Analizar y Evaluar de la Taxonomía de Bloom, con retroalimentación metacognitiva.',
        'color': 'indigo',
    },
    'refuerzo': {
        'label': 'Taller de Profundización',
        'icon': 'refuerzo',
        'descripcion': 'Secuencia didáctica de 6 problemas graduados que movilizan los niveles Aplicar y Analizar. Rigor académico sin simplificaciones.',
        'color': 'pink',
    },
    'desafio': {
        'label': 'Problema de Alta Complejidad',
        'icon': 'desafio',
        'descripcion': 'Situación problema de orden superior (Sintetizar, Evaluar, Crear) para estudiantes con dominio avanzado del contenido.',
        'color': 'green',
    },
    'guia': {
        'label': 'Guía de Contenido Temático',
        'icon': 'guia',
        'descripcion': 'Texto teórico amplio y autosuficiente para el estudiante: marco conceptual, desarrollo desglosado, ejemplos graduales resueltos paso a paso y matriz de lectura crítica.',
        'color': 'amber',
    },
}


@login_required
def lab(request):
    cursos = Curso.objects.filter(usuario=request.user)
    preset_modo = request.GET.get('modo', 'quiz')
    if preset_modo not in LAB_MODOS:
        preset_modo = 'quiz'
    preset_curso = request.GET.get('curso', '').strip()
    preset_tema = request.GET.get('tema', '').strip()
    preset_grado = request.GET.get('grado', '').strip()
    return render(request, 'lab.html', {
        'page': 'lab',
        'cursos': cursos,
        'materia_doc': get_user_materia(request.user),
        'modos': LAB_MODOS,
        'preset_modo': preset_modo,
        'preset_curso': preset_curso,
        'preset_tema': preset_tema,
        'preset_grado': preset_grado,
    })


@login_required
@rate_limit('lab', max_calls=10, window_sec=60)
def lab_api(request):
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Método no permitido'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'JSON inválido'}, status=400)

    modo = data.get('modo', 'quiz')
    if modo not in LAB_MODOS:
        return JsonResponse({'ok': False, 'error': 'Modo no válido'}, status=400)

    materia = (data.get('materia') or get_user_materia(request.user) or 'Matemáticas').strip()
    grado = (data.get('grado') or '').strip()
    tema = (data.get('tema') or '').strip()
    objetivos = (data.get('objetivos') or '').strip()

    # ── Validaciones CONDICIONALES por modo ──────────────────────────────
    # Tema es obligatorio en TODOS los modos (sin él la IA no tiene foco).
    if not tema:
        return JsonResponse({
            'ok': False,
            'error': 'Indica el tema central del recurso.',
        }, status=400)

    # Campos específicos de quiz/refuerzo/desafio
    nivel = (data.get('nivel') or 'intermedio').strip()
    try:
        cantidad_preguntas = int(data.get('cantidad_preguntas') or 0)
    except (ValueError, TypeError):
        cantidad_preguntas = 0
    formato_preguntas = (data.get('formato_preguntas') or 'multiple').strip()
    if formato_preguntas not in ('multiple', 'desarrollo', 'emparejamiento'):
        formato_preguntas = 'multiple'

    # Nivel cognitivo NO es requerido para guía — saltar validación si vacío
    if modo != 'guia':
        NIVEL_SPEC = {
            'basico': 'Exploratorio — niveles Recordar y Comprender de Bloom. Apto para introducción inicial al tema.',
            'intermedio': 'Aplicativo — niveles Aplicar y Analizar de Bloom. Exige transferir el concepto a situaciones nuevas.',
            'avanzado': 'Crítico/Evaluativo — niveles Evaluar y Crear de Bloom. Demanda juicio fundamentado y construcción original.',
        }
        nivel_spec = NIVEL_SPEC.get(nivel, NIVEL_SPEC['intermedio'])
    else:
        nivel_spec = ''

    ctx_parts = [f'Materia: {materia}']
    if grado: ctx_parts.append(f'Grado/Sección: {grado}')
    if tema: ctx_parts.append(f'Tema central: {tema}')
    if objetivos: ctx_parts.append(f'Objetivos pedagógicos: {objetivos}')
    if nivel_spec: ctx_parts.append(f'Nivel cognitivo objetivo: {nivel_spec}')
    contexto = '\n'.join(ctx_parts)

    # Lineamientos comunes a quiz/refuerzo/desafio (instrumentos evaluativos)
    lineamientos_evaluativos = (
        "LINEAMIENTOS OBLIGATORIOS: "
        "(1) CONTEXTUALIZACIÓN REAL — todo enunciado debe partir de una situación verificable del mundo real "
        "(industria, ciencia, vida cotidiana, fenómenos sociales o naturales), nunca abstracciones desnudas. "
        "(2) DISTRACTORES INTELIGENTES — en opciones de respuesta, los distractores deben corresponder a "
        "errores conceptuales o procedimentales documentados que los estudiantes cometen comúnmente en este tema; "
        "prohibidas las opciones triviales, absurdas o claramente descartables por intuición. "
        "(3) RIGOR ACADÉMICO — lenguaje técnico y formal, sin tono lúdico ni infantil, sin emojis. "
        "(4) JUSTIFICACIÓN PEDAGÓGICA — cada respuesta correcta debe acompañarse de una explicación que "
        "habilite al docente a dar retroalimentación de calidad. "
    )

    if modo == 'quiz':
        n_items = cantidad_preguntas if 3 <= cantidad_preguntas <= 20 else 5
        # ~500 tokens per question (enunciado + 4 opciones + justificación + distractores)
        max_tokens = min(8192, max(2048, n_items * 500 + 400))
        fmt_label = {
            'multiple': 'ítems de opción múltiple (4 opciones por pregunta)',
            'desarrollo': 'ítems de desarrollo (pregunta abierta con rúbrica)',
            'emparejamiento': 'ítems de emparejamiento (dos columnas A↔B)',
        }[formato_preguntas]
        system_prompt = (
            f"Eres un evaluador educativo experto en Taxonomía de Bloom revisada y en análisis de errores "
            f"conceptuales documentados por la investigación didáctica. "
            f"Diseña una Evaluación Diagnóstica de {n_items} {fmt_label}, ajustada al nivel cognitivo indicado. "
            + lineamientos_evaluativos +
            "Devuelve SOLO JSON válido sin comentarios ni markdown con este esquema exacto: "
            '{"titulo": "Evaluación Diagnóstica — [Tema]", "preguntas": [{"enunciado": "Situación real + pregunta…", '
            '"opciones": ["…","…","…","…"], "correcta": 0, '
            '"justificacion": "Por qué la opción correcta es correcta + fundamento Bloom", '
            '"errores_distractores": ["Error conceptual que revela la opción A", "Error que revela B", '
            '"Error que revela C", "Error que revela D"]}]}. '
            'En errores_distractores, la posición correspondiente a la opción correcta puede contener "—". '
            'correcta es índice 0–3.'
        )
        user_prompt = f"{contexto}\nGenera la Evaluación Diagnóstica de {n_items} ítems."
    elif modo == 'refuerzo':
        n_items = cantidad_preguntas if 3 <= cantidad_preguntas <= 20 else 6
        # ~650 tokens per exercise (enunciado + pista + solución paso a paso)
        max_tokens = min(8192, max(2048, n_items * 650 + 400))
        system_prompt = (
            f"Eres un especialista en diseño curricular basado en la Taxonomía de Bloom revisada. "
            f"Diseña un Taller de Profundización con {n_items} problemas de aplicación graduados, ajustados al nivel "
            f"cognitivo indicado. Cada problema debe exigir procedimiento explícito y reflexión metodológica. "
            + lineamientos_evaluativos +
            "Devuelve SOLO JSON válido sin markdown: "
            '{"titulo": "Taller de Profundización — [Tema]", "introduccion": "Contextualización académica del taller…", '
            '"ejercicios": [{"enunciado": "Situación real + consigna…", '
            '"pista": "Orientación metodológica que el estudiante puede consultar", '
            '"solucion": "Desarrollo paso a paso con justificación procedimental para el docente"}]}.'
        )
        user_prompt = f"{contexto}\nGenera el Taller de Profundización con {n_items} problemas."
    elif modo == 'desafio':
        max_tokens = 2048
        system_prompt = (
            "Eres un diseñador de olimpiadas académicas y situaciones problema de alto nivel cognitivo. "
            "Construye UN Problema de Aplicación de Alta Complejidad ajustado al nivel cognitivo indicado, "
            "que requiera análisis multifactorial, modelación y justificación epistemológica. "
            + lineamientos_evaluativos +
            "Devuelve SOLO JSON válido: "
            '{"titulo": "Problema de Aplicación de Alta Complejidad — [Tema]", "problema": "Situación real compleja…", '
            '"pistas": ["Orientación 1 para el estudiante…", "Orientación 2…", "Orientación 3…"], '
            '"solucion_detallada": "Desarrollo paso a paso con justificación pedagógica para el docente"}.'
        )
        user_prompt = f"{contexto}\nGenera el Problema de Aplicación de Alta Complejidad."
    else:  # ─────────── modo == 'guia' ───────────
        # Motor de Generación de Guías de Contenido Temático — V5
        # Genera texto teórico autosuficiente destinado AL ESTUDIANTE.
        # PROHIBIDO: fases docentes, instrucciones de aula, secuencias Inicio/Desarrollo/Cierre.
        max_tokens = 8192

        system_prompt = (
            "Eres un experto en Didáctica del Contenido y Redacción Académica. "
            "Tu tarea es construir una GUÍA DE CONTENIDO TEÓRICO AMPLIA, RIGUROSA Y AUTOSUFICIENTE "
            "destinada al estudiante. El texto explica el tema en profundidad para que el lector "
            "pueda dominarlo sin depender de un docente.\n\n"

            "[INSTRUCCIÓN DE CONTROL ESTRICTA]: Bajo ninguna circunstancia generes únicamente "
            "títulos o esquemas de secciones. Cada campo de texto del JSON DEBE contener un mínimo "
            "de 3 a 5 párrafos extensos de contenido teórico puro y explicativo. Si dejas un campo "
            "vacío o con menos de 200 palabras, la ejecución se considerará fallida. "
            "Desarrolla los ejemplos paso a paso de forma completamente explícita.\n\n"

            "PROHIBICIÓN ABSOLUTA: Queda completamente prohibido incluir secciones como "
            "'Fase de Inicio', 'Fase de Desarrollo', 'Fase de Cierre', 'Instrucciones para el docente', "
            "'Duración de la sesión' o cualquier referencia a cómo dictar la clase. "
            "El texto NO le habla al profesor; explica el tema directamente al estudiante.\n\n"

            "DIRECTRICES DE POTENCIA:\n"
            "(1) DENSIDAD MÁXIMA — párrafos largos y bien conectados. "
            "Prohibidos bullets superficiales en los campos de texto principal.\n"
            "(2) RIGOR ACADÉMICO — terminología precisa, sin tono lúdico, sin emojis.\n"
            "(3) PROGRESIÓN LÓGICA — del concepto abstracto a la aplicación concreta.\n"
            "(4) EJEMPLOS COMPLETAMENTE RESUELTOS — cada paso justificado explícitamente.\n"
            "(5) MATRIZ BASADA EN EL TEXTO GENERADO — las preguntas de la matriz deben surgir "
            "EXCLUSIVAMENTE del contenido de los campos anteriores.\n\n"

            "ESTRUCTURA OBLIGATORIA — devuelve SOLO JSON válido con EXACTAMENTE estas claves "
            "en el nivel raíz (no anides objetos para los campos de texto extenso):\n\n"
            '{\n'
            '  "titulo": "Guía de Contenido Teórico: [Tema específico]",\n'
            '  "introduccion_narrativa": "TEXTO EXTENSO: 4-6 párrafos que contextualizan el tema de forma atractiva para el estudiante. Mostrar relevancia en el mundo real. Enganchar desde la primera línea. Cada párrafo separado por \\n\\n.",\n'
            '  "definicion_tecnica": "TEXTO EXTENSO: definición formal y rigurosa con todos sus componentes esenciales. Distinguir de conceptos relacionados. Incluir terminología disciplinar precisa. Mínimo 3 párrafos.",\n'
            '  "utilidad_vida_real": "TEXTO EXTENSO: 3-5 párrafos con aplicaciones históricas, científicas, tecnológicas y cotidianas. Al menos un referente histórico y dos aplicaciones contemporáneas concretas.",\n'
            '  "desarrollo_teorico": "TEXTO MUY EXTENSO: mínimo 8-12 párrafos densos que desarrollan sistemáticamente propiedades, reglas, fórmulas y sus derivaciones lógicas. Usar TITULO EN MAYUSCULAS como separador de subtemas dentro del mismo string. Párrafos separados por \\n\\n.",\n'
            '  "representaciones": [\n'
            '    "REPRESENTACION 1 — [título descriptivo]: esquema ASCII, tabla o expresión simbólica seguida de su explicación pedagógica de 2-3 líneas",\n'
            '    "REPRESENTACION 2 — [título descriptivo]: ...",\n'
            '    "REPRESENTACION 3 — [título descriptivo]: ..."\n'
            '  ],\n'
            '  "ejemplos_introductorios": [\n'
            '    {"enunciado": "Situación sencilla e intuitiva con datos concretos.", "resolucion": "Paso 1: [acción] — [justificación de la propiedad usada]\\nPaso 2: [acción] — [justificación]\\n...\\nPaso N: [resultado final con interpretación]. Mínimo 10 pasos explícitos."},\n'
            '    {"enunciado": "Segundo ejemplo introductorio en contexto diferente.", "resolucion": "Resolución completa con el mismo nivel de detalle."}\n'
            '  ],\n'
            '  "ejemplos_avanzados": [\n'
            '    {"enunciado": "Problema complejo con múltiples condiciones que requieren articular varias propiedades.", "resolucion": "ANÁLISIS PREVIO: [identificar variables y estrategia]\\nPaso 1: ...\\nPaso 2: ...\\n...\\nVERIFICACIÓN: [comprobar el resultado]\\nCONCLUSIÓN: [interpretación argumentada]. Mínimo 15 pasos."},\n'
            '    {"enunciado": "Segundo ejemplo avanzado en contexto diferente al primero.", "resolucion": "Resolución completa con análisis, desarrollo, verificación y conclusión."}\n'
            '  ],\n'
            '  "matriz_analitica": [\n'
            '    {"dimension": "Dimensión conceptual evaluada (ej: Definición formal)", "pregunta_lectura": "Pregunta de comprensión profunda basada en el texto generado arriba", "indicador_respuesta": "Qué debe contener la respuesta para demostrar comprensión real"},\n'
            '    "(repetir — mínimo 6 filas, una por cada dimensión clave del contenido)"\n'
            '  ],\n'
            '  "bibliografia": [\n'
            '    "Apellido, N. (año). Título. Editorial. — referencia mundial",\n'
            '    "Apellido, N. (año). Título. Editorial. — referencia latinoamericana",\n'
            '    "Referencia adicional APA 7"\n'
            '  ]\n'
            '}'
        )

        user_prompt = (
            f"{contexto}\n\n"
            f"Genera la Guía de Contenido Teórico COMPLETA sobre '{tema}'. "
            "RELLENA CADA CAMPO DE TEXTO CON CONTENIDO REAL Y EXTENSO — no con descripciones "
            "de lo que debería ir ahí. "
            "Los campos introduccion_narrativa, definicion_tecnica, utilidad_vida_real y "
            "desarrollo_teorico deben contener el texto académico real, no instrucciones. "
            "NO ABREVIES. NO DEJES CAMPOS VACIOS. DESARROLLA CADA EJEMPLO PASO A PASO."
        )

    temperature = 0.3 if modo == 'guia' else 0.7
    ok, payload, status = ai_generate(system_prompt, user_prompt, max_tokens=max_tokens, temperature=temperature)
    if ok:
        return JsonResponse({'ok': True, 'modo': modo, 'data': payload})
    return JsonResponse({'ok': False, **payload}, status=status)


@login_required
@rate_limit('lab_save', max_calls=20, window_sec=60)
def lab_guardar_recurso(request):
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Método no permitido'}, status=405)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'JSON inválido'}, status=400)
    titulo = (data.get('titulo') or '').strip()[:200]
    contenido = (data.get('contenido') or '').strip()[:5000]
    if not titulo or not contenido:
        return JsonResponse({'ok': False, 'error': 'Título y contenido son obligatorios'}, status=400)
    # Strip HTML tags to prevent stored XSS if descripcion is ever rendered via |safe.
    from django.utils.html import strip_tags
    recurso = Recurso.objects.create(
        usuario=request.user,
        titulo=strip_tags(titulo)[:200],
        tipo='documento',
        descripcion=strip_tags(contenido)[:5000],
    )
    return JsonResponse({'ok': True, 'recurso_id': recurso.id})


# ==================== EXPORTACIÓN A PDF ====================

def _render_pdf_from_html(html_source):
    """HTML → PDF en memoria usando xhtml2pdf (Python puro).
    Returns (ok, bytes_or_error_msg)."""
    try:
        from xhtml2pdf import pisa
    except ImportError:
        return False, 'Falta instalar xhtml2pdf: pip install xhtml2pdf'
    import io
    buf = io.BytesIO()
    result = pisa.CreatePDF(src=html_source, dest=buf, encoding='utf-8')
    if result.err:
        return False, 'Error al renderizar el PDF.'
    return True, buf.getvalue()


def _slug_filename(s, fallback='archivo'):
    import re
    s = re.sub(r'[^A-Za-zÁÉÍÓÚáéíóúÑñ0-9]+', '_', s or '').strip('_')
    return (s or fallback)[:80]


def _unique_filename(base, ext):
    """Construye un nombre de archivo único añadiendo timestamp + UUID corto.
    Garantiza que dos usuarios generando 'Taller_Mate.pdf' simultáneamente NUNCA
    colisionen a nivel de storage, incluso sin la protección de `get_available_name`.

    Formato: <base>_<YYYYMMDD-HHMMSS>_<uuid8>.<ext>
    Ejemplo: PlanClase_10A_Funciones_20260523-104512_a3f9c2e1.pdf
    """
    import uuid
    import datetime as _dt
    ts = _dt.datetime.now().strftime('%Y%m%d-%H%M%S')
    suffix = uuid.uuid4().hex[:8]
    return f'{base}_{ts}_{suffix}.{ext}'


def _resolver_curso_clase(user, clase_id=None, curso_id=None):
    """Resuelve (curso, clase) garantizando consistencia A↔B.

    Reglas:
      - Si llega clase_id: se prioriza. El curso se DERIVA del grado_nombre
        de la clase (ignorando un curso_id contradictorio del cliente).
      - Si solo llega curso_id: se valida y se usa.
      - Si ambos están vacíos o son ajenos: devuelve (None, None).

    Esto blinda contra que un docente envíe deliberadamente curso=3°A
    con clase=3°B y termine creando recursos cruzados entre grupos.
    """
    clase = None
    if clase_id:
        try:
            clase = Clase.objects.filter(id=int(clase_id), usuario=user).first()
        except (ValueError, TypeError):
            clase = None

    curso = None
    if clase is not None and clase.grado_nombre:
        # Deriva el curso desde la clase — fuente de verdad
        curso = Curso.objects.filter(
            usuario=user, nombre=clase.grado_nombre
        ).first()
    elif curso_id:
        try:
            curso = Curso.objects.filter(id=int(curso_id), usuario=user).first()
        except (ValueError, TypeError):
            curso = None

    if (clase_id and not clase) or (curso_id and not curso and not clase):
        logger.warning(
            'Lab guardar: usuario %s envió ids ajenos/inexistentes (clase_id=%s curso_id=%s)',
            user.username, clase_id, curso_id,
        )

    return curso, clase


@login_required
def clase_pdf(request, id):
    """Exporta una clase planificada como PDF profesional optimizado para
    impresión en blanco y negro. Verifica propiedad estricta."""
    clase = get_object_or_404(Clase, id=id, usuario=request.user)
    horario_obj = getattr(request.user, 'horario_academico', None)
    duracion_total = _session_duration_min(request.user)

    # Distribución pedagógica 20/55/25 redondeada a 5 min
    def _round5(n):
        return int(round(n / 5.0) * 5) or 5
    inicio_min = _round5(duracion_total * 0.20)
    desarrollo_min = _round5(duracion_total * 0.55)
    cierre_min = duracion_total - inicio_min - desarrollo_min

    config = getattr(request.user, 'configuracion', None)
    institucion = (config.nombre_institucion if config else '') or 'Institución Educativa'
    cargo = config.cargo if config else ''

    html = render(request, 'clases/pdf.html', {
        'clase': clase,
        'institucion': institucion,
        'cargo': cargo,
        'docente_nombre': request.user.get_full_name() or request.user.username,
        'duracion_total': duracion_total,
        'inicio_min': inicio_min,
        'desarrollo_min': desarrollo_min,
        'cierre_min': cierre_min,
        'fecha_emision': timezone.now(),
    }).content.decode('utf-8')

    ok, payload = _render_pdf_from_html(html)
    if not ok:
        from django.http import HttpResponse
        return HttpResponse(payload, status=500, content_type='text/plain; charset=utf-8')

    grupo = _slug_filename(clase.grado_nombre or 'GeneralS', 'Grupo')
    tema = _slug_filename(clase.titulo or 'Clase', 'Clase')
    filename = f'PlanClase_{grupo}_{tema}.pdf'

    from django.http import HttpResponse
    resp = HttpResponse(payload, content_type='application/pdf')
    resp['Content-Disposition'] = f'attachment; filename="{filename}"'
    return resp


@login_required
@rate_limit('clase_pdf_save', max_calls=10, window_sec=60)
def clase_pdf_guardar(request, id):
    """Genera el PDF de la clase y lo persiste como Recurso (tipo plan_pdf)
    vinculado al docente, la clase y el curso. Verifica propiedad."""
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Método no permitido'}, status=405)
    from django.core.files.base import ContentFile

    clase = get_object_or_404(Clase, id=id, usuario=request.user)
    duracion_total = _session_duration_min(request.user)
    def _round5(n):
        return int(round(n / 5.0) * 5) or 5
    inicio_min = _round5(duracion_total * 0.20)
    desarrollo_min = _round5(duracion_total * 0.55)
    cierre_min = duracion_total - inicio_min - desarrollo_min
    config = getattr(request.user, 'configuracion', None)

    try:
        html = render(request, 'clases/pdf.html', {
            'clase': clase,
            'institucion': (config.nombre_institucion if config else '') or 'Institución Educativa',
            'cargo': config.cargo if config else '',
            'docente_nombre': request.user.get_full_name() or request.user.username,
            'duracion_total': duracion_total,
            'inicio_min': inicio_min,
            'desarrollo_min': desarrollo_min,
            'cierre_min': cierre_min,
            'fecha_emision': timezone.now(),
        }).content.decode('utf-8')
    except Exception as e:
        logger.error('clase_pdf_guardar: error renderizando template: %s', e)
        return JsonResponse({'ok': False, 'error': 'Error al preparar el PDF. Intenta de nuevo.'}, status=500)

    ok, payload = _render_pdf_from_html(html)
    if not ok:
        return JsonResponse({'ok': False, 'error': payload}, status=500)

    try:
        curso_match = None
        if clase.grado_nombre:
            curso_match = Curso.objects.filter(
                usuario=request.user, nombre=clase.grado_nombre
            ).first()

        grupo = _slug_filename(clase.grado_nombre or 'General', 'Grupo')
        tema = _slug_filename(clase.titulo or 'Clase', 'Clase')
        filename = _unique_filename(f'PlanClase_{grupo}_{tema}', 'pdf')

        recurso = Recurso.objects.create(
            usuario=request.user,
            clase=clase,
            curso=curso_match,
            titulo=f'Plan de clase — {clase.titulo}'[:200],
            descripcion=f'Plan exportado para {clase.grado_nombre or "—"} · {clase.fecha}'[:5000],
            tipo='plan_pdf',
        )
        recurso.archivo.save(filename, ContentFile(payload), save=True)
    except Exception as e:
        logger.error('clase_pdf_guardar: error guardando recurso: %s', e)
        return JsonResponse({'ok': False, 'error': 'Error al guardar el recurso. Intenta de nuevo.'}, status=500)

    return JsonResponse({'ok': True, 'recurso_id': recurso.id, 'filename': filename})


# ==================== GUARDADO ENRIQUECIDO DESDE EL AI LAB ====================

def _build_lab_pdf_html(modo, data, ctx):
    """Construye el HTML completo (con estilos inline) que xhtml2pdf
    convertirá a PDF. Diseño limpio, optimizado para impresión B/N."""
    from django.template.loader import render_to_string
    return render_to_string('lab/pdf_documento.html', {
        'modo': modo,
        'data': data,
        'ctx': ctx,
    })


@login_required
@rate_limit('lab_save_pdf', max_calls=10, window_sec=60)
def lab_guardar_documento(request):
    """Guarda en Recursos el material generado por el AI Lab como PDF binario.
    Soporta los modos quiz, refuerzo, desafio, guia."""
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Método no permitido'}, status=405)
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'JSON inválido'}, status=400)

    modo = (body.get('modo') or '').strip()
    data = body.get('data') or {}
    if modo not in LAB_MODOS or not isinstance(data, dict):
        return JsonResponse({'ok': False, 'error': 'Modo o data inválidos'}, status=400)

    ctx = {
        'materia': (body.get('materia') or '').strip()[:80],
        'grado': (body.get('grado') or '').strip()[:80],
        'tema': (body.get('tema') or '').strip()[:200],
        'docente': request.user.get_full_name() or request.user.username,
        'fecha': timezone.now(),
        'modo_label': LAB_MODOS[modo]['label'],
    }
    curso_match, clase_match = _resolver_curso_clase(
        request.user,
        clase_id=body.get('clase_id'),
        curso_id=body.get('curso_id'),
    )

    try:
        html = _build_lab_pdf_html(modo, data, ctx)
    except Exception as e:
        logger.error('lab_guardar_documento: error renderizando template PDF: %s', e, exc_info=True)
        return JsonResponse({'ok': False, 'error': 'Error al preparar el documento. Inténtalo de nuevo.'}, status=500)

    try:
        ok, payload = _render_pdf_from_html(html)
    except Exception as e:
        logger.error('lab_guardar_documento: error en xhtml2pdf: %s', e, exc_info=True)
        return JsonResponse({'ok': False, 'error': 'Error al generar el PDF. Inténtalo de nuevo.'}, status=500)
    if not ok:
        return JsonResponse({'ok': False, 'error': 'Error al generar el PDF. Inténtalo de nuevo.'}, status=500)

    from django.core.files.base import ContentFile
    from django.utils.html import strip_tags

    try:
        titulo = strip_tags(data.get('titulo') or LAB_MODOS[modo]['label'])[:200]
        tipo_map = {'quiz': 'quiz', 'refuerzo': 'taller', 'desafio': 'taller', 'guia': 'guia'}
        tipo = tipo_map.get(modo, 'documento')
        tipo_prefix = {'quiz': 'Evaluacion', 'refuerzo': 'Taller', 'desafio': 'Problema', 'guia': 'Guia'}[modo]
        grupo = _slug_filename(ctx['grado'] or 'General')
        tema = _slug_filename(ctx['tema'] or titulo)
        filename = _unique_filename(f'Recurso_{tipo_prefix}_{grupo}_{tema}', 'pdf')

        recurso = Recurso.objects.create(
            usuario=request.user,
            curso=curso_match,
            clase=clase_match,
            titulo=titulo,
            descripcion=f'{LAB_MODOS[modo]["label"]} · {ctx["materia"]} · {ctx["grado"] or "General"}'[:5000],
            tipo=tipo,
        )
        recurso.archivo.save(filename, ContentFile(payload), save=True)
    except Exception as e:
        logger.error('lab_guardar_documento: error guardando recurso: %s', e)
        return JsonResponse({'ok': False, 'error': 'Error al guardar el recurso. Intenta de nuevo.'}, status=500)

    return JsonResponse({'ok': True, 'recurso_id': recurso.id, 'filename': filename})


# ==================== TEST DE CORREO ====================

@login_required
def test_recordatorio_email(request):
    """Verifica que el SMTP esté configurado correctamente sin hacer conexión de red."""
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Método no permitido'}, status=405)

    from django.conf import settings as _cfg

    if getattr(_cfg, 'EMAIL_BACKEND', '').endswith('dummy.EmailBackend'):
        return JsonResponse({
            'ok': False,
            'error': 'SMTP no configurado. Agrega EMAIL_HOST_USER en las variables de entorno de Render.',
        }, status=503)

    email = (request.user.email or '').strip()
    if not email:
        return JsonResponse({
            'ok': False,
            'error': 'Tu cuenta no tiene correo registrado. Agrégalo en Ajustes → Perfil.',
        }, status=400)

    host = getattr(_cfg, 'EMAIL_HOST', 'smtp.gmail.com')
    user = getattr(_cfg, 'EMAIL_HOST_USER', '')
    return JsonResponse({
        'ok': True,
        'email': email,
        'detail': f'SMTP configurado: {user} → {host}. Los recordatorios diarios se enviarán a {email}.',
    })


# ==================== DESCARGA SEGURA DE RECURSOS ====================

def _serve_recurso(request, id, attachment):
    """Common implementation behind descargar_recurso / inline_recurso.
    Verifies ownership strictly. attachment=True forces download (.pdf, .png);
    attachment=False allows inline display (img previews)."""
    recurso = get_object_or_404(Recurso, id=id, usuario=request.user)
    if not recurso.archivo:
        from django.http import HttpResponseNotFound
        return HttpResponseNotFound('Este recurso no tiene archivo descargable.')

    from django.http import FileResponse
    try:
        f = recurso.archivo.open('rb')
    except FileNotFoundError:
        from django.http import HttpResponseNotFound
        return HttpResponseNotFound('El archivo físico se eliminó del servidor.')

    return FileResponse(
        f,
        as_attachment=attachment,
        filename=recurso.descarga_filename() if attachment else None,
    )


@login_required
def descargar_recurso(request, id):
    """Fuerza descarga (Content-Disposition: attachment) con nombre
    parametrizado. Verifica propiedad estricta (404 si no pertenece)."""
    return _serve_recurso(request, id, attachment=True)


@login_required
def inline_recurso(request, id):
    """Sirve el archivo INLINE para previews (<img>, <iframe>, etc.).
    Verifica propiedad estricta — esta es la única ruta segura para mostrar
    media en producción, ya que /media/ directo no aplica autorización."""
    return _serve_recurso(request, id, attachment=False)
