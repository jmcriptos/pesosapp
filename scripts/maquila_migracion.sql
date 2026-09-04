-- Módulo de maquila. Correr ANTES del push a Heroku:
--   heroku pg:psql --app pesosapp -f scripts/maquila_migracion.sql
--   heroku restart --app pesosapp
-- No modifica ninguna tabla existente: solo crea las doce nuevas.
BEGIN;
CREATE TABLE ingrediente (
	id SERIAL NOT NULL,
	nombre VARCHAR(120) NOT NULL,
	unidad VARCHAR(10) NOT NULL,
	activo BOOLEAN NOT NULL,
	notas TEXT,
	PRIMARY KEY (id),
	UNIQUE (nombre)
);
CREATE TABLE recepcion_ingrediente (
	id SERIAL NOT NULL,
	codigo VARCHAR(20) NOT NULL,
	cliente_id INTEGER NOT NULL,
	recibido_en DATE NOT NULL,
	documento_cliente VARCHAR(100),
	temperatura NUMERIC(5, 2),
	transportista VARCHAR(120),
	firma BYTEA,
	firma_mimetype VARCHAR(50),
	notas TEXT,
	registrado_por INTEGER NOT NULL,
	registrado_en TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	anulada_en TIMESTAMP WITHOUT TIME ZONE,
	anulada_por INTEGER,
	motivo_anulacion TEXT,
	PRIMARY KEY (id),
	FOREIGN KEY(cliente_id) REFERENCES cliente (id),
	FOREIGN KEY(registrado_por) REFERENCES vendedor (id),
	FOREIGN KEY(anulada_por) REFERENCES vendedor (id)
);
CREATE INDEX ix_recepcion_ingrediente_cliente_id ON recepcion_ingrediente (cliente_id);
CREATE UNIQUE INDEX ix_recepcion_ingrediente_codigo ON recepcion_ingrediente (codigo);
CREATE TABLE recepcion_linea (
	id SERIAL NOT NULL,
	recepcion_id INTEGER NOT NULL,
	ingrediente_id INTEGER NOT NULL,
	lote_cliente VARCHAR(50),
	fecha_vencimiento DATE,
	peso_total NUMERIC(10, 3) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(recepcion_id) REFERENCES recepcion_ingrediente (id) ON DELETE CASCADE,
	FOREIGN KEY(ingrediente_id) REFERENCES ingrediente (id)
);
CREATE INDEX ix_recepcion_linea_ingrediente_id ON recepcion_linea (ingrediente_id);
CREATE INDEX ix_recepcion_linea_recepcion_id ON recepcion_linea (recepcion_id);
CREATE TABLE recepcion_bulto (
	id SERIAL NOT NULL,
	recepcion_linea_id INTEGER NOT NULL,
	numero INTEGER NOT NULL,
	peso NUMERIC(8, 3) NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_bulto_linea_numero UNIQUE (recepcion_linea_id, numero),
	FOREIGN KEY(recepcion_linea_id) REFERENCES recepcion_linea (id) ON DELETE CASCADE
);
CREATE INDEX ix_recepcion_bulto_recepcion_linea_id ON recepcion_bulto (recepcion_linea_id);
CREATE TABLE recepcion_foto (
	id SERIAL NOT NULL,
	recepcion_id INTEGER NOT NULL,
	imagen BYTEA NOT NULL,
	mimetype VARCHAR(50) NOT NULL,
	subida_en TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(recepcion_id) REFERENCES recepcion_ingrediente (id) ON DELETE CASCADE
);
CREATE INDEX ix_recepcion_foto_recepcion_id ON recepcion_foto (recepcion_id);
CREATE TABLE receta (
	id SERIAL NOT NULL,
	producto_id INTEGER NOT NULL,
	cliente_id INTEGER,
	nombre VARCHAR(120) NOT NULL,
	base_kg NUMERIC(10, 3) NOT NULL,
	activa BOOLEAN NOT NULL,
	creada_en TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	creada_por INTEGER,
	PRIMARY KEY (id),
	FOREIGN KEY(producto_id) REFERENCES producto (id),
	FOREIGN KEY(cliente_id) REFERENCES cliente (id),
	FOREIGN KEY(creada_por) REFERENCES vendedor (id)
);
CREATE INDEX ix_receta_producto_id ON receta (producto_id);
CREATE INDEX ix_receta_cliente_id ON receta (cliente_id);
CREATE TABLE receta_ingrediente (
	id SERIAL NOT NULL,
	receta_id INTEGER NOT NULL,
	ingrediente_id INTEGER NOT NULL,
	cantidad NUMERIC(10, 3) NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_receta_ingrediente UNIQUE (receta_id, ingrediente_id),
	FOREIGN KEY(receta_id) REFERENCES receta (id) ON DELETE CASCADE,
	FOREIGN KEY(ingrediente_id) REFERENCES ingrediente (id)
);
CREATE INDEX ix_receta_ingrediente_receta_id ON receta_ingrediente (receta_id);
CREATE TABLE corrida_produccion (
	id SERIAL NOT NULL,
	codigo VARCHAR(20) NOT NULL,
	cliente_id INTEGER NOT NULL,
	producto_id INTEGER NOT NULL,
	receta_id INTEGER,
	lote VARCHAR(50) NOT NULL,
	fecha_produccion DATE NOT NULL,
	fecha_vencimiento DATE,
	estado VARCHAR(20) NOT NULL,
	notas TEXT,
	registrado_por INTEGER NOT NULL,
	registrado_en TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	cerrada_por INTEGER,
	cerrada_en TIMESTAMP WITHOUT TIME ZONE,
	PRIMARY KEY (id),
	CONSTRAINT uq_corrida_cliente_lote UNIQUE (cliente_id, lote),
	FOREIGN KEY(cliente_id) REFERENCES cliente (id),
	FOREIGN KEY(producto_id) REFERENCES producto (id),
	FOREIGN KEY(receta_id) REFERENCES receta (id),
	FOREIGN KEY(registrado_por) REFERENCES vendedor (id),
	FOREIGN KEY(cerrada_por) REFERENCES vendedor (id)
);
CREATE INDEX ix_corrida_produccion_cliente_id ON corrida_produccion (cliente_id);
CREATE INDEX ix_corrida_produccion_producto_id ON corrida_produccion (producto_id);
CREATE UNIQUE INDEX ix_corrida_produccion_codigo ON corrida_produccion (codigo);
CREATE INDEX ix_corrida_produccion_lote ON corrida_produccion (lote);
CREATE TABLE corrida_caja (
	id SERIAL NOT NULL,
	corrida_id INTEGER NOT NULL,
	numero INTEGER NOT NULL,
	peso NUMERIC(8, 3) NOT NULL,
	caja_pesada_id INTEGER,
	anulada_en TIMESTAMP WITHOUT TIME ZONE,
	motivo_anulacion TEXT,
	PRIMARY KEY (id),
	CONSTRAINT uq_corrida_caja_numero UNIQUE (corrida_id, numero),
	FOREIGN KEY(corrida_id) REFERENCES corrida_produccion (id) ON DELETE CASCADE,
	FOREIGN KEY(caja_pesada_id) REFERENCES caja_pesada (id) ON DELETE SET NULL
);
CREATE UNIQUE INDEX ix_corrida_caja_caja_pesada_id ON corrida_caja (caja_pesada_id);
CREATE INDEX ix_corrida_caja_corrida_id ON corrida_caja (corrida_id);
CREATE TABLE corrida_consumo (
	id SERIAL NOT NULL,
	corrida_id INTEGER NOT NULL,
	ingrediente_id INTEGER NOT NULL,
	cantidad_teorica NUMERIC(10, 3) NOT NULL,
	cantidad_real NUMERIC(10, 3) NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_corrida_consumo UNIQUE (corrida_id, ingrediente_id),
	FOREIGN KEY(corrida_id) REFERENCES corrida_produccion (id) ON DELETE CASCADE,
	FOREIGN KEY(ingrediente_id) REFERENCES ingrediente (id)
);
CREATE INDEX ix_corrida_consumo_corrida_id ON corrida_consumo (corrida_id);
CREATE TABLE corrida_consumo_origen (
	id SERIAL NOT NULL,
	corrida_consumo_id INTEGER NOT NULL,
	recepcion_linea_id INTEGER NOT NULL,
	cantidad NUMERIC(10, 3) NOT NULL,
	automatico BOOLEAN NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(corrida_consumo_id) REFERENCES corrida_consumo (id) ON DELETE CASCADE,
	FOREIGN KEY(recepcion_linea_id) REFERENCES recepcion_linea (id)
);
CREATE INDEX ix_corrida_consumo_origen_corrida_consumo_id ON corrida_consumo_origen (corrida_consumo_id);
CREATE INDEX ix_corrida_consumo_origen_recepcion_linea_id ON corrida_consumo_origen (recepcion_linea_id);
CREATE TABLE movimiento_ingrediente (
	id SERIAL NOT NULL,
	cliente_id INTEGER NOT NULL,
	ingrediente_id INTEGER NOT NULL,
	recepcion_linea_id INTEGER,
	tipo VARCHAR(20) NOT NULL,
	cantidad NUMERIC(10, 3) NOT NULL,
	origen_tipo VARCHAR(20) NOT NULL,
	origen_id INTEGER,
	motivo TEXT,
	registrado_por INTEGER NOT NULL,
	registrado_en TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(cliente_id) REFERENCES cliente (id),
	FOREIGN KEY(ingrediente_id) REFERENCES ingrediente (id),
	FOREIGN KEY(recepcion_linea_id) REFERENCES recepcion_linea (id),
	FOREIGN KEY(registrado_por) REFERENCES vendedor (id)
);
CREATE INDEX ix_movimiento_ingrediente_ingrediente_id ON movimiento_ingrediente (ingrediente_id);
CREATE INDEX ix_movimiento_ingrediente_recepcion_linea_id ON movimiento_ingrediente (recepcion_linea_id);
CREATE INDEX ix_movimiento_ingrediente_cliente_id ON movimiento_ingrediente (cliente_id);
CREATE INDEX ix_mov_cliente_ingr_fecha ON movimiento_ingrediente (cliente_id, ingrediente_id, registrado_en);
COMMIT;
