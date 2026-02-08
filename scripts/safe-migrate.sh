#!/usr/bin/env bash
# scripts/safe-migrate.sh
# Ejecuta backup de la base de datos ANTES de correr migraciones Flask.
# Si el backup falla, la migracion NO se ejecuta.
#
# Uso:
#   ./scripts/safe-migrate.sh [--local]
#
# Opciones:
#   --local    Usa pg_dump para backup local en lugar de Heroku CLI
#
# Variables de entorno:
#   HEROKU_APP_NAME  Nombre de la app en Heroku (default: pesosapp)
#   BACKUP_DIR       Directorio para backups locales (default: ./backups)
#   DATABASE_URL     URL de la base de datos (solo para --local)

set -euo pipefail

APP_NAME="${HEROKU_APP_NAME:-pesosapp}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
LOCAL_MODE=false
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Parsear argumentos
for arg in "$@"; do
    case $arg in
        --local)
            LOCAL_MODE=true
            shift
            ;;
        *)
            echo "Argumento desconocido: $arg"
            echo "Uso: $0 [--local]"
            exit 1
            ;;
    esac
done

echo "=== Safe Migrate: Backup + Migration ==="
echo "Modo: $([ "$LOCAL_MODE" = true ] && echo 'LOCAL' || echo 'HEROKU')"
echo "Timestamp: $TIMESTAMP"
echo ""

# --- PASO 1: Backup ---
echo "--- Paso 1: Ejecutando backup pre-migracion ---"

if [ "$LOCAL_MODE" = true ]; then
    # Backup local con pg_dump
    if [ -z "${DATABASE_URL:-}" ]; then
        echo "ERROR: DATABASE_URL no esta definida. Necesaria para backup local."
        exit 1
    fi

    mkdir -p "$BACKUP_DIR"
    BACKUP_FILE="$BACKUP_DIR/pesosapp-pre-migrate-$TIMESTAMP.dump"

    echo "Ejecutando pg_dump..."
    if pg_dump "$DATABASE_URL" --format=custom --no-owner --no-acl -f "$BACKUP_FILE"; then
        echo "Backup local exitoso: $BACKUP_FILE"
        BACKUP_SIZE=$(ls -lh "$BACKUP_FILE" | awk '{print $5}')
        echo "Tamano: $BACKUP_SIZE"
    else
        echo "ERROR: pg_dump fallo. Migracion CANCELADA."
        exit 1
    fi
else
    # Backup en Heroku
    if ! command -v heroku &> /dev/null; then
        echo "ERROR: heroku CLI no esta instalado."
        exit 1
    fi

    echo "Ejecutando heroku pg:backups:capture..."
    if heroku pg:backups:capture --app "$APP_NAME"; then
        echo "Backup de Heroku exitoso."
    else
        echo "ERROR: heroku pg:backups:capture fallo. Migracion CANCELADA."
        exit 1
    fi

    # Verificar que el backup se completo
    echo "Verificando backup..."
    BACKUP_STATUS=$(heroku pg:backups --app "$APP_NAME" 2>/dev/null | head -5)
    echo "$BACKUP_STATUS"

    if echo "$BACKUP_STATUS" | grep -q "Completed"; then
        echo "Backup verificado correctamente."
    else
        echo "ADVERTENCIA: No se pudo verificar el estado del backup."
        echo "Revisa manualmente: heroku pg:backups --app $APP_NAME"
        echo "Migracion CANCELADA por precaucion."
        exit 1
    fi
fi

echo ""

# --- PASO 2: Migracion ---
echo "--- Paso 2: Ejecutando migracion ---"

if [ "$LOCAL_MODE" = true ]; then
    echo "Ejecutando: flask db upgrade"
    if flask db upgrade; then
        echo "Migracion local exitosa."
    else
        echo "ERROR: flask db upgrade fallo."
        echo "Restaurar desde backup: $BACKUP_FILE"
        echo "Comando: pg_restore --no-owner --no-acl -d \$DATABASE_URL $BACKUP_FILE"
        exit 1
    fi
else
    echo "Ejecutando: heroku run flask db upgrade --app $APP_NAME"
    if heroku run flask db upgrade --app "$APP_NAME"; then
        echo "Migracion en Heroku exitosa."
    else
        echo "ERROR: flask db upgrade fallo en Heroku."
        echo "Para restaurar el backup, ejecuta:"
        echo "  heroku pg:backups:restore --app $APP_NAME"
        exit 1
    fi
fi

echo ""
echo "=== Safe Migrate completado exitosamente ==="
echo "Backup: OK | Migracion: OK"
