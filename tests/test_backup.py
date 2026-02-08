# tests/test_backup.py
"""Tests para Story 2.1: Backup automático de base de datos."""
import os
import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

from app import app as flask_app, db as _db


@pytest.fixture
def app():
    flask_app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
    )
    with flask_app.app_context():
        _db.create_all()
        from app import Rol, Territorio, Vendedor
        rol = Rol(nombre='super_admin', descripcion='Admin')
        _db.session.add(rol)
        territorio = Territorio(nombre='test', descripcion='Test')
        _db.session.add(territorio)
        _db.session.flush()
        vendedor = Vendedor(
            username='admin',
            email='admin@test.com',
            nombre_completo='Admin Test',
            rol_id=rol.id,
            territorio_id=territorio.id,
            activo=True,
        )
        vendedor.set_password('testpass')
        _db.session.add(vendedor)
        _db.session.commit()
        yield flask_app
        _db.drop_all()


@pytest.fixture
def logged_client(app):
    client = app.test_client()
    client.post('/login', data={
        'username': 'admin',
        'password': 'testpass',
    }, follow_redirects=True)
    return client


@pytest.fixture
def anon_client(app):
    return app.test_client()


# === AC #5: Página de admin backup ===

def test_backup_page_loads_for_super_admin(logged_client):
    """AC #5: La ruta /admin/backup carga exitosamente para super_admin."""
    resp = logged_client.get('/admin/backup')
    assert resp.status_code == 200


def test_backup_page_shows_configuration_info(logged_client):
    """AC #5: La página muestra información de configuración de backups."""
    resp = logged_client.get('/admin/backup')
    html = resp.data.decode('utf-8')
    assert '02:00' in html
    assert 'backup' in html.lower()


def test_backup_page_shows_status_check_instruction(logged_client):
    """AC #5: La página indica cómo ver fecha y total de backups via CLI."""
    resp = logged_client.get('/admin/backup')
    html = resp.data.decode('utf-8')
    assert 'heroku pg:backups --app pesosapp' in html


def test_backup_page_shows_cli_commands(logged_client):
    """AC #5: La página muestra comandos CLI para gestión de backups."""
    resp = logged_client.get('/admin/backup')
    html = resp.data.decode('utf-8')
    assert 'pg:backups' in html
    assert 'heroku' in html.lower()


def test_backup_page_shows_restore_instructions(logged_client):
    """AC #5: La página muestra instrucciones de restore."""
    resp = logged_client.get('/admin/backup')
    html = resp.data.decode('utf-8')
    assert 'restore' in html.lower() or 'Restaurar' in html


def test_backup_page_requires_login(anon_client):
    """AC #5: La ruta /admin/backup requiere autenticación."""
    resp = anon_client.get('/admin/backup')
    # Should redirect to login
    assert resp.status_code in (302, 308)


def test_backup_page_requires_super_admin_role(app):
    """AC #5: La ruta /admin/backup requiere rol super_admin."""
    with app.app_context():
        from app import Rol, Territorio, Vendedor
        rol_vendedor = Rol(nombre='vendedor', descripcion='Vendedor')
        _db.session.add(rol_vendedor)
        _db.session.flush()
        territorio = Territorio.query.first()
        vendedor = Vendedor(
            username='vendedor1',
            email='vendedor@test.com',
            nombre_completo='Vendedor Test',
            rol_id=rol_vendedor.id,
            territorio_id=territorio.id,
            activo=True,
        )
        vendedor.set_password('testpass')
        _db.session.add(vendedor)
        _db.session.commit()

    client = app.test_client()
    client.post('/login', data={
        'username': 'vendedor1',
        'password': 'testpass',
    }, follow_redirects=True)
    resp = client.get('/admin/backup')
    # Should either redirect (403 handled as redirect) or return 403
    assert resp.status_code in (302, 403, 308)


# === AC #1, #2, #3, #4: Scripts existen ===

def test_setup_heroku_backups_script_exists():
    """AC #1: El script setup-heroku-backups.sh existe."""
    script_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'scripts', 'setup-heroku-backups.sh'
    )
    assert os.path.isfile(script_path), f"Script no encontrado: {script_path}"


def test_setup_heroku_backups_script_is_executable():
    """AC #1: El script setup-heroku-backups.sh es ejecutable."""
    script_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'scripts', 'setup-heroku-backups.sh'
    )
    assert os.access(script_path, os.X_OK), "Script no es ejecutable"


