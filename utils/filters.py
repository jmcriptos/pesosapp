# utils/filters.py
def kpi_tag(valor):
    """
    Devuelve (texto, clase_css) según el valor del KPI.
    Ajusta los umbrales a tu gusto.
    """
    if valor >= 95:
        return "Excelente", "badge-success"
    elif valor >= 90:
        return "Bueno", "badge-primary"
    elif valor >= 80:
        return "Regular", "badge-warning"
    else:
        return "Crítico", "badge-danger"
