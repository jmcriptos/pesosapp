-- Editar recepciones. Correr ANTES del push a Heroku:
--   heroku pg:psql --app pesosapp -f scripts/maquila_editar_migracion.sql
--   heroku restart --app pesosapp
-- Aditivo y nullable: no toca ninguna fila existente.
BEGIN;

ALTER TABLE recepcion_linea ADD COLUMN anulada_en TIMESTAMP;

COMMIT;
