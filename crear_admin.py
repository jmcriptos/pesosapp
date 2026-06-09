import os
import secrets

from app import app, db, Vendedor, Rol
from werkzeug.security import generate_password_hash

with app.app_context():
    # Busca el rol super_admin
    rol = Rol.query.filter_by(nombre='super_admin').first()
    if not rol:
        print("❌ No existe el rol super_admin. Debes crearlo primero desde la app o la base de datos.")
        exit(1)

    username = os.environ.get('ADMIN_USERNAME', 'admin')

    # Verifica si el usuario ya existe
    if Vendedor.query.filter_by(username=username).first():
        print("❌ Ya existe un usuario con ese username.")
        exit(1)

    # La contraseña NUNCA debe estar hardcodeada. Se toma de ADMIN_PASSWORD
    # o se genera una aleatoria que se imprime una sola vez.
    password = os.environ.get('ADMIN_PASSWORD')
    generada = False
    if not password:
        password = secrets.token_urlsafe(16)
        generada = True

    # Crea el usuario
    v = Vendedor(
        username=username,
        email=os.environ.get('ADMIN_EMAIL', 'jomarfood@gmail.com'),
        nombre_completo=os.environ.get('ADMIN_NOMBRE', 'Administrador'),
        telefono=os.environ.get('ADMIN_TELEFONO', ''),
        rol_id=rol.id,
        activo=True
    )
    v.password_hash = generate_password_hash(password)
    # Forzar cambio de contraseña en el primer inicio de sesión si el modelo lo soporta.
    if hasattr(v, 'debe_cambiar_password'):
        v.debe_cambiar_password = True

    try:
        db.session.add(v)
        db.session.commit()
        print(f"✅ Usuario super_admin '{username}' creado correctamente.")
        if generada:
            print(f"🔑 Contraseña temporal (guárdala ahora, no se vuelve a mostrar): {password}")
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error al crear el usuario: {str(e)}")
