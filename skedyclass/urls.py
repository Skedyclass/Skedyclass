"""
URL configuration for SkedyClass project.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from planificador import views

urlpatterns = [
    path('admin/', admin.site.urls),

    # Landing pública
    path('', views.landing, name='landing'),

    # Páginas legales públicas (requeridas por la verificación OAuth de Google)
    path('privacidad/', views.privacidad, name='privacidad'),
    path('terminos/', views.terminos, name='terminos'),

    # Autenticación
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    # Our bridge view validates OAuth config before delegating to allauth.
    # Name MUST NOT collide with allauth's internal `google_login` URL.
    path('auth/google/', views.google_login, name='google_oauth_start'),

    # Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),

    # Planificador
    path('planificador/', views.planificador, name='planificador'),

    # Calendario
    path('calendario/', views.calendario, name='calendario'),

    # Clases
    path('clases/', views.listar_clases, name='listar_clases'),
    path('clases/nueva/', views.crear_clase, name='crear_clase'),
    path('api/clase/ia-plan/', views.clase_ia_plan, name='clase_ia_plan'),
    path('clases/editar/<int:id>/', views.editar_clase, name='editar_clase'),
    path('clases/eliminar/<int:id>/', views.eliminar_clase, name='eliminar_clase'),
    path('clases/estado/<int:id>/<str:estado>/', views.cambiar_estado_clase, name='cambiar_estado'),
    path('clases/<int:id>/pdf/', views.clase_pdf, name='clase_pdf'),
    path('clases/ver/<int:id>/', views.ver_clase, name='ver_clase'),
    path('api/clases/<int:id>/pdf/guardar/', views.clase_pdf_guardar, name='clase_pdf_guardar'),
    path('api/clases/<int:clase_id>/vincular-recurso/', views.vincular_recurso_clase, name='vincular_recurso_clase'),

    # Registro y bienvenida
    path('registro/', views.registro, name='registro'),
    path('bienvenida/', views.bienvenida, name='bienvenida'),

    # Cursos
    path('cursos/', views.listar_cursos, name='listar_cursos'),
    path('cursos/nuevo/', views.crear_curso, name='crear_curso'),
    path('cursos/<int:id>/', views.ver_curso, name='ver_curso'),
    path('cursos/eliminar/<int:id>/', views.eliminar_curso, name='eliminar_curso'),

    # Recursos
    path('recursos/', views.listar_recursos, name='listar_recursos'),
    path('recursos/nuevo/', views.crear_recurso, name='crear_recurso'),
    path('recursos/eliminar/<int:id>/', views.eliminar_recurso, name='eliminar_recurso'),
    path('recursos/<int:id>/descargar/', views.descargar_recurso, name='descargar_recurso'),
    path('recursos/<int:id>/ver/', views.inline_recurso, name='inline_recurso'),

    # Notas
    path('notas/', views.notas, name='notas'),
    path('notas/eliminar/<int:id>/', views.eliminar_nota, name='eliminar_nota'),

    # Horario Académico
    path('horario/', views.horario, name='horario'),
    path('horario/guardar/', views.guardar_horario, name='guardar_horario'),
    path('horario/bloque/nuevo/', views.guardar_bloque, name='guardar_bloque'),
    path('horario/bloque/eliminar/<int:id>/', views.eliminar_bloque, name='eliminar_bloque'),
    path('horario/bloque-semanal/nuevo/', views.guardar_bloque_horario, name='guardar_bloque_horario'),
    path('horario/bloque-semanal/eliminar/<int:id>/', views.eliminar_bloque_horario, name='eliminar_bloque_horario'),
    path('horario/ano-lectivo/', views.guardar_ano_lectivo, name='guardar_ano_lectivo'),
    path('api/horario/proyectar/', views.proyectar_ano_lectivo, name='proyectar_ano_lectivo'),

    # Ajustes y perfil
    path('ajustes/', views.ajustes, name='ajustes'),
    path('perfil/', views.perfil, name='perfil'),

    # Asistente IA
    path('asistente/', views.asistente, name='asistente'),

    # AI Pedagogical Lab
    path('lab/', views.lab, name='lab'),
    path('api/lab/', views.lab_api, name='lab_api'),
    path('api/lab/guardar/', views.lab_guardar_recurso, name='lab_guardar_recurso'),
    path('api/lab/guardar-pdf/', views.lab_guardar_documento, name='lab_guardar_documento'),

    # Google Calendar Sync
    path('api/gcal/sync/<int:id>/', views.gcal_sync_clase, name='gcal_sync_clase'),
    path('api/gcal/eventos/', views.gcal_eventos_api, name='gcal_eventos_api'),
    path('api/gcal/sync-all/', views.gcal_sync_all, name='gcal_sync_all'),
    path('api/gcal/disconnect/', views.gcal_disconnect, name='gcal_disconnect'),

    # API interna
    path('api/preferencia/', views.guardar_preferencia, name='guardar_preferencia'),
    path('api/asistente/', views.asistente_api, name='asistente_api'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Google OAuth (django-allauth) — solo se monta si la app está instalada
try:
    import allauth  # noqa: F401
    urlpatterns += [path('accounts/', include('allauth.urls'))]
except ImportError:
    pass
