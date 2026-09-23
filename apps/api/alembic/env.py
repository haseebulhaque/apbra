import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

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
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_offline() if context.is_offline_mode() else run_migrations_online()
