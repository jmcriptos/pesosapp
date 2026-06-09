# init_multivendor_data.py
import os
import sys
import secrets
from datetime import datetime, date

# Asegurarse de que podemos importar desde app.py
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def crear_roles_y_permisos():
    """Crea los roles y permisos básicos del sistema"""
    from app import app, db, Rol, Permiso, RolPermiso
    
    with app.app_context():
        print("Creando permisos...")
        
        # Definir permisos básicos
        permisos_data = [
            {'nombre': 'ver_clientes', 'descripcion': 'Ver información de clientes', 'categoria': 'clientes'},
            {'nombre': 'crear_clientes', 'descripcion': 'Crear nuevos clientes', 'categoria': 'clientes'},
            {'nombre': 'editar_clientes', 'descripcion': 'Modificar información de clientes', 'categoria': 'clientes'},
            {'nombre': 'eliminar_clientes', 'descripcion': 'Eliminar clientes', 'categoria': 'clientes'},
            {'nombre': 'ver_pedidos', 'descripcion': 'Ver pedidos', 'categoria': 'pedidos'},
            {'nombre': 'crear_pedidos', 'descripcion': 'Crear nuevos pedidos', 'categoria': 'pedidos'},
            {'nombre': 'editar_pedidos', 'descripcion': 'Modificar pedidos', 'categoria': 'pedidos'},
            {'nombre': 'eliminar_pedidos', 'descripcion': 'Eliminar pedidos', 'categoria': 'pedidos'},
            {'nombre': 'ver_productos', 'descripcion': 'Ver catálogo de productos', 'categoria': 'productos'},
            {'nombre': 'crear_productos', 'descripcion': 'Agregar nuevos productos', 'categoria': 'productos'},
            {'nombre': 'ver_facturacion', 'descripcion': 'Ver registros de facturación', 'categoria': 'facturacion'},
            {'nombre': 'crear_facturacion', 'descripcion': 'Registrar nuevas facturaciones', 'categoria': 'facturacion'},
            {'nombre': 'ver_recepciones', 'descripcion': 'Ver recepciones de mercancía', 'categoria': 'recepciones'},
            {'nombre': 'crear_recepciones', 'descripcion': 'Registrar recepciones', 'categoria': 'recepciones'},
            {'nombre': 'gestionar_usuarios', 'descripcion': 'Crear y gestionar usuarios', 'categoria': 'admin'},
            {'nombre': 'ver_reportes_globales', 'descripcion': 'Ver todos los reportes', 'categoria': 'reportes'},
        ]
        
        # Crear permisos
        permisos_creados = {}
        for permiso_data in permisos_data:
            permiso_existente = Permiso.query.filter_by(nombre=permiso_data['nombre']).first()
            if not permiso_existente:
                permiso = Permiso(**permiso_data)
                db.session.add(permiso)
                db.session.flush()
                permisos_creados[permiso_data['nombre']] = permiso
                print(f"  ✓ Permiso creado: {permiso_data['nombre']}")
            else:
                permisos_creados[permiso_data['nombre']] = permiso_existente
                print(f"  - Permiso ya existe: {permiso_data['nombre']}")
        
        print("\nCreando roles...")
        
        # Definir roles
        roles_data = [
            {
                'nombre': 'super_admin',
                'descripcion': 'Super Administrador - Acceso total',
                'nivel_jerarquia': 10,
                'permisos': list(permisos_creados.keys())  # Todos los permisos
            },
            {
                'nombre': 'vendedor',
                'descripcion': 'Vendedor - Acceso básico',
                'nivel_jerarquia': 1,
                'permisos': [
                    'ver_clientes', 'crear_clientes',
                    'ver_pedidos', 'crear_pedidos',
                    'ver_productos',
                    'ver_facturacion', 'crear_facturacion',
                    'ver_recepciones'
                ]
            }
        ]
        
        # Crear roles y asignar permisos
        for rol_data in roles_data:
            rol_existente = Rol.query.filter_by(nombre=rol_data['nombre']).first()
            if not rol_existente:
                rol = Rol(
                    nombre=rol_data['nombre'],
                    descripcion=rol_data['descripcion'],
                    nivel_jerarquia=rol_data['nivel_jerarquia']
                )
                db.session.add(rol)
                db.session.flush()
                
                # Asignar permisos al rol
                for permiso_nombre in rol_data['permisos']:
                    if permiso_nombre in permisos_creados:
                        rol_permiso = RolPermiso(
                            rol=rol,
                            permiso=permisos_creados[permiso_nombre],
                            puede_leer=True,
                            puede_crear='crear_' in permiso_nombre,
                            puede_editar='editar_' in permiso_nombre,
                            puede_eliminar='eliminar_' in permiso_nombre
                        )
                        db.session.add(rol_permiso)
                
                print(f"  ✓ Rol creado: {rol_data['nombre']}")
            else:
                print(f"  - Rol ya existe: {rol_data['nombre']}")
        
        db.session.commit()
        print("✅ Roles y permisos creados exitosamente")

