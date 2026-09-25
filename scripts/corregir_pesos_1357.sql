-- Pedido 1357 (DeliNova, factura 48007): cajas de Pork Chorizo y Andouiline
-- Pork Chorizo registradas en el producto equivocado. El código no las
-- mezcló: cada caja quedó en el producto con el que se tecleó (ver historial
-- del pedido), pero lo tecleado no coincide con las cajas físicas. Las
-- etiquetas imprimen lo que hay en `caja_pesada`, así que se corrige acá y se
-- reimprimen desde la app.
--
-- Al cotejar etiquetas con cajas (JM, 25/09/2026):
--   4 etiquetas de Andouiline son de Pork Chorizo:   17.15, 15.95, 15.95, 16.90
--   5 etiquetas de Pork Chorizo son de Andouiline:   17.05, 16.80, 17.05, 16.80, 16.85
-- Resultado: Andouiline pasa de 11 a 12 cajas (171.10 → 189.70 kg) y Pork
-- Chorizo de 11 a 10 (174.75 → 156.15 kg). El total (345.85 kg) no cambia.
--
-- Donde un peso se repite (16.90 en Andouiline; 17.05 en Pork Chorizo) se
-- mueve cualquiera de las cajas: mismo peso, mismo lote y mismas fechas, así
-- que el resultado es idéntico.
--
-- CÓMO USAR
--   1. heroku pg:psql --app pesosapp
--      y adentro:  \i scripts/corregir_pesos_1357.sql
--      (NO usar `-f`: psql cerraría la sesión y desharía la transacción
--      antes de poder confirmar).
--   2. Revisar el ANTES/DESPUÉS que imprime: 12 cajas / 189.70 kg y
--      10 cajas / 156.15 kg. Si cuadra: COMMIT;  Si no: ROLLBACK;
--   3. Pedido 1357 → Etiquetas → reimprimir.
--   4. Ajustar los kg de las dos líneas en la factura 48007 de QuickBooks
--      (Andouiline 189.70, Pork Chorizo 156.15). La app no la reenvía: el
--      pedido está facturado.
--
-- El pedido está facturado y la app no deja editarlo: por eso va por SQL.
-- Queda un evento por caja movida en el historial del pedido. Los números
-- de caja se reasignan corridos (1..12 y 1..10): las que ya estaban conservan
-- su orden y las que llegan van al final.

BEGIN;

-- Las dos líneas del pedido.
CREATE TEMP TABLE lineas ON COMMIT DROP AS
SELECT dp.id AS detalle_id, p.nombre AS producto
  FROM detalle_pedido dp
  JOIN producto p ON p.id = dp.producto_id
 WHERE dp.pedido_id = 1357
   AND dp.es_linea_pedido = TRUE
   AND p.nombre IN ('Pork Chorizo', 'Andouiline Pork Chorizo');

-- Tiene que haber exactamente una línea por producto.
SELECT producto, detalle_id FROM lineas ORDER BY producto;

-- ANTES
SELECT l.producto, cp.numero, cp.peso
  FROM caja_pesada cp JOIN lineas l ON l.detalle_id = cp.detalle_pedido_id
 ORDER BY l.producto, cp.numero;

SELECT l.producto, COUNT(*) AS cajas, SUM(cp.peso) AS kg_antes
  FROM caja_pesada cp JOIN lineas l ON l.detalle_id = cp.detalle_pedido_id
 GROUP BY l.producto ORDER BY l.producto;

-- Cajas a mover: (producto donde está hoy, peso, cuántas de ese peso).
CREATE TEMP TABLE mover (desde TEXT, peso NUMERIC(8,3), cuantas INT) ON COMMIT DROP;
INSERT INTO mover VALUES
  ('Andouiline Pork Chorizo', 17.150, 1),
  ('Andouiline Pork Chorizo', 15.950, 2),
  ('Andouiline Pork Chorizo', 16.900, 1),
  ('Pork Chorizo',            17.050, 2),
  ('Pork Chorizo',            16.800, 2),
  ('Pork Chorizo',            16.850, 1);

