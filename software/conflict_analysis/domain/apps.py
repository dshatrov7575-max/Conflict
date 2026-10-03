from django.apps import AppConfig
from django.db import connections
from django.db.backends.signals import connection_created


_SQLITE_GUARD_FUNCTION = "domain_fd08_projection_write_authorized"


def _register_sqlite_projection_authority(*, connection, **_kwargs) -> None:
    """Expose the process-local projection lease to SQLite fail-closed triggers."""

    if connection.vendor != "sqlite" or connection.connection is None:
        return

    def authorized() -> int:
        from domain.models import _assessment_projection_write_is_authorized

        return int(_assessment_projection_write_is_authorized("projection"))

    connection.connection.create_function(
        _SQLITE_GUARD_FUNCTION,
        0,
        authorized,
        deterministic=False,
    )


class DomainConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "domain"
    verbose_name = "Conflict analysis domain"

    def ready(self) -> None:
        connection_created.connect(
            _register_sqlite_projection_authority,
            dispatch_uid="domain.fd08.sqlite_projection_authority",
            weak=False,
        )
        for connection in connections.all():
            if connection.connection is not None:
                _register_sqlite_projection_authority(connection=connection)
