from django.contrib import admin
from .models import Clase, Curso, Grado, Recurso


class OwnerScopedAdmin(admin.ModelAdmin):
    """Non-superusers can only see and modify their own records.
    Closes the IDOR hole where a staff user could type /admin/<model>/<id>/change/
    to access records belonging to other users."""

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(usuario=request.user)

    def _owns(self, request, obj):
        return obj is None or request.user.is_superuser or obj.usuario_id == request.user.id

    def has_view_permission(self, request, obj=None):
        return super().has_view_permission(request, obj) and self._owns(request, obj)

    def has_change_permission(self, request, obj=None):
        return super().has_change_permission(request, obj) and self._owns(request, obj)

    def has_delete_permission(self, request, obj=None):
        return super().has_delete_permission(request, obj) and self._owns(request, obj)

    def save_model(self, request, obj, form, change):
        # Enforce ownership on save: if a staff user is creating, the record is theirs
        if not change and not request.user.is_superuser and not obj.usuario_id:
            obj.usuario = request.user
        super().save_model(request, obj, form, change)


@admin.register(Recurso)
class RecursoAdmin(OwnerScopedAdmin):
    list_display = ['titulo', 'tipo', 'usuario', 'fecha_creacion']
    list_filter = ['tipo']
    search_fields = ['titulo', 'usuario__username']


@admin.register(Curso)
class CursoAdmin(OwnerScopedAdmin):
    list_display = ['nombre', 'nivel_academico', 'materia', 'usuario', 'anio']
    list_filter = ['materia', 'anio']
    search_fields = ['nombre', 'usuario__username']


@admin.register(Grado)
class GradoAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'descripcion']


@admin.register(Clase)
class ClaseAdmin(OwnerScopedAdmin):
    list_display = ['titulo', 'materia', 'profesor_nombre', 'grado_nombre', 'fecha', 'hora_inicio', 'estado']
    list_filter = ['estado', 'materia', 'fecha']
    search_fields = ['titulo', 'profesor_nombre']
