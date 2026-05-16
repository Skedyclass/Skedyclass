# 🎨 SkedyClass - Planificador Mágico de Clases

Un sistema de planificación de clases para docentes de primaria, desarrollado con Django.

## 🔐 Crear usuario administrador

Después de instalar, crea tu propio usuario con:

```bash
python manage.py createsuperuser
```

O accede al panel de admin en `/admin/` para gestionar usuarios.

## 📋 Características

- ✅ Sistema de autenticación (login/logout)
- ✅ Dashboard con estadísticas y tablero Kanban
- ✅ Planificador de clases con calendario
- ✅ Gestión de clases (CRUD completo)
- ✅ Gestión de profesores
- ✅ Gestión de estudiantes
- ✅ Juegos educativos interactivos
- ✅ Sistema de notas personales
- ✅ Observador Personal (imprimible)
- ✅ Temas claro/oscuro
- ✅ 4 esquemas de colores (Ocean, Sunset, Forest, Candy)
- ✅ Diseño responsivo

## 🐧 Instalación en Linux

```bash
# 1. Descomprimir y entrar a la carpeta
unzip skedyclass_django.zip
cd skedyclass_django

# 2. Dar permisos y ejecutar
chmod +x run.sh
./run.sh

# 3. Abrir en navegador: http://127.0.0.1:8000
```

## 🪟 Instalación en Windows

```cmd
# 1. Descomprimir el ZIP

# 2. Hacer doble clic en run.bat
#    O desde CMD:
run.bat

# 3. Abrir en navegador: http://127.0.0.1:8000
```

## 📂 Estructura del Proyecto

```
skedyclass_django/
├── manage.py
├── run.sh              # Script para Linux
├── run.bat             # Script para Windows
├── requirements.txt
├── skedyclass/         # Configuración Django
├── planificador/       # App principal
│   ├── models.py
│   ├── views.py
│   ├── forms.py
│   └── templates/
└── static/
    ├── css/styles.css
    └── js/main.js
```

## 🎨 Personalización

### Cambiar Tema
Ve a **Ajustes** en el menú lateral y selecciona entre modo claro u oscuro.

### Cambiar Colores
En la misma página de Ajustes, puedes elegir entre 4 esquemas de colores:
- 🌊 Ocean (azul/violeta)
- 🌅 Sunset (naranja/rojo)
- 🌲 Forest (verde/turquesa)
- 🍬 Candy (rosa/morado)

## ⚠️ Requisitos

| Sistema | Requisito |
|---------|-----------|
| **Linux** | Python 3.8+ (`sudo apt install python3 python3-venv`) |
| **Windows** | Python 3.8+ desde [python.org](https://www.python.org/downloads/) |

## 📝 Licencia

Proyecto educativo - SkedyClass 2026

---

Desarrollado con ❤️ y Django
