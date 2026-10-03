-- Módulo de producción propia (lotes, mermas y rendimiento). Correr ANTES
-- del push a Heroku:
--   heroku pg:psql --app pesosapp -f scripts/produccion_migracion.sql
--   heroku restart --app pesosapp
-- No modifica ninguna tabla existente: solo crea las tres nuevas. Requiere
-- que las tablas de maquila (ingrediente, receta) ya existan.
BEGIN;
CREATE TABLE lote_produccion (
	id SERIAL NOT NULL,
	codigo VARCHAR(20) NOT NULL,
	producto_id INTEGER NOT NULL,
	receta_id INTEGER,
	lote VARCHAR(50) NOT NULL,
	fecha_produccion DATE NOT NULL,
	fecha_vencimiento DATE,
	peso_producido NUMERIC(10, 3) NOT NULL,
	unidades_producidas INTEGER,
	cajas_producidas INTEGER,
	estado VARCHAR(20) NOT NULL,
	notas TEXT,
	registrado_por INTEGER NOT NULL,
	registrado_en TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	cerrado_por INTEGER,
	cerrado_en TIMESTAMP WITHOUT TIME ZONE,
	anulado_por INTEGER,
	anulado_en TIMESTAMP WITHOUT TIME ZONE,
	motivo_anulacion TEXT,
	PRIMARY KEY (id),
	FOREIGN KEY(producto_id) REFERENCES producto (id),
	FOREIGN KEY(receta_id) REFERENCES receta (id),
	FOREIGN KEY(registrado_por) REFERENCES vendedor (id),
	FOREIGN KEY(cerrado_por) REFERENCES vendedor (id),
	FOREIGN KEY(anulado_por) REFERENCES vendedor (id)
);
CREATE INDEX ix_lote_produccion_producto_lote ON lote_produccion (producto_id, lote);
CREATE INDEX ix_lote_produccion_estado ON lote_produccion (estado);
CREATE INDEX ix_lote_produccion_fecha_produccion ON lote_produccion (fecha_produccion);
CREATE INDEX ix_lote_produccion_lote ON lote_produccion (lote);
CREATE UNIQUE INDEX ix_lote_produccion_codigo ON lote_produccion (codigo);
CREATE INDEX ix_lote_produccion_producto_id ON lote_produccion (producto_id);
CREATE TABLE lote_consumo (
	id SERIAL NOT NULL,
	lote_id INTEGER NOT NULL,
	ingrediente_id INTEGER NOT NULL,
	cantidad_teorica NUMERIC(10, 3) NOT NULL,
	cantidad_real NUMERIC(10, 3) NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_lote_consumo UNIQUE (lote_id, ingrediente_id),
	FOREIGN KEY(lote_id) REFERENCES lote_produccion (id) ON DELETE CASCADE,
	FOREIGN KEY(ingrediente_id) REFERENCES ingrediente (id)
);
CREATE INDEX ix_lote_consumo_ingrediente_id ON lote_consumo (ingrediente_id);
CREATE INDEX ix_lote_consumo_lote_id ON lote_consumo (lote_id);
CREATE TABLE lote_merma (
	id SERIAL NOT NULL,
	lote_id INTEGER NOT NULL,
	tipo VARCHAR(20) NOT NULL,
	cantidad NUMERIC(10, 3) NOT NULL,
	motivo TEXT,
	PRIMARY KEY (id),
	FOREIGN KEY(lote_id) REFERENCES lote_produccion (id) ON DELETE CASCADE
);
CREATE INDEX ix_lote_merma_lote_id ON lote_merma (lote_id);
COMMIT;
