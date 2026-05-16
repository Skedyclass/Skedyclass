#!/bin/bash

# =====================================================
#  SkedyClass - Script de Instalación y Ejecución
#  Para Linux (Ubuntu, Debian, etc.)
# =====================================================

echo ""
echo "╔════════════════════════════════════════════════╗"
echo "║     🎨 SkedyClass - Planificador Mágico 🎨     ║"
echo "╚════════════════════════════════════════════════╝"
echo ""

# Verificar si Python está instalado
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: Python3 no está instalado."
    echo "   Instálalo con: sudo apt install python3"
    exit 1
fi

echo "✅ Python3 encontrado: $(python3 --version)"

# Crear entorno virtual si no existe
if [ ! -d "venv" ]; then
    echo ""
    echo "📦 Creando entorno virtual..."
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo "❌ Error creando el entorno virtual."
        echo "   Intenta instalar: sudo apt install python3-venv"
        exit 1
    fi
    echo "✅ Entorno virtual creado"
fi

# Activar entorno virtual
echo ""
echo "🔄 Activando entorno virtual..."
source venv/bin/activate

# Instalar dependencias
echo ""
echo "📥 Instalando dependencias (Django, IA, PDF)..."
pip install --upgrade pip > /dev/null 2>&1
pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "❌ Error instalando dependencias"
    exit 1
fi
echo "✅ Dependencias instaladas correctamente"

# Ejecutar migraciones
echo ""
echo "🗃️ Configurando base de datos..."
python manage.py makemigrations planificador --noinput
python manage.py migrate --noinput
echo "✅ Base de datos configurada"

# Crear usuario administrador usando script Python
echo ""
echo "👤 Creando usuario administrador..."

cat > _crear_usuario.py << 'PYTHON_SCRIPT'
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'skedyclass.settings')
django.setup()

from django.contrib.auth.models import User

username = 'profesor'
password = 'skedy2026'
email = 'profesor@skedyclass.com'

try:
    if User.objects.filter(username=username).exists():
        user = User.objects.get(username=username)
        user.set_password(password)
        user.save()
        print(f"✅ Contraseña actualizada para '{username}'")
    else:
        User.objects.create_user(username=username, email=email, password=password)
        print(f"✅ Usuario '{username}' creado exitosamente")
except Exception as e:
    print(f"❌ Error: {e}")
PYTHON_SCRIPT

python _crear_usuario.py
rm -f _crear_usuario.py

# Mensaje de éxito
echo ""
echo "╔════════════════════════════════════════════════╗"
echo "║           ✅ ¡Todo listo!                      ║"
echo "╠════════════════════════════════════════════════╣"
echo "║                                                ║"
echo "║  🔐 CREDENCIALES DE ACCESO:                   ║"
echo "║     Usuario: profesor                          ║"
echo "║     Contraseña: skedy2026                      ║"
echo "║                                                ║"
echo "║  🚀 Iniciando servidor en:                    ║"
echo "║     http://127.0.0.1:8000                     ║"
echo "║                                                ║"
echo "║  📌 Para detener: presiona Ctrl+C             ║"
echo "║                                                ║"
echo "╚════════════════════════════════════════════════╝"
echo ""

# Iniciar servidor
python manage.py runserver
