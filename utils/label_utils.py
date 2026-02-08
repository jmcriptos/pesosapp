"""
Utilidades para generación de etiquetas PDF.
Centraliza el código común para etiquetas de pedidos y etiquetas de vencimiento.
"""
import os
from io import BytesIO
from reportlab.lib.units import inch
from reportlab.lib.pagesizes import letter, A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics


# =============================================================================
# CONSTANTES DE DISEÑO DE ETIQUETAS
# =============================================================================

# Dimensiones estándar de etiqueta 4" x 2"
LABEL_WIDTH = 4 * inch
LABEL_HEIGHT = 2 * inch

# Margen interno
MARGIN = 8

# Dimensiones del logo
LOGO_X = MARGIN
LOGO_WIDTH = 1.20 * inch
LOGO_HEIGHT = 1.20 * inch

# Columna derecha (labels y valores)
LABEL_X_RIGHT = 2.80 * inch
VALUE_X = LABEL_X_RIGHT + 0.12 * inch

# Posiciones Y para etiquetas con cliente (pedidos)
Y_CLIENT = LABEL_HEIGHT - MARGIN - 0.22 * inch
Y_LOT = Y_CLIENT - 0.18 * inch
Y_MFG = Y_LOT - 0.18 * inch
Y_EXP = Y_MFG - 0.18 * inch
Y_KEEP = Y_EXP - 0.18 * inch

# Net Weight
Y_NET_WEIGHT = MARGIN + 0.46 * inch

# Separador
SEPARATOR_Y = MARGIN + 0.33 * inch

# Área del producto (etiquetas de pedido)
PRODUCT_Y_MIN = MARGIN + 0.06 * inch
PRODUCT_Y_MAX = MARGIN + 0.26 * inch

# Posiciones Y para etiquetas de vencimiento (sin cliente)
Y_LOT_VENC = LABEL_HEIGHT - 0.12 * inch
Y_MFG_VENC = Y_LOT_VENC - 0.18 * inch
Y_EXP_VENC = Y_MFG_VENC - 0.18 * inch
Y_KEEP_VENC = Y_EXP_VENC - 0.18 * inch

# Separador para vencimiento
SEPARATOR_Y_VENC = MARGIN + 0.55 * inch

# Área del producto (etiquetas de vencimiento - más grande)
PRODUCT_Y_MIN_VENC = MARGIN + 0.15 * inch
PRODUCT_Y_MAX_VENC = MARGIN + 0.50 * inch


# =============================================================================
# FUNCIONES DE UTILIDAD
# =============================================================================

def draw_center_wrap_text(canvas_obj, text, center_x, y_bottom, y_top, max_width,
                          font_name="Helvetica-Bold", max_font=19.2, min_font=12, line_gap=2):
    """
    Dibuja texto centrado, 1-2 líneas, con auto-escalado para caber en ancho y alto.

    Args:
        canvas_obj: Objeto canvas de ReportLab
        text: Texto a dibujar
        center_x: Posición X central
        y_bottom: Límite inferior Y
        y_top: Límite superior Y
        max_width: Ancho máximo disponible
        font_name: Nombre de la fuente
        max_font: Tamaño máximo de fuente
        min_font: Tamaño mínimo de fuente
        line_gap: Espacio entre líneas
    """
    txt = (text or "").strip()
    if not txt:
        return

    def wrap_two_lines(s, font_size):
        """Intenta dividir el texto en 1-2 líneas equilibradas."""
        # Intenta con 1 línea
        if pdfmetrics.stringWidth(s, font_name, font_size) <= max_width:
            return [s]

        # Intenta con 2 líneas (corte equilibrado por ancho)
        words = s.split()
        best = None
        for i in range(1, len(words)):
            line1 = " ".join(words[:i])
            line2 = " ".join(words[i:])
            width1 = pdfmetrics.stringWidth(line1, font_name, font_size)
            width2 = pdfmetrics.stringWidth(line2, font_name, font_size)
            if width1 <= max_width and width2 <= max_width:
                diff = abs(width1 - width2)
                if best is None or diff < best[0]:
                    best = (diff, [line1, line2])
        if best:
            return best[1]
        return None

    avail_h = y_top - y_bottom
    font = max_font

    while font >= min_font:
        lines = wrap_two_lines(txt, font)
        if lines is None:
            font -= 0.5
            continue

        line_h = font
        total_h = line_h * len(lines) + (len(lines) - 1) * line_gap

        if total_h <= avail_h:
            # Centrado vertical
            top_y = y_bottom + (avail_h + total_h) / 2
            canvas_obj.setFont(font_name, font)

            if len(lines) == 1:
                canvas_obj.drawCentredString(center_x, top_y - line_h + 1, lines[0])
            else:
                canvas_obj.drawCentredString(center_x, top_y - line_h + 1, lines[0])
                canvas_obj.drawCentredString(center_x, top_y - 2*line_h - line_gap + 1, lines[1])
            return
        font -= 0.5

    # Fallback: una línea con elipsis
    font = min_font
    s = txt
    ellipsis = "…"
    while pdfmetrics.stringWidth(s + ellipsis, font_name, font) > max_width and len(s) > 1:
        s = s[:-1]
    y = y_bottom + (avail_h - font) / 2
    canvas_obj.setFont(font_name, font)
    canvas_obj.drawCentredString(center_x, y, s + ellipsis)


