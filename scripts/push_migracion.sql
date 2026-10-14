-- Notificaciones push de pedidos nuevos: tabla de suscripciones.
--
-- Normalmente NO hace falta correrlo: al arrancar, la app crea esta tabla si
-- falta (app.py, _asegurar_tabla_push), igual que evento_auditoria y las del
-- módulo de producción. Este script hace lo mismo a mano, para quien
-- prefiera verlo correr o restaurar la tabla en una base copiada.
--   heroku pg:psql --app pesosapp -f scripts/push_migracion.sql
-- No toca ninguna otra tabla.
BEGIN;
CREATE TABLE IF NOT EXISTS suscripcion_push (
	id SERIAL NOT NULL,
	vendedor_id INTEGER NOT NULL,
	endpoint VARCHAR(1000) NOT NULL,
	p256dh VARCHAR(255) NOT NULL,
	auth VARCHAR(255) NOT NULL,
	user_agent VARCHAR(255),
	creado_en TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	ultimo_envio_en TIMESTAMP WITHOUT TIME ZONE,
	PRIMARY KEY (id),
	FOREIGN KEY(vendedor_id) REFERENCES vendedor (id) ON DELETE CASCADE,
	UNIQUE (endpoint)
);
CREATE INDEX IF NOT EXISTS ix_suscripcion_push_vendedor_id ON suscripcion_push (vendedor_id);
COMMIT;
