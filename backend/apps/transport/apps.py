from django.apps import AppConfig


class TransportConfig(AppConfig):
    name = 'apps.transport'

    def ready(self):
        import apps.transport.signals  # noqa: F401
        from . import audit
        audit.connect()  # admin activity log
