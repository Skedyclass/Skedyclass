"""
Django settings for SkedyClass project.
"""

import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Cargador de .env sin dependencias externas
# Las variables del sistema operativo tienen prioridad sobre el archivo .env
# ---------------------------------------------------------------------------
def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, val = line.partition('=')
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


_load_dotenv(BASE_DIR / '.env')


# ---------------------------------------------------------------------------
# SECRET_KEY — nunca hardcodeada
# Orden de preferencia: env var → .secret_key local → genera y persiste uno
# ---------------------------------------------------------------------------
def _get_secret_key() -> str:
    key = os.environ.get('SECRET_KEY', '').strip()
    if key:
        return key
    key_file = BASE_DIR / '.secret_key'
    if key_file.exists():
        return key_file.read_text().strip()
    key = secrets.token_hex(50)
    key_file.write_text(key)
    return key


SECRET_KEY = _get_secret_key()

# ---------------------------------------------------------------------------
# DEBUG — False por defecto; activar explícitamente con DEBUG=True en .env
# ---------------------------------------------------------------------------
DEBUG = os.environ.get('DEBUG', 'False').lower() in ('true', '1', 'yes')

# ---------------------------------------------------------------------------
# ALLOWED_HOSTS — lista separada por comas en env var
# ---------------------------------------------------------------------------
_hosts_raw = os.environ.get('ALLOWED_HOSTS', '127.0.0.1,localhost')
ALLOWED_HOSTS = [h.strip() for h in _hosts_raw.split(',') if h.strip()]

# ---------------------------------------------------------------------------
# CSRF_TRUSTED_ORIGINS — Django 4.x exige el esquema https:// para validar
# POST/AJAX en producción. Lista separada por comas en env var, p.ej.:
#   CSRF_TRUSTED_ORIGINS=https://skedyclass.com,https://www.skedyclass.com
# Si no se define, se derivan https://<host> desde ALLOWED_HOSTS (excepto local).
# ---------------------------------------------------------------------------
_csrf_raw = os.environ.get('CSRF_TRUSTED_ORIGINS', '').strip()
if _csrf_raw:
    CSRF_TRUSTED_ORIGINS = [o.strip() for o in _csrf_raw.split(',') if o.strip()]
else:
    CSRF_TRUSTED_ORIGINS = [
        f'https://{h}' for h in ALLOWED_HOSTS
        if h not in ('127.0.0.1', 'localhost') and not h.startswith('*')
    ]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    'planificador',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # WhiteNoise sirve los estáticos en producción (DEBUG=False) sin un CDN/nginx aparte.
    # Debe ir justo después de SecurityMiddleware.
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# ---------------------------------------------------------------------------
# Google OAuth via django-allauth (opcional — requiere `pip install django-allauth`)
# Setup:
#   1. pip install django-allauth
#   2. Añade en .env: GOOGLE_OAUTH_CLIENT_ID=... y GOOGLE_OAUTH_CLIENT_SECRET=...
#   3. python manage.py migrate
#   4. (opcional) En /admin/ crea un Site con domain 127.0.0.1:8000
# ---------------------------------------------------------------------------
SITE_ID = 1
try:
    import allauth  # noqa: F401
    INSTALLED_APPS += [
        'allauth',
        'allauth.account',
        'allauth.socialaccount',
        'allauth.socialaccount.providers.google',
    ]
    MIDDLEWARE += ['allauth.account.middleware.AccountMiddleware']
    AUTHENTICATION_BACKENDS = (
        'django.contrib.auth.backends.ModelBackend',
        'allauth.account.auth_backends.AuthenticationBackend',
    )
    SOCIALACCOUNT_PROVIDERS = {
        'google': {
            'APP': {
                'client_id': os.environ.get('GOOGLE_OAUTH_CLIENT_ID', ''),
                'secret': os.environ.get('GOOGLE_OAUTH_CLIENT_SECRET', ''),
                'key': '',
            },
            'SCOPE': [
                'profile',
                'email',
                'https://www.googleapis.com/auth/calendar.events',
            ],
            'AUTH_PARAMS': {'access_type': 'offline', 'prompt': 'consent'},
        }
    }
    SOCIALACCOUNT_LOGIN_ON_GET = True
    SOCIALACCOUNT_AUTO_SIGNUP = True
    SOCIALACCOUNT_EMAIL_AUTHENTICATION = True  # vincular por email si ya existe
    ACCOUNT_EMAIL_VERIFICATION = 'none'
    ACCOUNT_LOGIN_METHODS = {'username', 'email'}
    LOGIN_REDIRECT_URL = '/dashboard/'
    ACCOUNT_LOGOUT_REDIRECT_URL = '/'
    SOCIALACCOUNT_CONNECT_REDIRECT_URL = '/ajustes/?s=google_calendar'
