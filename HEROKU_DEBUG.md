# 🔧 Guía de Debugging para Heroku - Dashboard

## Problemas Más Comunes y Soluciones

### 1. ❌ Error 500 - Internal Server Error

**Posibles Causas:**
- Variables de entorno faltantes
- Problemas de base de datos
- Errores en consultas SQLAlchemy
- Problemas con imports de librerías

**Soluciones Implementadas:**
- ✅ Variables de entorno con valores por defecto
- ✅ Manejo robusto de errores en consultas
- ✅ Fallback data para casos críticos
- ✅ Logging detallado

### 2. 🗃️ Variables de Entorno Requeridas

Verifica que tengas configuradas en Heroku:

```bash
# Revisar variables configuradas
heroku config

# Configurar variables faltantes
heroku config:set DEFAULT_USERNAME=tu_usuario
heroku config:set DEFAULT_PASSWORD=password_seguro
heroku config:set SECRET_KEY=clave_secreta_larga_y_segura
```

### 3. 📊 Problemas con Chart.js

**Síntomas:** Dashboard carga pero gráficos no aparecen

**Soluciones:**
- ✅ Try-catch en JavaScript
- ✅ CDN alternativo para Chart.js
- ✅ Validación de datos antes de crear gráficos

### 4. 🔍 Comandos de Debugging en Heroku

```bash
# Ver logs en tiempo real
heroku logs --tail

# Ver logs específicos del dashboard
heroku logs --grep "dashboard"

# Revisar errores específicos
heroku logs --grep "Error"

# Acceder a la consola de Python en Heroku
heroku run python

# Verificar base de datos
heroku run python -c "from app import db; print(db.engine.table_names())"
```

### 5. 🧪 Tests Locales Antes del Despliegue

```bash
# Ejecutar pruebas del dashboard
python test_dashboard.py

# Verificar que la app arranca
python app.py

# Probar ruta específica
curl -I http://localhost:5000/dashboard
```

### 6. 📈 Datos de Fallback

Si hay problemas críticos, el dashboard mostrará:
- ✅ Datos en cero pero estructura válida
- ✅ Gráficos vacíos en lugar de errores
- ✅ Mensajes informativos en logs

### 7. 🔧 Optimizaciones de Performance

**Implementadas:**
- ✅ Consultas simplificadas sin eager loading
- ✅ Manejo de errores por pedido individual
- ✅ Cálculos robustos con validaciones
- ✅ Timeout handling para consultas lentas

## 🚀 Pasos de Despliegue Seguros

1. **Pre-despliegue:**
   ```bash
   python test_dashboard.py
   ```

2. **Desplegar:**
   ```bash
   git add .
   git commit -m "Fix dashboard para Heroku"
   git push heroku main
   ```

3. **Post-despliegue:**
   ```bash
   heroku logs --tail
   heroku open /dashboard
   ```

4. **Si hay errores:**
   ```bash
   heroku logs --grep "Error\|dashboard" --lines 100
   ```

## 📞 Checklist de Troubleshooting

- [ ] Variables de entorno configuradas
- [ ] Base de datos accesible
- [ ] Logs sin errores críticos
- [ ] Dashboard carga (aunque sea con datos en cero)
- [ ] Gráficos no causan errores JavaScript

## 🆘 Rollback de Emergencia

Si el dashboard sigue fallando, puedes hacer rollback:

```bash
# Ver releases anteriores
heroku releases

# Hacer rollback a versión anterior
heroku rollback v123  # Reemplaza con el número de versión que funcionaba
```