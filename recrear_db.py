import os

# Establecer las variables de entorno necesarias
os.environ.setdefault("SECRET_KEY", "Casco2021*")
os.environ.setdefault("DEFAULT_USERNAME", "jdasilva")
os.environ.setdefault("DEFAULT_PASSWORD", "Casco2021*")
os.environ.setdefault("DATABASE_URL", "sqlite:///local.db")

from app import app, db
# Importar TODOS los modelos explícitamente para asegurar que SQLAlchemy los detecte
from app import (
    Producto, Cliente, Facturacion, Recepcion, Importacion,
    Pedido, DetallePedido, Rol, Permiso, RolPermiso, Territorio, 
    Vendedor, ClienteVendedor, ListaPrecio, PrecioProducto, 
    ClienteListaPrecio, PrecioClienteProducto
)

print("Iniciando recreación de base de datos...")
print(f"Modelos importados: {len(db.Model.registry._class_registry)} clases")

with app.app_context():
    # Eliminar todas las tablas existentes
    db.drop_all()
    print("Tablas eliminadas")
    
    # Crear todas las tablas
    db.create_all()
    print("Tablas creadas")
    
    # Verificar que las tablas se crearon correctamente
    from sqlalchemy import inspect
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    print(f"Tablas en la base de datos: {tables}")
    
    # Verificar columnas específicas de las tablas problemáticas
    for tabla in ['pedido', 'producto', 'cliente']:
        if tabla in tables:
            columns = [col['name'] for col in inspector.get_columns(tabla)]
            print(f"Columnas de {tabla}: {columns}")
    
    # Crear datos iniciales mínimos
    try:
        # Crear rol por defecto
        rol_admin = Rol(nombre='super_admin', descripcion='Administrador del sistema')
        db.session.add(rol_admin)
        print("Rol admin creado")
        
        # Crear territorio por defecto
        territorio = Territorio(nombre='General', descripcion='Territorio general')
        db.session.add(territorio)
        print("Territorio creado")
        
        # Crear lista de precios por defecto
        lista_default = ListaPrecio(
            nombre='Lista General',
            descripcion='Lista de precios por defecto',
            es_default=True
        )
        db.session.add(lista_default)
        print("Lista de precios creada")
        
        db.session.commit()
        print("Datos iniciales guardados exitosamente")
        
    except Exception as e:
        print(f"Error creando datos iniciales: {e}")
        db.session.rollback()

print("Recreación completa")