-- Pedido 1357 (DeliNova, factura 48007): pesos de Pork Chorizo y Andouiline
-- Pork Chorizo registrados cruzados. El código no los mezcló: cada caja quedó
-- en el producto con el que se tecleó (ver historial del pedido), pero lo
-- tecleado no coincide con las cajas físicas. Las etiquetas imprimen lo que
-- hay en `caja_pesada`, así que se corrige acá y se reimprimen desde la app.
--
-- CÓMO USAR
--   1. Reemplazar en el bloque PESOS_REALES los 22 pesos por los que dicen las
--      cajas físicas (número de caja → peso real). Lote y fechas no se tocan.
--   2. heroku pg:psql --app pesosapp
--      y adentro:  \i scripts/corregir_pesos_1357.sql
--      (NO usar `-f`: psql cerraría la sesión y desharía la transacción
--      antes de poder confirmar).
--   3. Revisar el ANTES/DESPUÉS que imprime. Si cuadra: COMMIT; Si no: ROLLBACK;
--   4. Pedido 1357 → Etiquetas → reimprimir.
--   5. Si el total por producto cambió, ajustar los kg en la factura 48007 de
--      QuickBooks (la app no la reenvía: el pedido está facturado).
--
-- El pedido está facturado y la app no deja editarlo: por eso va por SQL.
-- Queda un evento en el historial del pedido con el detalle del cambio.

BEGIN;

-- Cajas hoy, para comparar con lo que se va a escribir.
SELECT p.nombre AS producto, cp.numero, cp.peso AS peso_actual
  FROM caja_pesada cp
  JOIN detalle_pedido dp ON dp.id = cp.detalle_pedido_id
  JOIN producto p ON p.id = dp.producto_id
 WHERE dp.pedido_id = 1357
   AND dp.es_linea_pedido = TRUE
   AND p.nombre IN ('Pork Chorizo', 'Andouiline Pork Chorizo')
 ORDER BY p.nombre, cp.numero;

SELECT p.nombre AS producto, COUNT(*) AS cajas, SUM(cp.peso) AS kg_antes
  FROM caja_pesada cp
  JOIN detalle_pedido dp ON dp.id = cp.detalle_pedido_id
  JOIN producto p ON p.id = dp.producto_id
 WHERE dp.pedido_id = 1357 AND dp.es_linea_pedido = TRUE
   AND p.nombre IN ('Pork Chorizo', 'Andouiline Pork Chorizo')
 GROUP BY p.nombre ORDER BY p.nombre;

-- ============================ PESOS_REALES ==================================
-- Los valores de abajo son los REGISTRADOS HOY (25/09/2026): hay que
-- reemplazarlos por los reales antes de correr. Formato: (producto, número
-- de caja, peso real en kg).
CREATE TEMP TABLE pesos_reales (producto TEXT, numero INT, peso NUMERIC(8,3))
ON COMMIT DROP;

INSERT INTO pesos_reales VALUES
  ('Andouiline Pork Chorizo',  1, 16.900),
  ('Andouiline Pork Chorizo',  2, 16.950),
  ('Andouiline Pork Chorizo',  3, 17.050),
  ('Andouiline Pork Chorizo',  4, 16.950),
  ('Andouiline Pork Chorizo',  5, 17.150),
  ('Andouiline Pork Chorizo',  6, 15.950),
  ('Andouiline Pork Chorizo',  7, 17.100),
  ('Andouiline Pork Chorizo',  8, 17.050),
  ('Andouiline Pork Chorizo',  9, 15.950),
  ('Andouiline Pork Chorizo', 10, 16.900),
  ('Andouiline Pork Chorizo', 11,  3.150),
  ('Pork Chorizo',             1, 16.900),
  ('Pork Chorizo',             2, 17.050),
  ('Pork Chorizo',             3, 16.950),
  ('Pork Chorizo',             4, 16.800),
  ('Pork Chorizo',             5, 17.050),
  ('Pork Chorizo',             6, 17.050),
  ('Pork Chorizo',             7, 16.800),
  ('Pork Chorizo',             8, 17.050),
  ('Pork Chorizo',             9, 16.850),
  ('Pork Chorizo',            10, 17.100),
  ('Pork Chorizo',            11,  5.150);
-- ============================================================================

-- Guarda: cada fila de pesos_reales tiene que corresponder a UNA caja
-- existente. Si el conteo no da 22, algo está mal escrito: ROLLBACK.
SELECT COUNT(*) AS cajas_que_se_van_a_corregir
  FROM pesos_reales pr
  JOIN producto p ON p.nombre = pr.producto
  JOIN detalle_pedido dp ON dp.producto_id = p.id
                        AND dp.pedido_id = 1357 AND dp.es_linea_pedido = TRUE
  JOIN caja_pesada cp ON cp.detalle_pedido_id = dp.id AND cp.numero = pr.numero;

-- Rastro en el historial: qué caja cambió, de cuánto a cuánto.
INSERT INTO pedido_evento (pedido_id, tipo, descripcion, usuario_id, metadata_json, created_at)
SELECT 1357,
       'caja_corregida',
       'Caja #' || LPAD(cp.numero::TEXT, 2, '0') || ' de ' || p.nombre
         || ': ' || cp.peso || ' kg → ' || pr.peso || ' kg (corrección pesos cruzados)',
       NULL,
       json_build_object('detalle_id', dp.id, 'numero', cp.numero,
                         'peso_anterior', cp.peso, 'peso_nuevo', pr.peso)::TEXT,
       NOW() AT TIME ZONE 'UTC'
  FROM pesos_reales pr
  JOIN producto p ON p.nombre = pr.producto
  JOIN detalle_pedido dp ON dp.producto_id = p.id
                        AND dp.pedido_id = 1357 AND dp.es_linea_pedido = TRUE
  JOIN caja_pesada cp ON cp.detalle_pedido_id = dp.id AND cp.numero = pr.numero
 WHERE cp.peso <> pr.peso;

UPDATE caja_pesada cp
   SET peso = pr.peso
  FROM pesos_reales pr
  JOIN producto p ON p.nombre = pr.producto
  JOIN detalle_pedido dp ON dp.producto_id = p.id
                        AND dp.pedido_id = 1357 AND dp.es_linea_pedido = TRUE
 WHERE cp.detalle_pedido_id = dp.id
   AND cp.numero = pr.numero
   AND cp.peso <> pr.peso;

-- DESPUÉS: comparar con la factura 48007 (171.10 kg Andouiline / 174.75 kg
-- Pork Chorizo). Si cambió, ajustar la factura en QuickBooks.
SELECT p.nombre AS producto, COUNT(*) AS cajas, SUM(cp.peso) AS kg_despues
  FROM caja_pesada cp
  JOIN detalle_pedido dp ON dp.id = cp.detalle_pedido_id
  JOIN producto p ON p.id = dp.producto_id
 WHERE dp.pedido_id = 1357 AND dp.es_linea_pedido = TRUE
   AND p.nombre IN ('Pork Chorizo', 'Andouiline Pork Chorizo')
 GROUP BY p.nombre ORDER BY p.nombre;

-- Revisar arriba y cerrar a mano:
--   COMMIT;    -- si cuadra
--   ROLLBACK;  -- si algo no da
