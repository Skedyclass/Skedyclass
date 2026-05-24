"""
Management command: send_daily_reminders
========================================
Despachado por el Cron Job de Render cada minuto:
  python manage.py send_daily_reminders

Para cada usuario con recordatorio activo cuya hora preferida coincida
con el minuto actual (zona horaria del proyecto), envía un correo con
su agenda del día o un mensaje de día libre.

Protección anti-duplicado: se guarda la fecha del último envío en
ConfiguracionUsuario.ultimo_recordatorio_enviado, por lo que aunque
el cron corra varias veces en el mismo minuto nunca se envía más de
una vez por día.
"""

import logging
from datetime import date as _date

from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand
from django.template.loader import render_to_string
from django.utils import timezone

from planificador.models import Clase, ConfiguracionUsuario

logger = logging.getLogger('planificador')


class Command(BaseCommand):
    help = 'Envía recordatorios diarios de agenda a los docentes según su hora preferida.'

    def handle(self, *args, **options):
        now = timezone.localtime()
        today = now.date()
        current_h = now.hour
        current_m = now.minute

        # Usuarios con recordatorio activo, hora coincidente y no enviado hoy
        configs = (
            ConfiguracionUsuario.objects
            .filter(
                recibir_recordatorio_email=True,
                hora_recordatorio_preferida__hour=current_h,
                hora_recordatorio_preferida__minute=current_m,
            )
            .exclude(ultimo_recordatorio_enviado=today)
            .select_related('usuario')
        )

        if not configs.exists():
            self.stdout.write('Sin recordatorios pendientes para este minuto.')
            return

        sent = errors = skipped = 0

        for config in configs:
            user = config.usuario
            email = user.email.strip() if user.email else ''

            if not email:
                logger.warning(
                    'send_daily_reminders: usuario %s no tiene email — omitido.',
                    user.username,
                )
                skipped += 1
                continue

            try:
                clases_hoy = list(
                    Clase.objects.filter(usuario=user, fecha=today)
                    .order_by('hora_inicio')
                )
                tiene_clases = bool(clases_hoy)

                context = {
                    'usuario': user,
                    'clases': clases_hoy,
                    'today': today,
                    'tiene_clases': tiene_clases,
                }

                fecha_str = today.strftime('%d de %B de %Y')
                subject = f'SkedyClass — Tu agenda del {fecha_str}'
                html_body = render_to_string('email/recordatorio_diario.html', context)
                text_body = _build_plain_text(user, clases_hoy, today, tiene_clases)

                msg = EmailMultiAlternatives(
                    subject=subject,
                    body=text_body,
                    to=[email],
                )
                msg.attach_alternative(html_body, 'text/html')
                msg.send(fail_silently=False)

                config.ultimo_recordatorio_enviado = today
                config.save(update_fields=['ultimo_recordatorio_enviado'])

                sent += 1
                logger.info(
                    'send_daily_reminders: recordatorio enviado → %s (%s) — %d clase(s).',
                    user.username, email, len(clases_hoy),
                )

            except Exception as exc:
                errors += 1
                logger.error(
                    'send_daily_reminders: error enviando a %s (%s): %s',
                    user.username, email, exc, exc_info=True,
                )

        summary = f'Recordatorios: {sent} enviados, {errors} errores, {skipped} sin email.'
        self.stdout.write(summary)
        logger.info(summary)


# ── Texto plano (fallback para clientes sin HTML) ──────────────────────────────

def _build_plain_text(user, clases, today, tiene_clases):
    nombre = user.first_name or user.username
    fecha_str = today.strftime('%d de %B de %Y')
    lines = [
        f'SkedyClass — Agenda del {fecha_str}',
        '=' * 48,
        f'Buenos días, {nombre}.',
        '',
    ]
    if tiene_clases:
        lines.append(f'Tienes {len(clases)} clase(s) programada(s) para hoy:')
        lines.append('')
        for i, cl in enumerate(clases, 1):
            hora_fin = cl.hora_fin.strftime('%H:%M') if cl.hora_fin else '—'
            lines.append(
                f'  {i}. {cl.titulo}'
                f'\n     Curso: {cl.grado_nombre or "—"}'
                f'\n     Materia: {cl.materia or "—"}'
                f'\n     Horario: {cl.hora_inicio.strftime("%H:%M")} – {hora_fin}'
            )
            lines.append('')
    else:
        lines.append(
            '¡Enhorabuena! Tienes el día libre. '
            'Aprovecha para organizar tus clases de la próxima semana.'
        )
        lines.append('')

    lines += [
        '─' * 48,
        'SkedyClass — Planificador inteligente para docentes',
        'Para desactivar este recordatorio, ingresa a Ajustes → Preferencias.',
    ]
    return '\n'.join(lines)
