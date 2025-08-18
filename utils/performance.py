"""
Utilidades de performance y monitoreo
"""
import time
import functools
import logging
from typing import Callable, Dict, List
from datetime import datetime
from flask import request, g, current_app

class PerformanceMonitor:
    """Monitor de rendimiento para la aplicación"""
    
    def __init__(self):
        self.metrics = {}
        self.slow_queries = []
        self.request_times = []
    
    def record_query_time(self, query: str, duration: float):
        """Registrar tiempo de consulta SQL"""
        if duration > 0.1:  # Consultas lentas > 100ms
            self.slow_queries.append({
                'query': query[:200],  # Primeros 200 caracteres
                'duration': duration,
                'timestamp': datetime.now()
            })
            
            # Mantener solo las últimas 100 consultas lentas
            if len(self.slow_queries) > 100:
                self.slow_queries = self.slow_queries[-100:]
    
    def record_request_time(self, endpoint: str, duration: float):
        """Registrar tiempo de request"""
        self.request_times.append({
            'endpoint': endpoint,
            'duration': duration,
            'timestamp': datetime.now()
        })
        
        # Mantener solo los últimos 1000 requests
        if len(self.request_times) > 1000:
            self.request_times = self.request_times[-1000:]
    
    def get_stats(self) -> Dict:
        """Obtener estadísticas de rendimiento"""
        if not self.request_times:
            return {}
        
        durations = [r['duration'] for r in self.request_times[-100:]]
        
        return {
            'avg_request_time': sum(durations) / len(durations),
            'max_request_time': max(durations),
            'min_request_time': min(durations),
            'slow_queries_count': len(self.slow_queries),
            'total_requests': len(self.request_times)
        }

# Instancia global del monitor
monitor = PerformanceMonitor()

def timer(func: Callable) -> Callable:
    """Decorador para medir tiempo de ejecución"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            return result
        finally:
            duration = time.time() - start_time
            current_app.logger.debug(f"⏱️  {func.__name__}: {duration:.3f}s")
            
            # Registrar en monitor si está disponible
            if hasattr(g, 'performance_monitor'):
                g.performance_monitor.record_query_time(func.__name__, duration)
    
    return wrapper

def profile_request(func: Callable) -> Callable:
    """Decorador para perfilar requests completos"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        endpoint = request.endpoint or 'unknown'
        
        try:
            result = func(*args, **kwargs)
            return result
        finally:
            duration = time.time() - start_time
            monitor.record_request_time(endpoint, duration)
            
            if duration > 1.0:  # Requests lentos > 1s
                current_app.logger.warning(
                    f"🐌 Slow request: {endpoint} took {duration:.3f}s"
                )
    
    return wrapper

class QueryCounter:
    """Contador de consultas SQL para debugging"""
    
    def __init__(self):
        self.count = 0
        self.queries = []
    
    def __enter__(self):
        self.count = 0
        self.queries = []
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.count > 10:
            current_app.logger.warning(
                f"🚨 High query count: {self.count} queries detected"
            )

def optimize_query_n_plus_one(func: Callable) -> Callable:
    """Decorador para detectar problemas N+1 en consultas"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with QueryCounter() as counter:
            result = func(*args, **kwargs)
            
            if counter.count > 5:
                current_app.logger.warning(
                    f"⚠️  Possible N+1 query in {func.__name__}: {counter.count} queries"
                )
            
            return result
    
    return wrapper

def benchmark(iterations: int = 1):
    """Decorador para hacer benchmark de funciones"""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            times = []
            result = None
            
            for i in range(iterations):
                start_time = time.time()
                result = func(*args, **kwargs)
                times.append(time.time() - start_time)
            
            avg_time = sum(times) / len(times)
            current_app.logger.info(
                f"📊 Benchmark {func.__name__}: "
                f"avg={avg_time:.3f}s over {iterations} iterations"
            )
            
            return result
        
        return wrapper
    return decorator

# Middleware para medir performance de requests
def init_performance_monitoring(app):
    """Inicializar monitoreo de performance"""
    
    @app.before_request
    def before_request():
        g.start_time = time.time()
        g.performance_monitor = monitor
    
    @app.after_request
    def after_request(response):
        if hasattr(g, 'start_time'):
            duration = time.time() - g.start_time
            endpoint = request.endpoint or 'unknown'
            
            # Headers de timing para debugging
            response.headers['X-Response-Time'] = f"{duration:.3f}"
            
            # Log requests lentos
            if duration > 2.0:
                current_app.logger.warning(
                    f"🚨 Very slow request: {endpoint} - {duration:.3f}s"
                )
            elif duration > 1.0:
                current_app.logger.info(
                    f"🐌 Slow request: {endpoint} - {duration:.3f}s"
                )
        
        return response

# Utilidades para optimización de consultas
def batch_loader(model_class, ids: List[int], batch_size: int = 100):
    """Cargar modelos en lotes para evitar N+1 queries"""
    results = {}
    
    for i in range(0, len(ids), batch_size):
        batch_ids = ids[i:i + batch_size]
        batch_results = model_class.query.filter(model_class.id.in_(batch_ids)).all()
        
        for item in batch_results:
            results[item.id] = item
    
    return results

def preload_relationships(query, *relationships):
    """Precargar relaciones para evitar lazy loading"""
    from sqlalchemy.orm import joinedload
    
    for relationship in relationships:
        query = query.options(joinedload(relationship))
    
    return query