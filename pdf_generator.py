# pdf_generator.py
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.graphics.barcode import code128

def construir_pdf_pases(lista_pases):
    """Genera un PDF tamaño Carta con cuadrícula compacta (2 columnas x 4 filas = 8 pases)."""
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    page_w, page_h = letter  # 612 x 792 pt

    cols = 2
    rows = 4
    pases_por_pagina = cols * rows

    margin_x = 24
    margin_y = 25
    spacing_x = 12
    spacing_y = 10

    card_w = (page_w - (2 * margin_x) - ((cols - 1) * spacing_x)) / cols
    card_h = (page_h - (2 * margin_y) - ((rows - 1) * spacing_y)) / rows

    for idx, item in enumerate(lista_pases):
        id_pase, etiqueta, fecha_exp, autorizo, tipo_pase = item

        pos_in_page = idx % pases_por_pagina
        col_idx = pos_in_page % cols
        row_idx = pos_in_page // cols

        x = margin_x + col_idx * (card_w + spacing_x)
        y = page_h - margin_y - ((row_idx + 1) * card_h) - (row_idx * spacing_y)

        # 1. Borde exterior
        p.setStrokeColor(colors.HexColor("#CBD5E1"))
        p.setFillColor(colors.HexColor("#FFFFFF"))
        p.setLineWidth(1)
        p.roundRect(x, y, card_w, card_h, 6, fill=1, stroke=1)

        # 2. Encabezado Azul
        p.setFillColor(colors.HexColor("#1E3A8A"))
        p.roundRect(x, y + card_h - 22, card_w, 22, 6, fill=1, stroke=0)
        p.rect(x, y + card_h - 22, card_w, 6, fill=1, stroke=0)

        # Textos de Encabezado
        p.setFillColor(colors.white)
        p.setFont("Helvetica-Bold", 8.5)
        p.drawString(x + 8, y + card_h - 15, "PASE DE COMEDOR")
        
        p.setFont("Helvetica-Bold", 7.5)
        p.drawRightString(x + card_w - 8, y + card_h - 15, str(tipo_pase).upper())

        # 3. Vigencia y Autorización
        p.setFillColor(colors.HexColor("#475569"))
        p.setFont("Helvetica", 7)
        autorizo_limpio = autorizo.split('[')[0].strip()
        p.drawString(x + 10, y + card_h - 35, f"Válido hasta: {fecha_exp}  |  Autoriza: {autorizo_limpio[:16]}")

        # 4. Líneas para llenar a mano
        p.setFillColor(colors.HexColor("#1E293B"))
        p.setFont("Helvetica-Bold", 7.5)
        p.setStrokeColor(colors.HexColor("#94A3B8"))
        p.setLineWidth(0.75)
        
        p.drawString(x + 10, y + card_h - 50, "Nombre:")
        p.line(x + 48, y + card_h - 51, x + card_w - 10, y + card_h - 51)

        p.drawString(x + 10, y + card_h - 66, "Firma:")
        p.line(x + 48, y + card_h - 67, x + card_w - 10, y + card_h - 67)

        # 5. Código de barras Code128
        try:
            barcode_obj = code128.Code128(id_pase, barHeight=28, barWidth=1.0, humanReadable=True)
            bc_x = x + (card_w - barcode_obj.width) / 2
            barcode_obj.drawOn(p, bc_x, y + 16)
        except Exception:
            p.setFont("Helvetica-Bold", 9)
            p.drawCentredString(x + card_w / 2, y + 22, id_pase)

        # 6. Pie de página
        p.setFont("Helvetica-Oblique", 6)
        p.setFillColor(colors.HexColor("#94A3B8"))
        p.drawCentredString(x + card_w / 2, y + 5, "Válido por 1 comida • Se anula automáticamente tras escanear")

        if (idx + 1) % pases_por_pagina == 0 and (idx + 1) < len(lista_pases):
            p.showPage()

    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer