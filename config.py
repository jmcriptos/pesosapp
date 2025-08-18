import os
from datetime import timedelta

class Config:
    """Configuración base de Flask optimizada"""
    
    # Configuración básica
    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-unsafe-change-me"
    
    # Base de datos
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///local.db")
    if SQLALCHEMY_DATABASE_URI.startswith("postgres://"):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace("postgres://", "postgresql://", 1)
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 3600
    }
    
    # Optimizaciones de sesión
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = True  # En producción
    REMEMBER_COOKIE_SECURE = True
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = 'Lax'
    REMEMBER_COOKIE_DURATION = timedelta(days=7)
    
    # Optimizaciones de rendimiento
    SEND_FILE_MAX_AGE_DEFAULT = timedelta(hours=12)  # Cache de archivos estáticos
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)  # Sesiones de 8 horas
    
    # Compresión y caching
    COMPRESS_MIMETYPES = [
        'text/html', 'text/css', 'text/xml', 'application/json',
        'application/javascript', 'text/javascript'
    ]
    COMPRESS_LEVEL = 6
    COMPRESS_MIN_SIZE = 500
    
    # Límites de seguridad
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB máximo para uploads
    
    # Logging
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    
    # CSRF
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600  # 1 hora
    
    # Cache Redis (si está disponible)
    CACHE_TYPE = "simple"  # Fallback a memoria
    CACHE_DEFAULT_TIMEOUT = 300  # 5 minutos
    
    # Talisman CSP
    TALISMAN_CSP = {
        'default-src': ["'self'"],
        'script-src': [
            "'self'",
            'https://cdn.jsdelivr.net',
            'https://code.jquery.com',
            'https://cdnjs.cloudflare.com'
        ],
        'style-src': [
            "'self'",
            'https://cdn.jsdelivr.net',
            'https://cdnjs.cloudflare.com'
        ],
        'img-src': ["'self'", 'data:'],
        'font-src': ["'self'", 'https://cdnjs.cloudflare.com'],
        'connect-src': ["'self'"],
    }

class DevelopmentConfig(Config):
    """Configuración para desarrollo"""
    DEBUG = True
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_SECURE = False
    SQLALCHEMY_ECHO = False  # Cambiar a True para debug SQL
    LOG_LEVEL = 'DEBUG'

class ProductionConfig(Config):
    """Configuración para producción"""
    DEBUG = False
    TESTING = False
    
    # Configuraciones de seguridad mejoradas
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SECURE = True
    
    # Optimizaciones adicionales para producción
    SQLALCHEMY_ENGINE_OPTIONS = {
        **Config.SQLALCHEMY_ENGINE_OPTIONS,
        'pool_size': 20,
        'pool_recycle': 1800,
        'pool_timeout': 30,
        'max_overflow': 20
    }
    
    # Cache Redis en producción
    REDIS_URL = os.environ.get('REDIS_URL')
    if REDIS_URL:
        CACHE_TYPE = "redis"
        CACHE_REDIS_URL = REDIS_URL
        CACHE_DEFAULT_TIMEOUT = 900  # 15 minutos en producción

class TestingConfig(Config):
    """Configuración para testing"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_SECURE = False

# Mapa de configuraciones
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}