def normalize_temperature(temp):
    """Normaliza el formato de temperatura (°C)."""
    if isinstance(temp, str):
        return temp.replace(" oC", " °C").replace("° C", "°C")
    return temp or ""


def get_logo_path(basedir):
    """Obtiene la ruta del logo de etiquetas."""
    return os.path.join(basedir, 'static', 'logo_etiquetas.png')


def draw_logo(canvas_obj, logo_path, x_base=0, y_base=0, use_margin=True):
    """
    Dibuja el logo en la etiqueta si existe.

    Args:
        canvas_obj: Objeto canvas de ReportLab
        logo_path: Ruta al archivo de logo
        x_base: Posición X base (para etiquetas en página letter)
        y_base: Posición Y base (para etiquetas en página letter)
        use_margin: Si incluir margen superior (True para pedidos, False para vencimiento)
    """
    if os.path.exists(logo_path):
        logo_y = LABEL_HEIGHT - MARGIN - LOGO_HEIGHT if use_margin else LABEL_HEIGHT - LOGO_HEIGHT
        canvas_obj.drawImage(
            logo_path,
            x_base + LOGO_X,
            y_base + logo_y,
            width=LOGO_WIDTH,
            height=LOGO_HEIGHT,
            preserveAspectRatio=True,
            mask='auto'
        )


def draw_separator(canvas_obj, x_base, y_base, separator_y):
    """Dibuja la línea separadora punteada."""
    canvas_obj.setLineWidth(0.5)
    canvas_obj.setDash(1, 2)
    canvas_obj.line(
        x_base + MARGIN,
        y_base + separator_y,
        x_base + LABEL_WIDTH - MARGIN,
        y_base + separator_y
    )
    canvas_obj.setDash()


def draw_order_label(canvas_obj, logo_path, client, product, temperature, lot,
                     mfg_date, exp_date, weight, x_base=0, y_base=0):
    """
    Dibuja una etiqueta completa de pedido (con cliente y peso).

    Args:
        canvas_obj: Objeto canvas de ReportLab
        logo_path: Ruta al logo
        client: Nombre del cliente
        product: Nombre del producto
        temperature: Temperatura de conservación
        lot: Número de lote
        mfg_date: Fecha de fabricación
        exp_date: Fecha de expiración
        weight: Peso neto
        x_base: Posición X base
        y_base: Posición Y base
    """
    # Logo
    draw_logo(canvas_obj, logo_path, x_base, y_base, use_margin=True)

    # Labels (derecha)
    canvas_obj.setFont("Helvetica-Bold", 9.5)
    canvas_obj.drawRightString(x_base + LABEL_X_RIGHT, y_base + Y_CLIENT, "Client:")
    canvas_obj.drawRightString(x_base + LABEL_X_RIGHT, y_base + Y_LOT, "Lot:")
    canvas_obj.drawRightString(x_base + LABEL_X_RIGHT, y_base + Y_MFG, "Manufactured:")
    canvas_obj.drawRightString(x_base + LABEL_X_RIGHT, y_base + Y_EXP, "Expiration:")
    canvas_obj.drawRightString(x_base + LABEL_X_RIGHT, y_base + Y_KEEP, "When Kept at:")

    # Valores
    canvas_obj.setFont("Helvetica", 9.5)
    canvas_obj.drawString(x_base + VALUE_X, y_base + Y_CLIENT, client or "")
    canvas_obj.drawString(x_base + VALUE_X, y_base + Y_LOT, lot or "")
    canvas_obj.drawString(x_base + VALUE_X, y_base + Y_MFG, mfg_date or "")
    canvas_obj.drawString(x_base + VALUE_X, y_base + Y_EXP, exp_date or "")
    canvas_obj.drawString(x_base + VALUE_X, y_base + Y_KEEP, normalize_temperature(temperature))

    # Net Weight
    canvas_obj.setFont("Helvetica-Bold", 15.6)
    canvas_obj.drawRightString(x_base + LABEL_X_RIGHT, y_base + Y_NET_WEIGHT, "Net Weight:")
    canvas_obj.setFont("Helvetica-Bold", 16.8)
    canvas_obj.drawString(x_base + VALUE_X, y_base + Y_NET_WEIGHT, str(weight))

    # Separador
    draw_separator(canvas_obj, x_base, y_base, SEPARATOR_Y)

    # Producto
    max_text_width = LABEL_WIDTH - (2 * MARGIN)
    draw_center_wrap_text(
        canvas_obj,
        product or "N/A",
        center_x=x_base + LABEL_WIDTH / 2,
        y_bottom=y_base + PRODUCT_Y_MIN,
        y_top=y_base + PRODUCT_Y_MAX,
        max_width=max_text_width,
        max_font=19.2,
        min_font=12
    )


