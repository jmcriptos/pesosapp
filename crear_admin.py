from app import app, db, Vendedor, Rol
from werkzeug.security import generate_password_hash

with app.app_context():
    # Busca el rol super_admin
    rol = Rol.query.filter_by(nombre='super_admin').first()
    if not rol:
        print("❌ No existe el rol super_admin. Debes crearlo primero desde la app o la base de datos.")
        exit(1)

    # Verifica si el usuario ya existe
    if Vendedor.query.filter_by(username='admin').first():
        print("❌ Ya existe un usuario con ese username.")
        exit(1)

    # Crea el usuario
    v = Vendedor(
        username='admin',
        email='jomarfood@gmail.com',
        nombre_completo='Jose Da Silva',
        telefono='6905484',
        rol_id=rol.id,
        activo=True
    )
    v.password_hash = generate_password_hash('Jomar2024!')

    try:
        db.session.add(v)
        db.session.commit()
        print("✅ Usuario super_admin creado correctamente.")
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error al crear el usuario: {str(e)}") 