#!/usr/bin/env bash
# scripts/backup-export.sh
# Descarga el ultimo backup de Heroku PG y lo guarda localmente.
#
# Uso:
#   ./scripts/backup-export.sh [--force] [APP_NAME]
#
# Opciones:
#   --force    Sobreescribir backup existente sin preguntar
#
# Variables de entorno:
#   HEROKU_APP_NAME  Nombre de la app (default: pesosapp)
#   BACKUP_DIR       Directorio destino (default: ./backups)

set -euo pipefail

FORCE=false
APP_NAME=""

# Parsear argumentos
for arg in "$@"; do
    case $arg in
        --force|-y)
            FORCE=true
            ;;
        *)
            APP_NAME="$arg"
            ;;
    esac
done

APP_NAME="${APP_NAME:-${HEROKU_APP_NAME:-pesosapp}}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
TIMESTAMP=$(date +%Y-%m-%d)
BACKUP_FILE="$BACKUP_DIR/pesosapp-$TIMESTAMP.dump"

echo "=== Exportacion de Backup: $APP_NAME ==="

# Verificar heroku CLI
if ! command -v heroku &> /dev/null; then
    echo "ERROR: heroku CLI no esta instalado."
    exit 1
fi

# Crear directorio de backups
mkdir -p "$BACKUP_DIR"

# Verificar si ya existe un backup de hoy
if [ -f "$BACKUP_FILE" ]; then
    if [ "$FORCE" = true ]; then
        echo "Sobreescribiendo backup existente (--force): $BACKUP_FILE"
    else
        echo "Ya existe un backup de hoy: $BACKUP_FILE"
        read -p "Sobreescribir? (s/N): " -r
        if [[ ! $REPLY =~ ^[Ss]$ ]]; then
            echo "Exportacion cancelada."
            exit 0
        fi
    fi
fi

# Obtener URL del ultimo backup
echo "Obteniendo URL del ultimo backup..."
BACKUP_URL=$(heroku pg:backups:url --app "$APP_NAME" 2>/dev/null)

if [ -z "$BACKUP_URL" ]; then
    echo "ERROR: No se pudo obtener la URL del backup."
    echo "Verifica que existan backups: heroku pg:backups --app $APP_NAME"
    exit 1
fi

# Descargar backup
echo "Descargando backup..."
if curl -o "$BACKUP_FILE" "$BACKUP_URL" --progress-bar --fail; then
    BACKUP_SIZE=$(ls -lh "$BACKUP_FILE" | awk '{print $5}')
    echo ""
    echo "Backup descargado exitosamente."
    echo "  Archivo: $BACKUP_FILE"
    echo "  Tamano:  $BACKUP_SIZE"
else
    echo "ERROR: Fallo la descarga del backup."
    rm -f "$BACKUP_FILE"
    exit 1
fi

# Listar backups locales
echo ""
echo "=== Backups locales disponibles ==="
ls -lh "$BACKUP_DIR"/*.dump 2>/dev/null || echo "(ninguno)"

echo ""
echo "Para restaurar este backup:"
echo "  heroku pg:backups:restore '$BACKUP_URL' DATABASE_URL --app $APP_NAME"
echo "  -- o localmente --"
echo "  pg_restore --no-owner --no-acl -d \$DATABASE_URL $BACKUP_FILE"

# TODO: Subir a S3 u otro storage externo
# Si se configura AWS CLI:
#   aws s3 cp "$BACKUP_FILE" "s3://pesosapp-backups/$TIMESTAMP/pesosapp.dump"