def test_safe_migrate_script_exists():
    """AC #2: El script safe-migrate.sh existe."""
    script_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'scripts', 'safe-migrate.sh'
    )
    assert os.path.isfile(script_path)


def test_safe_migrate_script_is_executable():
    """AC #2: El script safe-migrate.sh es ejecutable."""
    script_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'scripts', 'safe-migrate.sh'
    )
    assert os.access(script_path, os.X_OK)


def test_backup_export_script_exists():
    """AC #4: El script backup-export.sh existe."""
    script_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'scripts', 'backup-export.sh'
    )
    assert os.path.isfile(script_path)


def test_backup_export_script_is_executable():
    """AC #4: El script backup-export.sh es ejecutable."""
    script_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'scripts', 'backup-export.sh'
    )
    assert os.access(script_path, os.X_OK)


# === AC #3: Documentación de restore ===

def test_backup_restore_documentation_exists():
    """AC #3: El archivo docs/backup-restore.md existe."""
    doc_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'docs', 'backup-restore.md'
    )
    assert os.path.isfile(doc_path)


def test_backup_restore_doc_has_restore_procedure():
    """AC #3: La documentación contiene procedimiento de restore."""
    doc_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'docs', 'backup-restore.md'
    )
    with open(doc_path, 'r') as f:
        content = f.read()
    assert 'restore' in content.lower()
    assert 'pg:backups:restore' in content


def test_backup_restore_doc_has_verification_steps():
    """AC #3: La documentación contiene pasos de verificación post-restore."""
    doc_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'docs', 'backup-restore.md'
    )
    with open(doc_path, 'r') as f:
        content = f.read()
    assert 'verificacion' in content.lower() or 'Verificacion' in content


# === AC #6: Variables de entorno documentadas ===

def test_env_example_has_backup_vars():
    """AC #6: .env.example contiene variables de backup."""
    env_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        '.env.example'
    )
    with open(env_path, 'r') as f:
        content = f.read()
    assert 'HEROKU_APP_NAME' in content
    assert 'BACKUP_DIR' in content


# === AC #7: Sin regresiones (app sigue funcionando) ===

def test_app_still_loads_dashboard(logged_client):
    """AC #7: El dashboard sigue funcionando normalmente."""
    resp = logged_client.get('/dashboard')
    assert resp.status_code == 200


def test_app_still_loads_login_page(anon_client):
    """AC #7: La página de login sigue funcionando normalmente."""
    resp = anon_client.get('/login')
    assert resp.status_code == 200


# === Script content validation ===

def test_safe_migrate_script_has_backup_before_migrate():
    """AC #2: safe-migrate.sh ejecuta backup antes de migración."""
    script_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'scripts', 'safe-migrate.sh'
    )
    with open(script_path, 'r') as f:
        content = f.read()
    # El script debe contener el comando de backup de heroku
    assert 'pg:backups:capture' in content
    # Y el comando de migración
    assert 'flask db upgrade' in content


def test_safe_migrate_script_exits_on_backup_failure():
    """AC #2: safe-migrate.sh falla si el backup falla."""
    script_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'scripts', 'safe-migrate.sh'
    )
    with open(script_path, 'r') as f:
        content = f.read()
    assert 'exit 1' in content
    assert 'set -euo pipefail' in content


def test_safe_migrate_script_has_local_option():
    """AC #2: safe-migrate.sh soporta opción --local."""
    script_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'scripts', 'safe-migrate.sh'
    )
    with open(script_path, 'r') as f:
        content = f.read()
    assert '--local' in content
    assert 'pg_dump' in content


def test_setup_heroku_script_schedules_daily_backup():
    """AC #1: setup-heroku-backups.sh programa backup diario."""
    script_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'scripts', 'setup-heroku-backups.sh'
    )
    with open(script_path, 'r') as f:
        content = f.read()
    assert 'pg:backups:schedule' in content
    assert 'America/Curacao' in content


def test_gitignore_excludes_backups_dir():
    """Backups directory is excluded from git."""
    gitignore_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        '.gitignore'
    )
    with open(gitignore_path, 'r') as f:
        content = f.read()
    assert 'backups/' in content


def test_backup_export_script_has_force_flag():
    """M2 fix: backup-export.sh soporta --force para uso no-interactivo."""
    script_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'scripts', 'backup-export.sh'
    )
    with open(script_path, 'r') as f:
        content = f.read()
    assert '--force' in content
