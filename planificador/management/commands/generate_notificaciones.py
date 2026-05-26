"""
Management command: generate_notificaciones
============================================
Cron cada minuto. Genera notificaciones in-app para:
  - Inicio de jornada (resumen del día)
  - Pre-alerta 1 hora antes de cada clase
  - Inicio de clase
  - Fin de clase
  - Recordatorio de fin de semana (sábados)

Deduplicación: campo `clave` — nunca duplica el mismo evento.
Limpieza automática: mantiene máximo 50 notificaciones por usuario.
"""

import logging
from datetime import date as _date

from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger('planificador')


class Command(BaseCommand):
    help = 'Genera notificaciones in-app según la jornada y las clases del día.'

    def handle(self, *args, **options):
        from planificador.models import Clase, HorarioAcademico, Notificacion
        from django.db.models import Count

        now   = timezone.localtime()
        today = now.date()
        h, m  = now.hour, now.minute

        # ── 1. Resumen matutino al inicio de jornada ─────────────────────────
        for horario in HorarioAcademico.objects.filter(
            hora_inicio_jornada__hour=h,
            hora_inicio_jornada__minute=m,
        ).select_related('usuario'):
            user  = horario.usuario
            clave = f'jornada_inicio_{today.isoformat()}'
            if Notificacion.objects.filter(usuario=user, clave=clave).exists():
                continue

            n_clases = Clase.objects.filter(usuario=user, fecha=today).count()
            if n_clases:
                titulo  = 'Inicio de jornada'
                mensaje = (
                    f'Hoy tienes {n_clases} clase(s) programada(s). '
                    '¡Que tengas una excelente jornada académica!'
                )
                tipo = 'info'
            else:
                titulo  = 'Jornada sin clases'
                mensaje = (
                    'No tienes clases hoy. '
                    'Aprovecha para adelantar planeación o explorar el Lab Pedagógico.'
                )
                tipo = 'sistema'

            Notificacion.objects.create(
                usuario=user, titulo=titulo, mensaje=mensaje,
                tipo=tipo, clave=clave,
            )

        # ── 2. Notificaciones por clase (pre-alerta, inicio, fin) ─────────────
        for clase in Clase.objects.filter(fecha=today, estado='pending').select_related('usuario'):
            user = clase.usuario

            inicio_dt = timezone.make_aware(
                timezone.datetime(
                    today.year, today.month, today.day,
                    clase.hora_inicio.hour, clase.hora_inicio.minute,
                )
            )
            mins_para_inicio = (inicio_dt - now).total_seconds() / 60

            # Pre-alerta: ~60 min antes
            if 59 <= mins_para_inicio <= 61:
                clave = f'prealerta_{clase.id}_{today.isoformat()}'
                if not Notificacion.objects.filter(usuario=user, clave=clave).exists():
                    Notificacion.objects.create(
                        usuario=user,
                        titulo='Clase en 1 hora',
                        mensaje=(
                            f'En 1 hora inicia {clase.titulo}'
                            + (f' · {clase.grado_nombre}' if clase.grado_nombre else '')
                            + '.'
                        ),
                        tipo='alerta',
                        clave=clave,
                    )

            # Inicio de clase: ±1 min
            if -1 <= mins_para_inicio <= 1:
                clave = f'inicio_{clase.id}_{today.isoformat()}'
                if not Notificacion.objects.filter(usuario=user, clave=clave).exists():
                    hora_fin = clase.hora_fin.strftime('%H:%M') if clase.hora_fin else '—'
                    Notificacion.objects.create(
                        usuario=user,
                        titulo='Clase iniciando ahora',
                        mensaje=(
                            f'{clase.titulo}'
                            + (f' con {clase.grado_nombre}' if clase.grado_nombre else '')
                            + f' acaba de comenzar. Hora de finalización: {hora_fin}.'
                        ),
                        tipo='exito',
                        clave=clave,
                    )

            # Fin de clase: ±1 min
            if clase.hora_fin:
                fin_dt = timezone.make_aware(
                    timezone.datetime(
                        today.year, today.month, today.day,
                        clase.hora_fin.hour, clase.hora_fin.minute,
                    )
                )
                mins_desde_fin = (now - fin_dt).total_seconds() / 60
                if -1 <= mins_desde_fin <= 1:
                    clave = f'fin_{clase.id}_{today.isoformat()}'
                    if not Notificacion.objects.filter(usuario=user, clave=clave).exists():
                        Notificacion.objects.create(
                            usuario=user,
                            titulo='Clase finalizada',
                            mensaje=(
                                f'{clase.titulo} ha concluido. '
                                'El registro quedó archivado en tu historial.'
                            ),
                            tipo='sistema',
                            clave=clave,
                        )

        # ── 3. Recordatorio de fin de semana (sábado 8 AM) ───────────────────
        if today.weekday() == 5 and h == 8 and m == 0:
            from planificador.models import ConfiguracionUsuario
            for config in ConfiguracionUsuario.objects.select_related('usuario').all():
                user  = config.usuario
                clave = f'finde_{today.isoformat()}'
                if Notificacion.objects.filter(usuario=user, clave=clave).exists():
                    continue
                Notificacion.objects.create(
                    usuario=user,
                    titulo='Recordatorio de fin de semana',
                    mensaje=(
                        'Es fin de semana. Recuerda revisar y completar '
                        'los temas de la próxima semana en el Planificador.'
                    ),
                    tipo='alerta',
                    clave=clave,
                )

        # ── 4. Limpieza: mantener máximo 50 por usuario ───────────────────────
        from planificador.models import Notificacion
        for row in (
            Notificacion.objects
            .values('usuario')
            .annotate(total=Count('id'))
            .filter(total__gt=50)
        ):
            ids_a_borrar = list(
                Notificacion.objects
                .filter(usuario_id=row['usuario'])
                .order_by('-fecha_creacion')
                .values_list('id', flat=True)[50:]
            )
            if ids_a_borrar:
                Notificacion.objects.filter(id__in=ids_a_borrar).delete()

        self.stdout.write('generate_notificaciones: ciclo completado.')
