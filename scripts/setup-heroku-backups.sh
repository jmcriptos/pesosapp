#!/usr/bin/env bash
# scripts/setup-heroku-backups.sh
# Configura backup automático diario de PostgreSQL en Heroku
#
# Uso:
#   ./scripts/setup-heroku-backups.sh [APP_NAME]
#
# Si no se pasa APP_NAME, usa la variable HEROKU_APP_NAME o 'pesosapp' por defecto.

set -euo pipefail

APP_NAME="${1:-${HEROKU_APP_NAME:-pesosapp}}"

echo "=== Configurando Heroku PG Backups para: $APP_NAME ==="

# Verificar que heroku CLI está instalado
if ! command -v heroku &> /dev/null; then
    echo "ERROR: heroku CLI no está instalado."
    echo "Instalar con: brew tap heroku/brew && brew install heroku"
    exit 1
fi

# Verificar autenticación
if ! heroku auth:whoami &> /dev/null; then
    echo "ERROR: No estás autenticado en Heroku. Ejecuta: heroku login"
    exit 1
fi

# Programar backup diario a las 2:00 AM hora de Curazao
echo "Programando backup diario a las 02:00 AM (America/Curacao)..."
heroku pg:backups:schedule DATABASE_URL --at '02:00 America/Curacao' --app "$APP_NAME"

echo ""
echo "=== Verificando schedule activo ==="
heroku pg:backups:schedules --app "$APP_NAME"

echo ""
echo "=== Backups existentes ==="
heroku pg:backups --app "$APP_NAME"

echo ""
echo "Configuracion completada."
echo ""
echo "NOTA: Heroku retiene los ultimos 5 backups en plan Mini/Basic."
echo "Para mayor retencion, usa scripts/backup-export.sh para descargar"
echo "backups a almacenamiento externo."
echo ""
echo "Comandos utiles:"
echo "  heroku pg:backups:schedules --app $APP_NAME   # Ver schedules activos"
echo "  heroku pg:backups --app $APP_NAME              # Listar backups"
echo "  heroku pg:backups:capture --app $APP_NAME      # Backup manual inmediato"
echo "  heroku pg:backups:url --app $APP_NAME          # URL del ultimo backup"
