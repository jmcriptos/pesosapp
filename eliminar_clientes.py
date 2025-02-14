from app import db, Cliente, app  # Asegúrate de importar tu aplicación

def eliminar_todos_los_clientes():
    try:
        # Eliminar todos los registros de la tabla Cliente
        Cliente.query.delete()
        db.session.commit()
        print("Todos los clientes han sido eliminados exitosamente.")
    except Exception as e:
        db.session.rollback()
        print(f"Error al eliminar los clientes: {str(e)}")

if __name__ == "__main__":
    with app.app_context():  # Configurar el contexto de la aplicación
        eliminar_todos_los_clientes()
