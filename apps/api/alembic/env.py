import os
import time
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool, text

from alembic import context
from apbra_api.persistence import Base

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
explicit_database_url = config.get_main_option("sqlalchemy.url").strip()
if not explicit_database_url and (database_url := os.environ.get("APBRA_DATABASE_URL")):
    config.set_main_option("sqlalchemy.url", database_url)
if not config.get_main_option("sqlalchemy.url").strip():
    raise RuntimeError("Alembic requires an explicit database URL or APBRA_DATABASE_URL.")
target_metadata = Base.metadata
_MIGRATION_LOCK = 0x4150425241313733  # Stable APBRA schema lock across release processes.


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    timeout = int(os.environ.get("APBRA_MIGRATION_LOCK_TIMEOUT_SECONDS", "30"))
    if not 1 <= timeout <= 300:
        raise RuntimeError("Migration lock timeout must be between 1 and 300 seconds")
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args={"connect_timeout": 10},
    )
    try:
        with connectable.connect() as connection:
            deadline = time.monotonic() + timeout
            locked = False
            try:
                while not locked:
                    locked = bool(
                        connection.scalar(
                            text("SELECT pg_try_advisory_lock(:key)"), {"key": _MIGRATION_LOCK}
                        )
                    )
                    connection.commit()  # The session lock survives this transaction boundary.
                    if not locked:
                        if time.monotonic() >= deadline:
                            raise RuntimeError("Timed out waiting for APBRA schema migration lock")
                        time.sleep(0.2)
                context.configure(connection=connection, target_metadata=target_metadata)
                with context.begin_transaction():
                    context.run_migrations()
            finally:
                connection.rollback()
                if locked:
                    released = connection.scalar(
                        text("SELECT pg_advisory_unlock(:key)"), {"key": _MIGRATION_LOCK}
                    )
                    connection.commit()
                    if not released:
                        raise RuntimeError("APBRA schema migration lock was not held at release")
    finally:
        connectable.dispose()


run_migrations_offline() if context.is_offline_mode() else run_migrations_online()
