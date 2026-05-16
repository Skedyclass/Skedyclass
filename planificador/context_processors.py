from .models import ConfiguracionUsuario


def user_config(request):
    """Inyecta user_config en todos los templates para acceder a tema, color, etc."""
    if not request.user.is_authenticated:
        return {}
    config, _ = ConfiguracionUsuario.objects.get_or_create(usuario=request.user)
    return {'user_config': config}