def draw_expiration_label(canvas_obj, logo_path, datos, x_base=0, y_base=0):
    """
    Dibuja una etiqueta de vencimiento (sin cliente ni peso).

    Args:
        canvas_obj: Objeto canvas de ReportLab
        logo_path: Ruta al logo
        datos: Diccionario con datos del producto (nombre_producto, lote, fecha_fabricacion, fecha_expiracion, temperatura)
        x_base: Posición X base
        y_base: Posición Y base
    """
    # Logo (sin margen superior)
    draw_logo(canvas_obj, logo_path, x_base, y_base, use_margin=False)

    # Labels (sin Client)
    canvas_obj.setFont("Helvetica-Bold", 9.5)
    canvas_obj.drawRightString(x_base + LABEL_X_RIGHT, y_base + Y_LOT_VENC, "Lot:")
    canvas_obj.drawRightString(x_base + LABEL_X_RIGHT, y_base + Y_MFG_VENC, "Manufactured:")
    canvas_obj.drawRightString(x_base + LABEL_X_RIGHT, y_base + Y_EXP_VENC, "Expiration:")
    canvas_obj.drawRightString(x_base + LABEL_X_RIGHT, y_base + Y_KEEP_VENC, "When Kept at:")

    # Valores
    canvas_obj.setFont("Helvetica", 9.5)
    canvas_obj.drawString(x_base + VALUE_X, y_base + Y_LOT_VENC, datos.get('lote', '') or "")
    canvas_obj.drawString(x_base + VALUE_X, y_base + Y_MFG_VENC, datos.get('fecha_fabricacion', '') or "")
    canvas_obj.drawString(x_base + VALUE_X, y_base + Y_EXP_VENC, datos.get('fecha_expiracion', '') or "")
    canvas_obj.drawString(x_base + VALUE_X, y_base + Y_KEEP_VENC, normalize_temperature(datos.get('temperatura', '')))

    # Separador
    draw_separator(canvas_obj, x_base, y_base, SEPARATOR_Y_VENC)

    # Producto (fuente más grande para vencimiento)
    max_text_width = LABEL_WIDTH - (2 * MARGIN)
    draw_center_wrap_text(
        canvas_obj,
        datos.get('nombre_producto', 'N/A'),
        center_x=x_base + LABEL_WIDTH / 2,
        y_bottom=y_base + PRODUCT_Y_MIN_VENC,
        y_top=y_base + PRODUCT_Y_MAX_VENC,
        max_width=max_text_width,
        font_name="Helvetica-Bold",
        max_font=24,
        min_font=16,
        line_gap=2
    )


def create_single_label_pdf():
    """
    Crea un PDF con tamaño de página 4x2 (una etiqueta por página).

    Returns:
        tuple: (BytesIO output, canvas object)
    """
    output = BytesIO()
    c = canvas.Canvas(output, pagesize=(LABEL_WIDTH, LABEL_HEIGHT))
    return output, c


def create_letter_page_pdf():
    """
    Crea un PDF con tamaño carta para múltiples etiquetas.

    Returns:
        tuple: (BytesIO output, canvas object, page_width, page_height)
    """
    output = BytesIO()
    c = canvas.Canvas(output, pagesize=letter)
    c.setPageCompression(1)
    return output, c, letter[0], letter[1]


def get_centered_x(page_width):
    """Calcula la posición X centrada para una etiqueta en página letter."""
    return (page_width - LABEL_WIDTH) / 2


# =============================================================================
# FORMATO A4 (2 etiquetas por página)
# =============================================================================

# Tamaño de etiqueta para A4 (100.16mm x 50.8mm)
A4_LABEL_WIDTH = 100.16 / 25.4 * inch
A4_LABEL_HEIGHT = 50.8 / 25.4 * inch


