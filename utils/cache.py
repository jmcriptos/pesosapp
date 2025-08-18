"""
Sistema de cache optimizado para PesosApp
"""
import functools
import pickle
import time
from typing import Any, Callable, Optional
from datetime import datetime, timedelta
import hashlib

class SimpleCache:
    """Cache simple en memoria para desarrollo"""
    
    def __init__(self, default_timeout=300):
        self._cache = {}
        self.default_timeout = default_timeout
    
    def get(self, key: str) -> Any:
        """Obtener valor del cache"""
        if key in self._cache:
            value, expiry = self._cache[key]
            if expiry > time.time():
                return value
            else:
                del self._cache[key]
        return None
    
    def set(self, key: str, value: Any, timeout: Optional[int] = None) -> bool:
        """Establecer valor en cache"""
        if timeout is None:
            timeout = self.default_timeout
        
        expiry = time.time() + timeout
        self._cache[key] = (value, expiry)
        return True
    
    def delete(self, key: str) -> bool:
        """Eliminar valor del cache"""
        if key in self._cache:
            del self._cache[key]
            return True
        return False
    
    def clear(self) -> bool:
        """Limpiar todo el cache"""
        self._cache.clear()
        return True
    
    def cleanup(self):
        """Limpiar entradas expiradas"""
        current_time = time.time()
        expired_keys = [
            key for key, (_, expiry) in self._cache.items()
            if expiry <= current_time
        ]
        for key in expired_keys:
            del self._cache[key]

# Instancia global del cache
cache = SimpleCache()

def cached(timeout=300, key_prefix=''):
    """
    Decorador para cachear resultados de funciones
    
    Args:
        timeout: Tiempo de vida del cache en segundos
        key_prefix: Prefijo para la clave del cache
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Generar clave única para los argumentos
            cache_key = _generate_cache_key(func, args, kwargs, key_prefix)
            
            # Intentar obtener del cache
            result = cache.get(cache_key)
            if result is not None:
                return result
            
            # Ejecutar función y cachear resultado
            result = func(*args, **kwargs)
            cache.set(cache_key, result, timeout)
            
            return result
        
        # Agregar método para limpiar cache de esta función
        wrapper.cache_clear = lambda: cache.delete(_generate_cache_key(func, (), {}, key_prefix))
        
        return wrapper
    return decorator

def _generate_cache_key(func: Callable, args: tuple, kwargs: dict, prefix: str = '') -> str:
    """Generar clave única para cache basada en función y argumentos"""
    # Crear string único basado en función y argumentos
    func_name = f"{func.__module__}.{func.__name__}"
    args_str = str(args) + str(sorted(kwargs.items()))
    
    # Hash para mantener clave corta
    hash_obj = hashlib.md5((func_name + args_str).encode())
    hash_hex = hash_obj.hexdigest()
    
    return f"{prefix}:{hash_hex}" if prefix else hash_hex

def cache_dashboard_metrics(user_id: int, timeout: int = 300):
    """Decorador específico para métricas del dashboard"""
    return cached(timeout=timeout, key_prefix=f'dashboard_metrics_{user_id}')

def cache_client_list(vendor_id: int, timeout: int = 600):
    """Decorador específico para lista de clientes"""
    return cached(timeout=timeout, key_prefix=f'client_list_{vendor_id}')

def cache_product_list(timeout: int = 900):
    """Decorador específico para lista de productos"""
    return cached(timeout=timeout, key_prefix='product_list')

def invalidate_user_cache(user_id: int):
    """Invalidar todo el cache relacionado con un usuario"""
    # En una implementación más sofisticada, usaríamos patrones
    # Por ahora, limpiamos claves específicas conocidas
    patterns = [
        f'dashboard_metrics_{user_id}',
        f'client_list_{user_id}'
    ]
    
    for pattern in patterns:
        # Limpiar entradas que contengan el patrón
        keys_to_delete = [
            key for key in cache._cache.keys()
            if pattern in key
        ]
        for key in keys_to_delete:
            cache.delete(key)

def cache_warming():
    """Precalentar cache con datos frecuentemente accedidos"""
    # Esta función se puede llamar al iniciar la aplicación
    # para precargar datos importantes
    pass

# Contexto manager para cache temporal
class temp_cache:
    """Context manager para cache temporal"""
    
    def __init__(self, key: str, value: Any, timeout: int = 60):
        self.key = key
        self.value = value
        self.timeout = timeout
    
    def __enter__(self):
        cache.set(self.key, self.value, self.timeout)
        return self.value
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        cache.delete(self.key)