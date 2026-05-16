@echo off
chcp 65001 >nul
echo.
echo ========================================================
echo      SkedyClass - Planificador Magico
echo ========================================================
echo.

REM Verificar Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python no esta instalado.
    echo Descargalo de: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [OK] Python encontrado

REM Crear entorno virtual
if not exist "venv" (
    echo.
    echo Creando entorno virtual...
    python -m venv venv
    if errorlevel 1 (
        echo ERROR: No se pudo crear el entorno virtual
        pause
        exit /b 1
    )
    echo [OK] Entorno virtual creado
)

REM Activar entorno virtual
echo.
echo Activando entorno virtual...
call venv\Scripts\activate.bat

REM Instalar dependencias
echo.
echo Instalando dependencias (Django, IA, PDF)...
pip install --upgrade pip >nul 2>&1
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: No se pudieron instalar las dependencias
    pause
    exit /b 1
)
echo [OK] Dependencias instaladas correctamente

REM Ejecutar migraciones
echo.
echo Configurando base de datos...
python manage.py makemigrations planificador --noinput
python manage.py migrate --noinput
echo [OK] Base de datos configurada

REM Crear usuario usando script Python
echo.
echo Creando usuario administrador...

echo import os > _crear_usuario.py
echo import django >> _crear_usuario.py
echo os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'skedyclass.settings') >> _crear_usuario.py
echo django.setup() >> _crear_usuario.py
echo from django.contrib.auth.models import User >> _crear_usuario.py
echo username = 'profesor' >> _crear_usuario.py
echo password = 'skedy2026' >> _crear_usuario.py
echo email = 'profesor@skedyclass.com' >> _crear_usuario.py
echo if User.objects.filter(username=username).exists(): >> _crear_usuario.py
echo     user = User.objects.get(username=username) >> _crear_usuario.py
echo     user.set_password(password) >> _crear_usuario.py
echo     user.save() >> _crear_usuario.py
echo     print('Contrasena actualizada') >> _crear_usuario.py
echo else: >> _crear_usuario.py
echo     User.objects.create_user(username=username, email=email, password=password) >> _crear_usuario.py
echo     print('Usuario creado') >> _crear_usuario.py

python _crear_usuario.py
del _crear_usuario.py

echo.
echo ========================================================
echo              TODO LISTO!
echo ========================================================
echo.
echo   CREDENCIALES DE ACCESO:
echo      Usuario: profesor
echo      Contrasena: skedy2026
echo.
echo   Abre en tu navegador:
echo      http://127.0.0.1:8000
echo.
echo   Para detener: presiona Ctrl+C
echo.
echo ========================================================
echo.

REM Iniciar servidor
python manage.py runserver

pause