def crear_territorio_inicial():
    """Crea un territorio básico"""
    from app import app, db, Territorio
    
    with app.app_context():
        print("Creando territorio inicial...")
        
        territorio_existente = Territorio.query.filter_by(nombre='General').first()
        if not territorio_existente:
            territorio = Territorio(
                nombre='General',
                descripcion='Territorio general para todos los vendedores',
                tipo='general'
            )
            db.session.add(territorio)
            db.session.commit()
            print("  ✓ Territorio 'General' creado")
        else:
            print("  - Territorio 'General' ya existe")

def crear_vendedor_admin():
    """Crea el vendedor administrador inicial"""
    from app import app, db, Vendedor, Rol
    
    with app.app_context():
        print("Creando vendedor administrador...")
        
        rol_admin = Rol.query.filter_by(nombre='super_admin').first()
        if not rol_admin:
            print("❌ Error: Rol super_admin no encontrado")
            return
        
        admin_existente = Vendedor.query.filter_by(username='admin').first()
        if not admin_existente:
            admin = Vendedor(
                username='admin',
                email='admin@jomarfoods.com',
                nombre_completo='Administrador del Sistema',
                telefono='+297-XXX-XXXX',
                rol=rol_admin,
                fecha_ingreso=date.today(),
                activo=True
            )
            admin_password = os.environ.get('ADMIN_PASSWORD') or secrets.token_urlsafe(16)
            admin.set_password(admin_password)
            if hasattr(admin, 'debe_cambiar_password'):
                admin.debe_cambiar_password = True
            db.session.add(admin)
            db.session.commit()
            print("  ✓ Vendedor administrador creado")
            print("     Usuario: admin")
            print(f"     Contraseña temporal (guárdala, no se vuelve a mostrar): {admin_password}")
            print("     ⚠️  Debe cambiarse en el primer inicio de sesión")
        else:
            print("  - Vendedor administrador ya existe")

def migrar_usuario_actual():
    """Migra el usuario actual del sistema a un vendedor"""
    from app import app, db, Vendedor, Rol
    
    with app.app_context():
        print("Migrando usuario actual...")
        
        # Obtener credenciales del entorno (sin defaults débiles)
        default_username = os.environ.get("DEFAULT_USERNAME", "jomar")
        default_password = os.environ.get("DEFAULT_PASSWORD") or secrets.token_urlsafe(16)
        
        vendedor_existente = Vendedor.query.filter_by(username=default_username).first()
        if not vendedor_existente:
            rol_admin = Rol.query.filter_by(nombre='super_admin').first()
            if rol_admin:
                vendedor_migrado = Vendedor(
                    username=default_username,
                    email=f'{default_username}@jomarfoods.com',
                    nombre_completo='Usuario Principal',
                    rol=rol_admin,
                    fecha_ingreso=date.today(),
                    activo=True
                )
                vendedor_migrado.set_password(default_password)
                db.session.add(vendedor_migrado)
                db.session.commit()
                print(f"  ✓ Usuario {default_username} migrado a vendedor")
            else:
                print("❌ Error: Rol super_admin no encontrado")
        else:
            print(f"  - Usuario {default_username} ya existe como vendedor")

def main():
    """Ejecuta toda la inicialización"""
    print("🚀 Iniciando configuración del sistema multi-vendedor...")
    print("=" * 60)
    
    try:
        crear_roles_y_permisos()
        print()
        crear_territorio_inicial()
        print()
        crear_vendedor_admin()
        print()
        migrar_usuario_actual()
        print()
        print("=" * 60)
        print("✅ ¡Inicialización completada exitosamente!")
        print()
        print("📋 Próximos pasos:")
        print("   1. Reiniciar la aplicación")
        print("   2. Usar las nuevas credenciales para login")
        print("   3. Crear vendedores adicionales desde el admin")
        
    except Exception as e:
        print(f"❌ Error durante la inicialización: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()