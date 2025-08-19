#!/usr/bin/env python3
"""
Script de prueba rápida para el dashboard
Útil para depurar problemas antes del despliegue en Heroku
"""

import os
import sys

# Agregar el directorio actual al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from app import app, db, Pedido, Cliente
    from datetime import datetime, timedelta, date
    
    def test_dashboard_basic():
        """Prueba básica de las funciones del dashboard"""
        print("🧪 Iniciando pruebas del dashboard...")
        
        with app.app_context():
            try:
                # Test 1: Verificar conexión a la base de datos
                print("✅ Test 1: Conexión a BD")
                total_pedidos = Pedido.query.count()
                print(f"   Total de pedidos en BD: {total_pedidos}")
                
                # Test 2: Verificar cálculos de fecha
                print("✅ Test 2: Cálculos de fecha")
                hoy = datetime.now().date()
                inicio_mes = hoy.replace(day=1)
                print(f"   Hoy: {hoy}, Inicio mes: {inicio_mes}")
                
                # Test 3: Verificar consultas básicas
                print("✅ Test 3: Consultas básicas")
                pedidos_mes = Pedido.query.filter(Pedido.fecha_pedido >= inicio_mes).count()
                pedidos_pendientes = Pedido.query.filter_by(estado='pendiente').count()
                print(f"   Pedidos este mes: {pedidos_mes}")
                print(f"   Pedidos pendientes: {pedidos_pendientes}")
                
                # Test 4: Verificar cálculo de ventas simple
                print("✅ Test 4: Cálculo de ventas")
                pedidos_muestra = Pedido.query.limit(5).all()
                total_ventas = 0
                for p in pedidos_muestra:
                    for d in p.detalles:
                        if d.subtotal:
                            total_ventas += float(d.subtotal)
                print(f"   Ventas muestra (5 pedidos): {total_ventas}")
                
                print("🎉 Todas las pruebas básicas pasaron!")
                return True
                
            except Exception as e:
                print(f"❌ Error en pruebas: {e}")
                import traceback
                traceback.print_exc()
                return False
    
    def test_dashboard_route():
        """Prueba la ruta del dashboard completa"""
        print("\n🧪 Probando ruta completa del dashboard...")
        
        with app.test_client() as client:
            try:
                # Simular login (necesitarás ajustar esto según tu sistema de auth)
                with client.session_transaction() as sess:
                    sess['user_id'] = 1  # O el ID que uses para auth
                
                response = client.get('/dashboard')
                print(f"   Código de respuesta: {response.status_code}")
                
                if response.status_code == 200:
                    print("✅ Dashboard responde correctamente")
                    return True
                elif response.status_code == 302:
                    print("⚠️  Redirección (probablemente falta autenticación)")
                    return False
                else:
                    print(f"❌ Error en dashboard: {response.status_code}")
                    print(f"   Respuesta: {response.data.decode('utf-8')[:200]}...")
                    return False
                    
            except Exception as e:
                print(f"❌ Error probando ruta: {e}")
                import traceback
                traceback.print_exc()
                return False

    if __name__ == "__main__":
        print("🚀 Iniciando pruebas del dashboard para Heroku...")
        
        # Ejecutar pruebas
        basic_ok = test_dashboard_basic()
        route_ok = test_dashboard_route()
        
        if basic_ok and route_ok:
            print("\n✅ ¡Todas las pruebas pasaron! El dashboard debería funcionar en Heroku.")
            sys.exit(0)
        else:
            print("\n❌ Algunas pruebas fallaron. Revisar errores antes del despliegue.")
            sys.exit(1)

except ImportError as e:
    print(f"❌ Error importando dependencias: {e}")
    print("Asegúrate de que todas las dependencias estén instaladas.")
    sys.exit(1)