def create_a4_page_pdf():
    """
    Crea un PDF con tamaño A4 para etiquetas (2 por página).

    Returns:
        tuple: (BytesIO output, canvas object, page_width, page_height)
    """
    output = BytesIO()
    c = canvas.Canvas(output, pagesize=A4)
    c.setPageCompression(1)
    return output, c, A4[0], A4[1]


def get_a4_label_positions(page_width, page_height):
    """
    Calcula las posiciones Y para 2 etiquetas centradas en A4.

    Returns:
        tuple: (x_offset, y_top, y_bottom)
    """
    x_offset = (page_width - A4_LABEL_WIDTH) / 2
    # Etiqueta superior: empieza justo arriba de la página (sin margen)
    y_top = page_height - A4_LABEL_HEIGHT
    # Etiqueta inferior: debajo de la superior con pequeño espacio
    y_bottom = y_top - A4_LABEL_HEIGHT - 0.2 * inch
    return x_offset, y_top, y_bottom


def draw_order_label_a4(canvas_obj, logo_path, client, product, temperature, lot,
                        mfg_date, exp_date, weight, x_offset, y_offset):
    """
    Dibuja una etiqueta de pedido en formato A4.
    Usa las mismas posiciones Y que las etiquetas de vencimiento (Y_LOT_VENC style).
    """
    # Posiciones Y igual que etiquetas de vencimiento (sin margen superior)
    # Y_LOT_VENC = LABEL_HEIGHT - 0.12 * inch = 1.88 inch desde abajo
    y_client = y_offset + A4_LABEL_HEIGHT - 0.12 * inch   # 1.88 inch (como Y_LOT_VENC)
    y_lot = y_client - 0.18 * inch                         # 1.70 inch
    y_mfg = y_lot - 0.18 * inch                            # 1.52 inch
    y_exp = y_mfg - 0.18 * inch                            # 1.34 inch
    y_keep = y_exp - 0.18 * inch                           # 1.16 inch

    # Logo (sin margen superior, igual que etiquetas vencimiento)
    logo_y = y_offset + A4_LABEL_HEIGHT - LOGO_HEIGHT
    if os.path.exists(logo_path):
        canvas_obj.drawImage(logo_path, x_offset + LOGO_X, logo_y,
                             width=LOGO_WIDTH, height=LOGO_HEIGHT,
                             preserveAspectRatio=True, mask='auto')

    # Labels y valores (usando las constantes compartidas)
    canvas_obj.setFont("Helvetica-Bold", 9.5)
    canvas_obj.drawRightString(x_offset + LABEL_X_RIGHT, y_client, "Client:")
    canvas_obj.drawRightString(x_offset + LABEL_X_RIGHT, y_lot, "Lot:")
    canvas_obj.drawRightString(x_offset + LABEL_X_RIGHT, y_mfg, "Manufactured:")
    canvas_obj.drawRightString(x_offset + LABEL_X_RIGHT, y_exp, "Expiration:")
    canvas_obj.drawRightString(x_offset + LABEL_X_RIGHT, y_keep, "When Kept at:")

    canvas_obj.setFont("Helvetica", 9.5)
    canvas_obj.drawString(x_offset + VALUE_X, y_client, client or "")
    canvas_obj.drawString(x_offset + VALUE_X, y_lot, lot or "")
    canvas_obj.drawString(x_offset + VALUE_X, y_mfg, mfg_date or "")
    canvas_obj.drawString(x_offset + VALUE_X, y_exp, exp_date or "")
    canvas_obj.drawString(x_offset + VALUE_X, y_keep, normalize_temperature(temperature))

    # Net Weight
    y_net_weight = y_offset + MARGIN + 0.46 * inch
    canvas_obj.setFont("Helvetica-Bold", 15.6)
    canvas_obj.drawRightString(x_offset + LABEL_X_RIGHT, y_net_weight, "Net Weight:")
    canvas_obj.setFont("Helvetica-Bold", 16.8)
    canvas_obj.drawString(x_offset + VALUE_X, y_net_weight, str(weight))

    # Separador
    draw_separator(canvas_obj, x_offset, y_offset, SEPARATOR_Y)

    # Producto (centrado abajo)
    max_text_width = A4_LABEL_WIDTH - (2 * MARGIN)
    draw_center_wrap_text(
        canvas_obj,
        product or "N/A",
        center_x=x_offset + A4_LABEL_WIDTH / 2,
        y_bottom=y_offset + PRODUCT_Y_MIN,
        y_top=y_offset + PRODUCT_Y_MAX,
        max_width=max_text_width,
        max_font=19.2,
        min_font=12
    )
