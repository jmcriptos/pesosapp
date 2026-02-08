# Backup y Restore - PesosApp

## Resumen

PesosApp usa **Heroku PG Backups** para backups automaticos diarios de la base de datos PostgreSQL. Los backups se complementan con exportacion externa para mayor retencion.

## Configuracion de Backups

### Backup Diario Automatico

Configurar el schedule (una sola vez):

```bash
./scripts/setup-heroku-backups.sh
```

Esto programa un backup diario a las **02:00 AM hora de Curazao** (America/Curacao).

### Verificar Schedule Activo

```bash
heroku pg:backups:schedules --app pesosapp
```

### Retencion

- **Heroku Mini/Basic:** retiene los ultimos **5 backups** automaticos
- **Heroku Standard:** retiene los ultimos **25 backups**
- Para cumplir con la politica de 7 dias de retencion, complementar con exportacion externa

## Operaciones de Backup

### Backup Manual Inmediato

```bash
heroku pg:backups:capture --app pesosapp
```

### Listar Backups Disponibles

```bash
heroku pg:backups --app pesosapp
```

Salida tipica:
```
=== Backups
ID    Created at                 Status                               Size
────  ─────────────────────────  ───────────────────────────────────  ──────
b005  2026-02-08 06:00:07 +0000  Completed 2026-02-08 06:00:25 +0000  4.2MB
b004  2026-02-07 06:00:05 +0000  Completed 2026-02-07 06:00:20 +0000  4.1MB
```

### Backup Pre-Migracion

Antes de cualquier migracion de base de datos, usar el script seguro:

```bash
# En Heroku (produccion)
./scripts/safe-migrate.sh

# Desarrollo local
./scripts/safe-migrate.sh --local
```

El script:
1. Ejecuta un backup completo
2. Verifica que el backup se completo exitosamente
3. Solo entonces ejecuta `flask db upgrade`
4. Si el backup falla, la migracion **NO se ejecuta**

### Exportacion a Almacenamiento Local

```bash
./scripts/backup-export.sh
```

Los backups se guardan en `./backups/` con formato `pesosapp-YYYY-MM-DD.dump`.

## Procedimiento de Restore

### Opcion 1: Restore desde Heroku (Produccion)

1. **Listar backups disponibles:**
   ```bash
   heroku pg:backups --app pesosapp
   ```

2. **Restaurar el ultimo backup:**
   ```bash
   heroku pg:backups:restore --app pesosapp --confirm pesosapp
   ```

3. **Restaurar un backup especifico (ej: b003):**
   ```bash
   heroku pg:backups:restore b003 DATABASE_URL --app pesosapp --confirm pesosapp
   ```

4. **Verificar la restauracion:**
   ```bash
   heroku run flask shell --app pesosapp
   >>> from app import db, Pedido
   >>> Pedido.query.count()
   ```

### Opcion 2: Restore desde Archivo Local

1. **Restaurar en Heroku desde archivo local:**
   ```bash
   # Obtener URL publica del backup
   heroku pg:backups:url --app pesosapp
   # Usar esa URL para restore
   heroku pg:backups:restore '<URL>' DATABASE_URL --app pesosapp --confirm pesosapp
   ```

2. **Restaurar en base de datos local:**
   ```bash
   pg_restore --no-owner --no-acl -d $DATABASE_URL backups/pesosapp-2026-02-08.dump
   ```

### Opcion 3: Restore desde URL de Backup

Si tienes la URL del archivo `.dump`:

```bash
heroku pg:backups:restore '<BACKUP_URL>' DATABASE_URL --app pesosapp --confirm pesosapp
```

## Verificacion Post-Restore

Despues de cualquier restore, verificar:

1. **Acceso a la aplicacion:** Navegar a la app y verificar que carga correctamente
2. **Datos recientes:** Verificar que los pedidos mas recientes estan presentes
3. **Login:** Verificar que las credenciales funcionan
4. **Dashboard:** Verificar que los KPIs se calculan correctamente

```bash
# Verificacion rapida via CLI
heroku run flask shell --app pesosapp
>>> from app import db, Pedido, Cliente
>>> print(f"Pedidos: {Pedido.query.count()}")
>>> print(f"Clientes: {Cliente.query.count()}")
>>> print(f"Ultimo pedido: {Pedido.query.order_by(Pedido.fecha.desc()).first().fecha}")
```

## Tiempos Aproximados

| Operacion | Tiempo Estimado | Notas |
|-----------|----------------|-------|
| Backup (capture) | 30-60 segundos | Depende del tamano de la DB |
| Descarga (export) | 1-3 minutos | Depende de la conexion |
| Restore | 1-5 minutos | Incluye downtime de la app |
| Verificacion | 2-3 minutos | Tests manuales basicos |

**Nota:** La app tendra **downtime durante el restore**. Planificar restores fuera de horario laboral (antes de 7:00 AM o despues de 6:00 PM, hora de Curazao).

## Variables de Entorno

| Variable | Descripcion | Default |
|----------|------------|---------|
| `HEROKU_APP_NAME` | Nombre de la app en Heroku | `pesosapp` |
| `BACKUP_DIR` | Directorio para backups locales | `./backups` |
| `DATABASE_URL` | URL de la base de datos (automatica en Heroku) | - |

## Troubleshooting

### "No backups yet"
Ejecutar un backup manual primero:
```bash
heroku pg:backups:capture --app pesosapp
```

### "Backup failed"
Verificar que la base de datos esta accesible:
```bash
heroku pg:info --app pesosapp
```

### "Permission denied" en scripts
```bash
chmod +x scripts/setup-heroku-backups.sh
chmod +x scripts/safe-migrate.sh
chmod +x scripts/backup-export.sh
```

## Referencias

- [Heroku PG Backups Documentation](https://devcenter.heroku.com/articles/heroku-postgres-backups)
- [Heroku pg:restore](https://devcenter.heroku.com/articles/heroku-postgres-import-export)
- Ruta admin: `/admin/backup` (solo super_admin)
