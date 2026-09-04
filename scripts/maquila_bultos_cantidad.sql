-- «Bultos» pasa de ser una lista de pesos a ser una CANTIDAD.
--
-- Correr ANTES del push a Heroku:
--   heroku pg:psql --app pesosapp -f scripts/maquila_bultos_cantidad.sql
--   heroku restart --app pesosapp
--
-- Agrega la columna y la rellena contando las filas de `recepcion_bulto` que
-- existan hoy. NO adivina: si una línea tiene una sola fila de bulto porque
-- alguien escribió la cantidad en el campo equivocado, va a quedar en 1 y hay
-- que corregirla a mano en la pantalla — que ya guarda lo que se le pone.
--
-- `recepcion_bulto` NO se borra: queda como tabla muerta con las filas
-- históricas. Nada la escribe ni la lee desde este cambio.
BEGIN;

ALTER TABLE recepcion_linea
  ADD COLUMN cantidad_bultos INTEGER NOT NULL DEFAULT 0;

UPDATE recepcion_linea rl
   SET cantidad_bultos = sub.n
  FROM (SELECT recepcion_linea_id, count(*) AS n
          FROM recepcion_bulto
         GROUP BY recepcion_linea_id) AS sub
 WHERE sub.recepcion_linea_id = rl.id;

COMMIT;