-- Resuelve cada fila de `mover` a cajas concretas (las de menor número).
CREATE TEMP TABLE cajas_a_mover ON COMMIT DROP AS
SELECT c.id AS caja_id, c.numero, c.peso, l.producto AS desde,
       l.detalle_id AS detalle_desde,
       (SELECT detalle_id FROM lineas WHERE producto <> l.producto) AS detalle_hacia,
       (SELECT producto   FROM lineas WHERE producto <> l.producto) AS hacia
  FROM mover m
  JOIN lineas l ON l.producto = m.desde
  JOIN LATERAL (
        SELECT cp.id, cp.numero, cp.peso
          FROM caja_pesada cp
         WHERE cp.detalle_pedido_id = l.detalle_id AND cp.peso = m.peso
         ORDER BY cp.numero
         LIMIT m.cuantas
       ) c ON TRUE;

-- Guarda: deben ser 9 cajas (4 + 5). Si no, faltó alguna con ese peso: ROLLBACK.
SELECT desde, numero, peso, hacia FROM cajas_a_mover ORDER BY desde, numero;
SELECT COUNT(*) AS cajas_que_se_mueven FROM cajas_a_mover;

-- Rastro en el historial: qué caja se movió y hacia dónde.
INSERT INTO pedido_evento (pedido_id, tipo, descripcion, usuario_id, metadata_json, created_at)
SELECT 1357,
       'caja_corregida',
       'Caja #' || LPAD(numero::TEXT, 2, '0') || ' de ' || desde || ' (' || peso
         || ' kg) movida a ' || hacia || ' (corrección de cajas cruzadas)',
       NULL,
       json_build_object('caja_pesada_id', caja_id, 'numero_anterior', numero,
                         'peso', peso, 'detalle_desde', detalle_desde,
                         'detalle_hacia', detalle_hacia)::TEXT,
       NOW() AT TIME ZONE 'UTC'
  FROM cajas_a_mover;

-- Mover. Antes se corren los números fuera de rango para no chocar con el
-- índice único (detalle_pedido_id, numero) mientras se reasignan.
UPDATE caja_pesada cp
   SET numero = cp.numero + 1000
 WHERE cp.detalle_pedido_id IN (SELECT detalle_id FROM lineas);

UPDATE caja_pesada cp
   SET detalle_pedido_id = m.detalle_hacia,
       -- +2000: las que llegan quedan detrás de las que ya estaban.
       numero = cp.numero + 1000
  FROM cajas_a_mover m
 WHERE cp.id = m.caja_id;

-- Renumerar 1..N por línea, en el orden que quedó.
UPDATE caja_pesada cp
   SET numero = r.n
  FROM (SELECT id, ROW_NUMBER() OVER (PARTITION BY detalle_pedido_id ORDER BY numero) AS n
          FROM caja_pesada
         WHERE detalle_pedido_id IN (SELECT detalle_id FROM lineas)) r
 WHERE cp.id = r.id;

-- DESPUÉS: esperado Andouiline 12 cajas / 189.700 kg, Pork Chorizo 10 / 156.150.
SELECT l.producto, cp.numero, cp.peso
  FROM caja_pesada cp JOIN lineas l ON l.detalle_id = cp.detalle_pedido_id
 ORDER BY l.producto, cp.numero;

SELECT l.producto, COUNT(*) AS cajas, SUM(cp.peso) AS kg_despues
  FROM caja_pesada cp JOIN lineas l ON l.detalle_id = cp.detalle_pedido_id
 GROUP BY l.producto ORDER BY l.producto;

-- Revisar arriba y cerrar a mano:
--   COMMIT;    -- si cuadra
--   ROLLBACK;  -- si algo no da
