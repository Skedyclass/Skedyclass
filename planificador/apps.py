import os
import logging

from django.apps import AppConfig
from django.db.models.signals import post_migrate

logger = logging.getLogger('planificador')


def _sync_site_from_env(sender, **kwargs):
    """Keep django.contrib.sites in sync with the SITE_DOMAIN env var so that
    Google OAuth callback URLs (built by allauth via Sites framework) always
    match what's registered in Google Cloud Console.

    Set SITE_DOMAIN=tudominio.com in production .env to auto-update.
    """
    site_domain = os.environ.get('SITE_DOMAIN', '').strip()
    if not site_domain:
        return
    try:
        from django.contrib.sites.models import Site
        from django.conf import settings
        site_id = getattr(settings, 'SITE_ID', 1)
        site, created = Site.objects.update_or_create(
            id=site_id,
            defaults={'domain': site_domain, 'name': site_domain},
        )
        if created:
            logger.info('Site %s creado: %s', site_id, site_domain)
        else:
            logger.info('Site %s sincronizado a: %s', site_id, site_domain)
    except Exception as e:
        logger.warning('No se pudo sincronizar Site desde SITE_DOMAIN: %s', e)


def _ensure_google_socialapp(sender, **kwargs):
    """Allauth 65+ can use either DB-based SocialApp records or settings-based
    APP config. We use settings-based (SOCIALACCOUNT_PROVIDERS['google']['APP']),
    but a stray DB SocialApp can cause the auth flow to fail with 'no app configured'.
    Make sure no orphan DB SocialApp shadows the settings config.
    """
    from django.conf import settings
    if 'allauth.socialaccount' not in settings.INSTALLED_APPS:
        return
    try:
        from allauth.socialaccount.models import SocialApp
        from django.contrib.sites.models import Site
        prov = settings.SOCIALACCOUNT_PROVIDERS.get('google', {}).get('APP', {})
        client_id = (prov.get('client_id') or '').strip()
        client_secret = (prov.get('secret') or '').strip()
        if not client_id or not client_secret:
            return
        # If a DB SocialApp exists, make sure it has the current credentials and
        # is associated with the current Site (otherwise allauth ignores it).
        app = SocialApp.objects.filter(provider='google').first()
        if app:
            changed = False
            if app.client_id != client_id:
                app.client_id = client_id; changed = True
            if app.secret != client_secret:
                app.secret = client_secret; changed = True
            if changed:
                app.save(update_fields=['client_id', 'secret'])
                logger.info('SocialApp google sincronizada con .env')
            # Ensure the current Site is attached
            current_site = Site.objects.filter(id=settings.SITE_ID).first()
            if current_site and current_site not in app.sites.all():
                app.sites.add(current_site)
                logger.info('Site %s vinculado a SocialApp google', current_site.domain)
    except Exception as e:
        logger.warning('SocialApp sync fallo: %s', e)


class PlanificadorConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'planificador'
    verbose_name = 'Planificador de Clases'

    def ready(self):
        import planificador.models  # noqa: registers post_save signal
        # Hook post_migrate so Site + SocialApp stay aligned with env on every deploy.
        post_migrate.connect(_sync_site_from_env, sender=self)
        post_migrate.connect(_ensure_google_socialapp, sender=self)
