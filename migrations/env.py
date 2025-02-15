import os
from logging.config import fileConfig
from alembic import context
from flask import current_app

# Cargar la configuración de Alembic desde alembic.ini
config = context.config

# Configurar el logging
fileConfig(config.config_file_name)

# Función para obtener el engine de la base de datos a partir de Flask-Migrate.
def get_engine():
    try:
        # Funciona con Flask-SQLAlchemy < 3
        return current_app.extensions['migrate'].db.get_engine()
    except (TypeError, AttributeError):
        # Funciona con Flask-SQLAlchemy >= 3
        return current_app.extensions['migrate'].db.engine

# Si se ha definido la variable de entorno DATABASE_URL, úsala;
# de lo contrario, utiliza la URL configurada en el engine.
env_url = os.environ.get("DATABASE_URL")
if env_url:
    # Asegurarse de que la URL sea compatible con SQLAlchemy (cambiar postgres:// a postgresql://)
    if env_url.startswith("postgres://"):
        env_url = env_url.replace("postgres://", "postgresql://", 1)
    config.set_main_option("sqlalchemy.url", env_url)
else:
    # Se usa la URL del engine configurado en Flask
    config.set_main_option("sqlalchemy.url", str(get_engine().url))

# Importa la metadata de tus modelos. Asumimos que el objeto "db" está en app.py.
from app import db
target_metadata = db.metadata

def run_migrations_offline():
    """Ejecuta migraciones en modo offline (sin conexión directa a la base de datos)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    """Ejecuta migraciones en modo online (con conexión a la base de datos)."""
    connectable = get_engine()

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