except ImportError:
    pass

ROOT_URLCONF = 'skedyclass.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'planificador' / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'planificador.context_processors.user_config',
            ],
        },
    },
]

WSGI_APPLICATION = 'skedyclass.wsgi.application'

_database_url = os.environ.get('DATABASE_URL')
if _database_url:
    import urllib.parse
    _u = urllib.parse.urlparse(_database_url)
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': _u.path.lstrip('/'),
            'USER': _u.username,
            'PASSWORD': _u.password,
            'HOST': _u.hostname,
            'PORT': _u.port or 5432,
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'es-co'
TIME_ZONE = 'America/Bogota'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
# STATIC_ROOT — destino de `collectstatic` en producción (servido por WhiteNoise).
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Almacenamiento comprimido + hash de cache-busting para los estáticos en prod.
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ---------------------------------------------------------------------------
# Cookie/session hardening — relaxed in DEBUG, strict in production
# ---------------------------------------------------------------------------
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # JS needs to read it for AJAX X-CSRFToken
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

if not DEBUG:
    # Production-only flags. Set DEBUG=False in .env to activate.
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = os.environ.get('SECURE_SSL_REDIRECT', 'True').lower() in ('true', '1', 'yes')
    SECURE_HSTS_SECONDS = int(os.environ.get('SECURE_HSTS_SECONDS', '31536000'))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# API Keys
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
GEMINI_MODEL = os.environ.get('GEMINI_MODEL', 'gemini-2.0-flash')
GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')
GROQ_MODEL = os.environ.get('GROQ_MODEL', 'llama-3.3-70b-versatile')
AI_PROVIDER = os.environ.get('AI_PROVIDER', 'groq').lower()  # groq | gemini | anthropic

# ---------------------------------------------------------------------------
# SMTP — Correo para alertas académicas de bajo rendimiento
# Configura estas variables en tu archivo .env:
#   EMAIL_HOST_USER=tu_correo@gmail.com
#   EMAIL_HOST_PASSWORD=tu_contraseña_de_aplicación
#   DEFAULT_FROM_EMAIL=SkedyClass <tu_correo@gmail.com>
#
# Para Gmail necesitas una "Contraseña de aplicación" (App Password):
#   Google Account → Seguridad → Verificación en 2 pasos → Contraseñas de aplicación
#
# Para SendGrid: EMAIL_HOST=smtp.sendgrid.net, EMAIL_HOST_USER=apikey,
#                EMAIL_HOST_PASSWORD=<tu_api_key_de_sendgrid>
# ---------------------------------------------------------------------------
_email_user = os.environ.get('EMAIL_HOST_USER', '')
if _email_user:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
    EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
    EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True').lower() in ('true', '1', 'yes')
    EMAIL_HOST_USER = _email_user
    EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
    DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', f'SkedyClass <{_email_user}>')
else:
    EMAIL_BACKEND = 'django.core.mail.backends.dummy.EmailBackend'

# Configuración de Login
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'landing'

# #25 — Logging de acciones críticas
LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {
            'format': '{asctime} {levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'file': {
            'class': 'logging.FileHandler',
            'filename': LOGS_DIR / 'skedyclass.log',
            'formatter': 'simple',
            'encoding': 'utf-8',
        },
    },
    'loggers': {
        'planificador': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
