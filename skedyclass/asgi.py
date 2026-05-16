"""
ASGI config for SkedyClass project.
"""

import os
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'skedyclass.settings')
application = get_asgi_application()
