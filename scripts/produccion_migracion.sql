-- Módulo de producción propia (insumos, fórmulas, lotes, cajas pesadas, mermas y rendimiento).
--
-- Normalmente NO hace falta correrlo: al arrancar, la app crea estas tablas
-- si faltan y, si encuentra las de la primera versión del módulo (lotes
-- apuntando a ingrediente y receta de maquila), las recrea con el catálogo
-- propio (produccion.asegurar_tablas). Este script hace lo mismo a mano,
-- para quien prefiera verlo correr. Los lotes de esa primera versión se
-- pierden en los dos caminos.
--   heroku pg:psql --app pesosapp -f scripts/produccion_migracion.sql
--   heroku restart --app pesosapp
-- No toca ninguna tabla de maquila ni del resto de la app.
BEGIN;
DROP TABLE IF EXISTS produccion_lote_caja;
DROP TABLE IF EXISTS lote_merma;
DROP TABLE IF EXISTS lote_consumo;
DROP TABLE IF EXISTS lote_produccion;
CREATE TABLE produccion_insumo (
	id SERIAL NOT NULL,
	nombre VARCHAR(120) NOT NULL,
	unidad VARCHAR(10) NOT NULL,
	activo BOOLEAN NOT NULL,
	notas TEXT,
	PRIMARY KEY (id),
	UNIQUE (nombre)
);
CREATE TABLE produccion_formula (
	id SERIAL NOT NULL,
	producto_id INTEGER NOT NULL,
	nombre VARCHAR(120) NOT NULL,
	base_kg NUMERIC(10, 3) NOT NULL,
	activa BOOLEAN NOT NULL,
	creada_en TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	creada_por INTEGER,
	PRIMARY KEY (id),
	FOREIGN KEY(producto_id) REFERENCES producto (id),
	FOREIGN KEY(creada_por) REFERENCES vendedor (id)
);
CREATE INDEX ix_produccion_formula_producto_id ON produccion_formula (producto_id);
CREATE TABLE produccion_formula_insumo (
	id SERIAL NOT NULL,
	formula_id INTEGER NOT NULL,
	insumo_id INTEGER NOT NULL,
	cantidad NUMERIC(10, 3) NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_produccion_formula_insumo UNIQUE (formula_id, insumo_id),
	FOREIGN KEY(formula_id) REFERENCES produccion_formula (id) ON DELETE CASCADE,
	FOREIGN KEY(insumo_id) REFERENCES produccion_insumo (id)
);
CREATE INDEX ix_produccion_formula_insumo_formula_id ON produccion_formula_insumo (formula_id);
CREATE TABLE lote_produccion (
	id SERIAL NOT NULL,
	codigo VARCHAR(20) NOT NULL,
	producto_id INTEGER NOT NULL,
	formula_id INTEGER,
	lote VARCHAR(50) NOT NULL,
	fecha_produccion DATE NOT NULL,
	fecha_vencimiento DATE,
	peso_adicional NUMERIC(10, 3) NOT NULL,
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
	FOREIGN KEY(formula_id) REFERENCES produccion_formula (id),
	FOREIGN KEY(registrado_por) REFERENCES vendedor (id),
	FOREIGN KEY(cerrado_por) REFERENCES vendedor (id),
	FOREIGN KEY(anulado_por) REFERENCES vendedor (id)
);
CREATE UNIQUE INDEX ix_lote_produccion_codigo ON lote_produccion (codigo);
CREATE INDEX ix_lote_produccion_estado ON lote_produccion (estado);
CREATE INDEX ix_lote_produccion_fecha_produccion ON lote_produccion (fecha_produccion);
CREATE INDEX ix_lote_produccion_lote ON lote_produccion (lote);
CREATE INDEX ix_lote_produccion_producto_id ON lote_produccion (producto_id);
CREATE INDEX ix_lote_produccion_producto_lote ON lote_produccion (producto_id, lote);
CREATE TABLE lote_consumo (
	id SERIAL NOT NULL,
	lote_id INTEGER NOT NULL,
	insumo_id INTEGER NOT NULL,
	cantidad_teorica NUMERIC(10, 3) NOT NULL,
	cantidad_real NUMERIC(10, 3) NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_lote_consumo UNIQUE (lote_id, insumo_id),
	FOREIGN KEY(lote_id) REFERENCES lote_produccion (id) ON DELETE CASCADE,
	FOREIGN KEY(insumo_id) REFERENCES produccion_insumo (id)
);
CREATE INDEX ix_lote_consumo_insumo_id ON lote_consumo (insumo_id);
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
CREATE TABLE produccion_lote_caja (
	id SERIAL NOT NULL,
	lote_id INTEGER NOT NULL,
	caja_pesada_id INTEGER NOT NULL,
	registrado_en TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(lote_id) REFERENCES lote_produccion (id) ON DELETE CASCADE,
	FOREIGN KEY(caja_pesada_id) REFERENCES caja_pesada (id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX ix_produccion_lote_caja_caja_pesada_id ON produccion_lote_caja (caja_pesada_id);
CREATE INDEX ix_produccion_lote_caja_lote_id ON produccion_lote_caja (lote_id);
COMMIT;
