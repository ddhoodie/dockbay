from django.apps import AppConfig


class RegistryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "registry"

    def ready(self):
        from django.db.models.signals import post_migrate

        from registry.bootstrap import bootstrap_on_migrate

        post_migrate.connect(bootstrap_on_migrate, sender=self)
