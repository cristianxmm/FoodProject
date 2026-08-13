import os
import sqlite3
import threading
import time as time_lib
from datetime import datetime, time as time_obj, timedelta
from functools import wraps
import glob
from io import BytesIO

import pandas as pd
from dotenv import load_dotenv
from evdev import InputDevice, categorize, ecodes
from flask import Flask, render_template, request, redirect, url_for, send_file, session, flash, jsonify, Response

# Librerías para PDF y Código de Barras
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.graphics.barcode import code128

import random
import string
import asyncio
import edge_tts

load_dotenv()

app = Flask(__name__)

# =========================================================
# CONFIGURACIÓN Y AUTENTICACIÓN
# =========================================================
app.secret_key = os.getenv('SECRET_KEY', 'clave_secreta_por_defecto')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=20)

# Configuración de límites de consumos por turno para fijos
LIMITES_POR_TURNO = {
    'EX000001': 6,   # EXTERNOS: Máximo 6 comidas por turno
    'PRV001': 5,     # PROVEEDORES: Máximo 5 comidas por turno
    'VST001': 10     # VISITAS: Máximo 10 comidas por turno
}

# =========================================================
# GESTIÓN DE BASE DE DATOS
# =========================================================
def inicializar_base_datos():
    """Configura el modo WAL y crea las tablas necesarias si no existen."""
    try:
        conexion = sqlite3.connect('comedor.db', timeout=30.0)
        conexion.execute('PRAGMA journal_mode=WAL;')
        conexion.execute('PRAGMA synchronous=NORMAL;')
        
        # Tabla para control de pases temporales de 1 solo uso (sin beneficiario/motivo)
        conexion.execute('''
            CREATE TABLE IF NOT EXISTS PasesTemporales (
                id_pase TEXT PRIMARY KEY,
                fecha_creacion DATETIME NOT NULL,
                fecha_expiracion DATE NOT NULL,
                usado INTEGER DEFAULT 0,
                fecha_consumo DATETIME,
                autorizo TEXT NOT NULL
            )
        ''')
        conexion.commit()
        conexion.close()
        print("[BD] Base de datos y tabla PasesTemporales verificadas.")
    except Exception as e:
        print(f"[BD ERROR] Error al inicializar BD: {e}")

inicializar_base_datos()

def obtener_conexion():
    return sqlite3.connect('comedor.db', timeout=30.0)

ultimo_evento_kiosko = {
    "timestamp": 0,
    "tipo": "",
    "mensaje": "",
    "nombre": "",
    "foto": "/static/fotos/default.jpg"
}

def obtener_ruta_foto(id_employee):
    if not id_employee or str(id_employee).startswith("TMP"):
        return "/static/fotos/default.jpg"

    id_limpio = str(id_employee).strip()
    extensiones = ['.jpg', '.jpeg', '.png', '.webp', '.JPG', '.JPEG', '.PNG', '.WEBP']
    carpeta_fotos = os.path.join(app.static_folder or os.path.join(app.root_path, 'static'), 'fotos')

    for ext in extensiones:
        nombre_archivo = f"{id_limpio}{ext}"
        if os.path.isfile(os.path.join(carpeta_fotos, nombre_archivo)):
            return f"/static/fotos/{nombre_archivo}"

    return "/static/fotos/default.jpg"

KEY_MAP = {
    'KEY_0': '0', 'KEY_1': '1', 'KEY_2': '2', 'KEY_3': '3', 'KEY_4': '4',
    'KEY_5': '5', 'KEY_6': '6', 'KEY_7': '7', 'KEY_8': '8', 'KEY_9': '9',
    'KEY_A': 'A', 'KEY_B': 'B', 'KEY_C': 'C', 'KEY_D': 'D', 'KEY_E': 'E',
    'KEY_F': 'F', 'KEY_G': 'G', 'KEY_H': 'H', 'KEY_I': 'I', 'KEY_J': 'J',
    'KEY_K': 'K', 'KEY_L': 'L', 'KEY_M': 'M', 'KEY_N': 'N', 'KEY_O': 'O',
    'KEY_P': 'P', 'KEY_Q': 'Q', 'KEY_R': 'R', 'KEY_S': 'S', 'KEY_T': 'T',
    'KEY_U': 'U', 'KEY_V': 'V', 'KEY_W': 'W', 'KEY_X': 'X', 'KEY_Y': 'Y',
    'KEY_Z': 'Z', 'KEY_MINUS': '-'
}

def requiere_login(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario_autenticado' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# =========================================================
# FUNCIONES AUXILIARES DE TIEMPO Y CONSUMO
# =========================================================

def obtener_datos_hoy():
    conexion = obtener_conexion()
    try:
        cursor = conexion.cursor()
        fecha_hoy = datetime.now().strftime('%Y-%m-%d')
        cursor.execute("SELECT COUNT(*) FROM Consumos WHERE date(date_hour) = ?", (fecha_hoy,))
        total = cursor.fetchone()[0]
        
        cursor.execute('''
            SELECT time(c.date_hour), e.firstname 
            FROM Consumos c
            JOIN Empleados e ON c.id_employee = e.id_employee
            WHERE date(c.date_hour) = ?
            ORDER BY c.date_hour DESC
        ''', (fecha_hoy,))
        return total, cursor.fetchall()
    finally:
        conexion.close()

def obtener_ventana_turno():
    ahora = datetime.now()
    hora_actual = ahora.time()
    
    if time_obj(6, 0) <= hora_actual < time_obj(14, 0):
        inicio = ahora.replace(hour=6, minute=0, second=0, microsecond=0)
        fin = ahora.replace(hour=13, minute=59, second=59)
        nombre_turno = "Turno 1"
    elif time_obj(14, 0) <= hora_actual < time_obj(22, 0):
        inicio = ahora.replace(hour=14, minute=0, second=0, microsecond=0)
        fin = ahora.replace(hour=21, minute=59, second=59)
        nombre_turno = "Turno 2"
    else:
        nombre_turno = "Turno 3"
        if hora_actual >= time_obj(22, 0):
            inicio = ahora.replace(hour=22, minute=0, second=0, microsecond=0)
            fin = (ahora + timedelta(days=1)).replace(hour=5, minute=59, second=59)
        else:
            inicio = (ahora - timedelta(days=1)).replace(hour=22, minute=0, second=0, microsecond=0)
            fin = ahora.replace(hour=5, minute=59, second=59)
            
    return inicio, fin, nombre_turno

def verificar_limite_superado(cursor, id_employee, inicio_str, fin_str):
    limite_permitido = LIMITES_POR_TURNO.get(id_employee, 1)
    cursor.execute('''
        SELECT COUNT(*) FROM Consumos 
        WHERE id_employee = ? AND date_hour >= ? AND date_hour <= ?
    ''', (id_employee, inicio_str, fin_str))
    consumos_actuales = cursor.fetchone()[0]
    return (consumos_actuales >= limite_permitido), consumos_actuales, limite_permitido

def procesar_pase_temporal(cursor, id_code, fecha_hora_exacta, metodo_origen):
    """Valida y canjea un pase temporal de un solo uso vinculando el nombre con Empleados."""
    cursor.execute('''
        SELECT p.id_pase, IFNULL(e.firstname, 'Visitante'), p.fecha_expiracion, p.usado, p.fecha_consumo 
        FROM PasesTemporales p
        LEFT JOIN Empleados e ON p.id_pase = e.id_employee
        WHERE p.id_pase = ?
    ''', (id_code,))
    pase = cursor.fetchone()
    
    if not pase:
        return False, "no_existe", None

    id_pase, beneficiario, fecha_exp, usado, fecha_consumo = pase
    hoy_str = datetime.now().strftime('%Y-%m-%d')

    if usado == 1:
        hora_uso = fecha_consumo[11:16] if fecha_consumo else ""
        fecha_uso = fecha_consumo[:10] if fecha_consumo else ""
        return True, f"Este pase ya fue utilizado el {fecha_uso} a las {hora_uso}.", beneficiario

    if hoy_str > fecha_exp:
        return True, f"Este pase expiró el {fecha_exp}.", beneficiario

    cursor.execute("UPDATE PasesTemporales SET usado = 1, fecha_consumo = ? WHERE id_pase = ?", (fecha_hora_exacta, id_code))
    cursor.execute("INSERT INTO Consumos (id_employee, date_hour, Metodo) VALUES (?, ?, ?)", 
                   (id_code, fecha_hora_exacta, f"Pase Temporal ({metodo_origen})"))
    
    return True, "OK", beneficiario

# =========================================================
# RUTAS DE LOGIN Y AUTENTICACIÓN
# =========================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        user_input = request.form['username']
        pass_input = request.form['password']
        if user_input == os.getenv('RH_USER') and pass_input == os.getenv('RH_PASS'):
            session.permanent = True 
            session['usuario_autenticado'] = True
            return redirect(url_for('menu_rh'))
        else:
            error = "Credenciales incorrectas. Intenta de nuevo."
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('usuario_autenticado', None)
    flash("Sesión cerrada correctamente.", "info")
    return redirect(url_for('login'))

# =========================================================
# RUTAS DEL KIOSCO
# =========================================================

@app.route('/')
def index():
    total, consumos = obtener_datos_hoy()
    return render_template('index.html', consumos=consumos, total_hoy=total)
@app.route('/kiosk_split')
def kiosk_split():
    return render_template('kiosk_split.html')

@app.route('/escanear', methods=['POST'])
def escanear():
    id_escaneado = request.form['id_employee'].strip().upper()
    metodo_ingreso = request.form.get('metodo_ingreso', 'escaner') 
    ahora = datetime.now()
    fecha_hora_exacta = ahora.strftime('%Y-%m-%d %H:%M:%S')
    
    conexion = obtener_conexion()
    try:
        cursor = conexion.cursor()
        
        # 1. Verificar si es un pase temporal
        es_pase, resultado, nombre_beneficiario = procesar_pase_temporal(cursor, id_escaneado, fecha_hora_exacta, metodo_ingreso)
        if es_pase:
            if resultado == "OK":
                conexion.commit()
                flash(f"¡Éxito! Pase canjeado. Buen provecho, {nombre_beneficiario}.", "success")
            else:
                flash(f"Pase Inválido: {resultado}", "danger")
            return redirect(url_for('index'))

        # 2. Si es un empleado fijo regular
        cursor.execute("SELECT firstname FROM Empleados WHERE id_employee = ?", (id_escaneado,))
        empleado = cursor.fetchone()
        
        if not empleado:
            flash(f"Error: Gafete {id_escaneado} no registrado.", "danger")
            return redirect(url_for('index'))

        nombre = empleado[0]
        inicio_turno, fin_turno, nombre_turno = obtener_ventana_turno()
        inicio_str = inicio_turno.strftime('%Y-%m-%d %H:%M:%S')
        fin_str = fin_turno.strftime('%Y-%m-%d %H:%M:%S')

        limite_excedido, consumos_act, limite_max = verificar_limite_superado(cursor, id_escaneado, inicio_str, fin_str)

        if limite_excedido:
            msg = f"Alerta: {nombre} ya comió en el {nombre_turno}." if limite_max == 1 else f"Alerta: {nombre} alcanzó el límite de {limite_max} consumos en el {nombre_turno}."
            flash(msg, "warning")
            return redirect(url_for('index'))
        
        cursor.execute("INSERT INTO Consumos (id_employee, date_hour, Metodo) VALUES (?, ?, ?)", 
                       (id_escaneado, fecha_hora_exacta, metodo_ingreso))
        conexion.commit()

        if metodo_ingreso == 'manual':
            flash(f"¡Éxito! {nombre} registrado manualmente ({consumos_act + 1}/{limite_max}).", "success")
        else:
            flash(f"¡Éxito! Buen provecho, {nombre} ({consumos_act + 1}/{limite_max}).", "success")
            
        return redirect(url_for('index'))
    finally:
        conexion.close()
async def sintetizar_voz_neural(texto: str, voz: str = "es-MX-DaliaNeural") -> bytes:
    comunicador = edge_tts.Communicate(texto, voz, rate="+0%", pitch="+0Hz")
    buffer = bytearray()
    async for fragmento in comunicador.stream():
        if fragmento["type"] == "audio":
            buffer.extend(fragmento["data"])
    return bytes(buffer)

@app.route('/api/tts')
def api_tts():
    texto = request.args.get('texto', 'Buen provecho')
    try:
        audio_bytes = asyncio.run(sintetizar_voz_neural(texto))
        return Response(audio_bytes, mimetype="audio/mpeg")
    except Exception as e:
        print(f"Error generando TTS neural: {e}")
        return ("Error TTS", 500)
# =========================================================
# RUTAS DE RECURSOS HUMANOS (/rh)
# =========================================================

@app.route('/rh')
@requiere_login
def menu_rh():
    return render_template('rh_menu.html')

# --- SECCIÓN DE PASES TEMPORALES ---
@app.route('/rh/rh_pases')
@app.route('/rh/pases')
@requiere_login
def rh_pases():
    conexion = obtener_conexion()
    try:
        cursor = conexion.cursor()
        cursor.execute('''
            SELECT 
                p.id_pase, 
                IFNULL(e.firstname, 'Visitante') AS beneficiario, 
                p.fecha_creacion, 
                p.fecha_expiracion, 
                p.usado, 
                p.fecha_consumo, 
                p.autorizo
            FROM PasesTemporales p
            LEFT JOIN Empleados e ON p.id_pase = e.id_employee
            ORDER BY p.fecha_creacion DESC LIMIT 50
        ''')
        pases = cursor.fetchall()
        hoy = datetime.now().strftime('%Y-%m-%d')
        return render_template('rh_pases.html', pases=pases, hoy=hoy)
    finally:
        conexion.close()
def generar_id_pase_unico(cursor):
    """Genera un ID único alfanumérico para evitar colisiones en lotes."""
    while True:
        sufijo = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        nuevo_id = f"TMP{sufijo}"
        cursor.execute("SELECT 1 FROM PasesTemporales WHERE id_pase = ?", (nuevo_id,))
        if not cursor.fetchone():
            return nuevo_id
        
# =========================================================
# GENERADOR DE PDF (8 PASES POR HOJA CON LÍNEAS DE FIRMA)
# =========================================================

def construir_pdf_pases(lista_pases):
    """
    Genera un PDF tamaño Carta con cuadrícula compacta (2 columnas x 4 filas = 8 pases).
    lista_pases: lista de tuplas (id_pase, etiqueta, fecha_exp, autorizo, tipo_pase)
    """
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

    card_w = (page_w - (2 * margin_x) - ((cols - 1) * spacing_x)) / cols  # ~276 pt
    card_h = (page_h - (2 * margin_y) - ((rows - 1) * spacing_y)) / rows  # ~178 pt

    for idx, item in enumerate(lista_pases):
        id_pase, etiqueta, fecha_exp, autorizo, tipo_pase = item

        pos_in_page = idx % pases_por_pagina
        col_idx = pos_in_page % cols
        row_idx = pos_in_page // cols

        x = margin_x + col_idx * (card_w + spacing_x)
        y = page_h - margin_y - ((row_idx + 1) * card_h) - (row_idx * spacing_y)

        # 1. Borde exterior de recorte (Gris claro)
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

        # 4. Líneas para llenar a mano (Nombre y Firma)
        p.setFillColor(colors.HexColor("#1E293B"))
        p.setFont("Helvetica-Bold", 7.5)
        p.setStrokeColor(colors.HexColor("#94A3B8"))
        p.setLineWidth(0.75)
        
        # Línea Nombre
        p.drawString(x + 10, y + card_h - 50, "Nombre:")
        p.line(x + 48, y + card_h - 51, x + card_w - 10, y + card_h - 51)

        # Línea Firma
        p.drawString(x + 10, y + card_h - 66, "Firma:")
        p.line(x + 48, y + card_h - 67, x + card_w - 10, y + card_h - 67)

        # 5. Código de barras Code128 legible
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

        # Salto de página cada 8 pases
        if (idx + 1) % pases_por_pagina == 0 and (idx + 1) < len(lista_pases):
            p.showPage()

    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer


# =========================================================
# RUTAS DE GENERACIÓN Y REIMPRESIÓN
# =========================================================

@app.route('/rh/pases/generar', methods=['POST'])
@requiere_login
def generar_pase_rh():
    tipo_pase = request.form.get('tipo_pase', 'Visitante').strip()
    cantidad = int(request.form.get('cantidad', 1))
    dias = int(request.form.get('dias', 1))
    autorizo = request.form.get('autorizo', 'Recursos Humanos').strip()

    cantidad = max(1, min(cantidad, 48))
    
    fecha_exp = (datetime.now() + timedelta(days=dias)).strftime('%Y-%m-%d')
    ahora_dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    lista_generados = []

    conexion = obtener_conexion()
    try:
        cursor = conexion.cursor()
        for i in range(1, cantidad + 1):
            id_pase = generar_id_pase_unico(cursor)
            etiqueta = f"Pase {tipo_pase}" if cantidad == 1 else f"{tipo_pase} #{i}"

            cursor.execute('''
                INSERT INTO PasesTemporales (id_pase, fecha_creacion, fecha_expiracion, usado, autorizo)
                VALUES (?, ?, ?, 0, ?)
            ''', (id_pase, ahora_dt, fecha_exp, f"{autorizo} [{tipo_pase}]"))
            
            cursor.execute("INSERT OR REPLACE INTO Empleados (id_employee, firstname) VALUES (?, ?)", 
                           (id_pase, etiqueta))
            
            lista_generados.append((id_pase, etiqueta, fecha_exp, autorizo, tipo_pase))
            
        conexion.commit()
    finally:
        conexion.close()

    # Llamada correcta con la lista completa
    pdf_buffer = construir_pdf_pases(lista_generados)
    nombre_descarga = f"Pases_{tipo_pase}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
    
    return send_file(
        pdf_buffer, 
        as_attachment=True, 
        download_name=nombre_descarga,
        mimetype='application/pdf'
    )

@app.route('/rh/pases/reimprimir/<id_pase>')
@requiere_login
def reimprimir_pase_rh(id_pase):
    conexion = obtener_conexion()
    try:
        cursor = conexion.cursor()
        cursor.execute('''
            SELECT p.id_pase, IFNULL(e.firstname, 'Visitante'), p.fecha_expiracion, p.autorizo
            FROM PasesTemporales p
            LEFT JOIN Empleados e ON p.id_pase = e.id_employee
            WHERE p.id_pase = ?
        ''', (id_pase,))
        pase = cursor.fetchone()
        
        if not pase:
            flash("Pase no encontrado.", "danger")
            return redirect(url_for('rh_pases'))

        autorizo_txt = pase[3] or 'RH'
        tipo_pase = 'PASE'
        if '[' in autorizo_txt and ']' in autorizo_txt:
            tipo_pase = autorizo_txt.split('[')[-1].replace(']', '').strip()
            autorizo_txt = autorizo_txt.split('[')[0].strip()

        # Se envuelve el pase en una lista de 1 elemento para reutilizar el generador
        lista_pase = [(pase[0], pase[1], pase[2], autorizo_txt, tipo_pase)]
        pdf_buffer = construir_pdf_pases(lista_pase)
        
        return send_file(
            pdf_buffer, 
            as_attachment=True, 
            download_name=f"Reimpresion_{pase[0]}.pdf",
            mimetype='application/pdf'
        )
    finally:
        conexion.close()


# --- DEMÁS RUTAS RH ---
@app.route('/rh/dashboard')
@requiere_login
def dashboard_rh():
    conexion = obtener_conexion()
    try:
        cursor = conexion.cursor()
        hace_una_semana = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        hoy = datetime.now().strftime('%Y-%m-%d') 
        hace_30_dias = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        
        cursor.execute('''
            SELECT substr(date_hour, 1, 10) as dia,
                   COUNT(*) as total,
                   SUM(CASE WHEN (strftime('%H:%M', date_hour) BETWEEN '06:00' AND '13:59') THEN 1 ELSE 0 END) as T1,
                   SUM(CASE WHEN (strftime('%H:%M', date_hour) BETWEEN '14:00' AND '21:59') THEN 1 ELSE 0 END) as T2,
                   SUM(CASE WHEN (strftime('%H:%M', date_hour) >= '22:00' OR strftime('%H:%M', date_hour) < '06:00') THEN 1 ELSE 0 END) as T3
            FROM Consumos
            WHERE substr(date_hour, 1, 10) BETWEEN ? AND ?
            GROUP BY dia ORDER BY dia DESC
        ''', (hace_una_semana, hoy))
        estadisticas = cursor.fetchall()
        
        cursor.execute('''
            SELECT substr(date_hour, 1, 10) as dia, COUNT(*) as total
            FROM Consumos
            WHERE substr(date_hour, 1, 10) BETWEEN ? AND ?
            GROUP BY dia ORDER BY dia ASC
        ''', (hace_30_dias, hoy))
        estadisticas_mes = cursor.fetchall()

        cursor.execute('''
            SELECT c.date_hour, e.id_employee, e.firstname,
                CASE 
                    WHEN time(c.date_hour) >= '06:00:00' AND time(c.date_hour) < '14:00:00' THEN 'T1'
                    WHEN time(c.date_hour) >= '14:00:00' AND time(c.date_hour) < '22:00:00' THEN 'T2'
                    ELSE 'T3'
                END as turno
            FROM Consumos c
            JOIN Empleados e ON c.id_employee = e.id_employee
            ORDER BY c.date_hour DESC LIMIT 15
        ''')
        ultimos_registros = cursor.fetchall()
        
        return render_template('dashboard_rh.html', estadisticas=estadisticas, estadisticas_mes=estadisticas_mes, ultimos_registros=ultimos_registros)
    finally:
        conexion.close()

@app.route('/rh/autorizaciones')
@requiere_login
def autorizaciones_rh():
    conexion = obtener_conexion()
    try:
        cursor = conexion.cursor()
        fecha_hoy = datetime.now().strftime('%Y-%m-%d')
        cursor.execute('''
            SELECT c.date_hour, e.id_employee, e.firstname, c.Metodo
            FROM Consumos c
            JOIN Empleados e ON c.id_employee = e.id_employee
            WHERE date(c.date_hour) = ? AND c.Metodo LIKE 'Manual%'
            ORDER BY c.date_hour DESC
        ''', (fecha_hoy,))
        autorizaciones_hoy = cursor.fetchall()
        return render_template('rh_authorization.html', autorizaciones=autorizaciones_hoy)
    finally:
        conexion.close()

@app.route('/rh/autorizar', methods=['POST'])
@requiere_login
def autorizar_rh():
    id_employee = request.form.get('id_employee', '').strip().upper()
    autorizo = request.form.get('autorizo', '').strip()
    
    if not id_employee or not autorizo:
        flash('Debes ingresar la nómina y el nombre de quien autoriza.', 'danger')
        return redirect(url_for('autorizaciones_rh'))
        
    conexion = obtener_conexion()
    try:
        cursor = conexion.cursor()
        cursor.execute('SELECT firstname FROM Empleados WHERE id_employee = ?', (id_employee,))
        empleado = cursor.fetchone()
        
        if not empleado:
            flash(f'Error: La nómina "{id_employee}" no existe.', 'danger')
            return redirect(url_for('autorizaciones_rh'))

        inicio_turno, fin_turno, nombre_turno = obtener_ventana_turno()
        inicio_str = inicio_turno.strftime('%Y-%m-%d %H:%M:%S')
        fin_str = fin_turno.strftime('%Y-%m-%d %H:%M:%S')

        limite_excedido, consumos_act, limite_max = verificar_limite_superado(cursor, id_employee, inicio_str, fin_str)
        
        if limite_excedido:
            flash(f'¡Alerta! {empleado[0]} ({id_employee}) ya alcanzó su límite de {limite_max} consumos en el {nombre_turno}.', 'warning')
            return redirect(url_for('autorizaciones_rh'))
            
        ahora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('''
            INSERT INTO Consumos (date_hour, id_employee, Metodo) 
            VALUES (?, ?, ?)
        ''', (ahora, id_employee, f'Manual ({autorizo})'))
        conexion.commit()
        flash(f'✓ Pase registrado para {empleado[0]} ({id_employee}) [{consumos_act + 1}/{limite_max}].', 'success')
    finally:
        conexion.close()
        
    return redirect(url_for('autorizaciones_rh'))

@app.route('/exportar')
@requiere_login
def exportar_excel():
    fecha_inicio = request.args.get('inicio')
    fecha_fin = request.args.get('fin')

    conexion = obtener_conexion()
    try:
        query = """
            SELECT 
                date(c.date_hour) as Fecha, 
                time(c.date_hour) as Hora, 
                CASE 
                    WHEN time(c.date_hour) >= '06:00:00' AND time(c.date_hour) < '14:00:00' THEN 'Turno 1'
                    WHEN time(c.date_hour) >= '14:00:00' AND time(c.date_hour) < '22:00:00' THEN 'Turno 2'
                    ELSE 'Turno 3'
                END as Turno,
                e.id_employee as ID, 
                e.firstname as Nombre, 
                c.Metodo
            FROM Consumos c
            JOIN Empleados e ON c.id_employee = e.id_employee
            WHERE date(c.date_hour) BETWEEN ? AND ?
            ORDER BY c.date_hour ASC
        """
        df = pd.read_sql_query(query, conexion, params=(fecha_inicio, fecha_fin))
    finally:
        conexion.close()

    nombre_archivo = f"reporte_comedor_{fecha_inicio}_al_{fecha_fin}.xlsx"
    df.to_excel(nombre_archivo, index=False)
    return send_file(nombre_archivo, as_attachment=True)

# =========================================================
# RUTAS DE COCINA
# =========================================================

@app.route('/lnc')
def panel_cocina():
    conexion = obtener_conexion()
    try:
        cursor = conexion.cursor()
        fecha_hoy = datetime.now().strftime('%Y-%m-%d')
        
        cursor.execute('''
            SELECT 
                COUNT(*),
                SUM(CASE WHEN (time(date_hour) BETWEEN '06:00:00' AND '13:59:59') THEN 1 ELSE 0 END),
                SUM(CASE WHEN (time(date_hour) BETWEEN '14:00:00' AND '21:59:59') THEN 1 ELSE 0 END),
                SUM(CASE WHEN (time(date_hour) >= '22:00:00' OR time(date_hour) < '06:00:00') THEN 1 ELSE 0 END)
            FROM Consumos WHERE date(date_hour) = ?
        ''', (fecha_hoy,))
        row = cursor.fetchone()
        total_hoy, t1, t2, t3 = row[0] or 0, row[1] or 0, row[2] or 0, row[3] or 0
        
        cursor.execute('''
            SELECT 
                c.date_hour, 
                e.id_employee, 
                e.firstname,
                CASE 
                    WHEN time(c.date_hour) >= '06:00:00' AND time(c.date_hour) < '14:00:00' THEN 'T1'
                    WHEN time(c.date_hour) >= '14:00:00' AND time(c.date_hour) < '22:00:00' THEN 'T2'
                    ELSE 'T3'
                END as turno,
                c.Metodo
            FROM Consumos c
            JOIN Empleados e ON c.id_employee = e.id_employee
            WHERE date(c.date_hour) = ?
            ORDER BY c.date_hour DESC
            LIMIT 10
        ''', (fecha_hoy,))
        ultimos_registros = cursor.fetchall()
        return render_template('lnc.html', total_hoy=total_hoy, t1=t1, t2=t2, t3=t3, ultimos_registros=ultimos_registros)
    finally:
        conexion.close()

@app.route('/lnc/registrar', methods=['POST'])
def registrar_cocina():
    id_escaneado = request.form['id_employee'].strip().upper()
    autorizo = request.form.get('autorizo', 'Supervisión').strip()
    
    if not id_escaneado:
        flash("Por favor ingresa un número de nómina.", "warning")
        return redirect(url_for('panel_cocina'))

    ahora = datetime.now()
    fecha_hora_exacta = ahora.strftime('%Y-%m-%d %H:%M:%S')
    
    conexion = obtener_conexion()
    try:
        cursor = conexion.cursor()
        
        es_pase, resultado, nombre_beneficiario = procesar_pase_temporal(cursor, id_escaneado, fecha_hora_exacta, f"Cocina: {autorizo}")
        if es_pase:
            if resultado == "OK":
                conexion.commit()
                flash(f"¡Éxito! Pase canjeado para {nombre_beneficiario}.", "success")
            else:
                flash(f"Error en pase: {resultado}", "danger")
            return redirect(url_for('panel_cocina'))

        cursor.execute("SELECT firstname FROM Empleados WHERE id_employee = ?", (id_escaneado,))
        empleado = cursor.fetchone()
        
        if not empleado:
            flash(f"Error: La nómina {id_escaneado} no está registrada en el sistema.", "danger")
            return redirect(url_for('panel_cocina'))

        nombre = empleado[0]
        inicio_turno, fin_turno, nombre_turno = obtener_ventana_turno()
        inicio_str = inicio_turno.strftime('%Y-%m-%d %H:%M:%S')
        fin_str = fin_turno.strftime('%Y-%m-%d %H:%M:%S')

        limite_excedido, consumos_act, limite_max = verificar_limite_superado(cursor, id_escaneado, inicio_str, fin_str)
        
        if limite_excedido:
            flash(f"Alerta: {nombre} alcanzó el límite de {limite_max} consumos en el {nombre_turno}.", "warning")
            return redirect(url_for('panel_cocina'))
        
        metodo = f"Manual ({autorizo})"
        cursor.execute("INSERT INTO Consumos (id_employee, date_hour, Metodo) VALUES (?, ?, ?)", 
                       (id_escaneado, fecha_hora_exacta, metodo))
        conexion.commit()
        flash(f"¡Éxito! Comida registrada para {nombre} ({consumos_act + 1}/{limite_max}).", "success")
        return redirect(url_for('panel_cocina'))
    finally:
        conexion.close()

# =========================================================
# ENDPOINTS API (AJAX / TIEMPO REAL)
# =========================================================

@app.route('/api/kiosko/ultimo_evento')
def api_ultimo_evento():
    return jsonify(ultimo_evento_kiosko)

@app.route('/api/lnc/datos')
@app.route('/api/cocina/datos')
def api_lnc_datos():
    conexion = obtener_conexion()
    try:
        cursor = conexion.cursor()
        fecha_hoy = datetime.now().strftime('%Y-%m-%d')
        
        cursor.execute('''
            SELECT 
                COUNT(*),
                SUM(CASE WHEN (time(date_hour) BETWEEN '06:00:00' AND '13:59:59') THEN 1 ELSE 0 END),
                SUM(CASE WHEN (time(date_hour) BETWEEN '14:00:00' AND '21:59:59') THEN 1 ELSE 0 END),
                SUM(CASE WHEN (time(date_hour) >= '22:00:00' OR time(date_hour) < '06:00:00') THEN 1 ELSE 0 END)
            FROM Consumos WHERE date(date_hour) = ?
        ''', (fecha_hoy,))
        row = cursor.fetchone()
        total_hoy, t1, t2, t3 = row[0] or 0, row[1] or 0, row[2] or 0, row[3] or 0
        
        cursor.execute('''
            SELECT c.date_hour, e.id_employee, e.firstname,
                CASE 
                    WHEN time(c.date_hour) >= '06:00:00' AND time(c.date_hour) < '14:00:00' THEN 'T1'
                    WHEN time(c.date_hour) >= '14:00:00' AND time(c.date_hour) < '22:00:00' THEN 'T2'
                    ELSE 'T3'
                END as turno,
                c.Metodo
            FROM Consumos c
            JOIN Empleados e ON c.id_employee = e.id_employee
            WHERE date(c.date_hour) = ?
            ORDER BY c.date_hour DESC LIMIT 10
        ''', (fecha_hoy,))
        registros = cursor.fetchall()

        lista_registros = []
        for reg in registros:
            lista_registros.append({
                'hora': reg[0][11:16],
                'id': reg[1],
                'nombre': reg[2],
                'turno': reg[3],
                'metodo': reg[4]
            })
            
        return jsonify({
            'total_hoy': total_hoy,
            't1': t1,
            't2': t2,
            't3': t3,
            'registros': lista_registros
        })
    finally:
        conexion.close()

# =========================================================
# LECTURA DE HARDWARE (EVDEV EN SEGUNDO PLANO)
# =========================================================
def procesar_codigo_escaneado(id_escaneado):
    global ultimo_evento_kiosko
    id_escaneado = id_escaneado.upper().strip()
    print(f"[ESCÁNER DIRECTO] Código recibido: {id_escaneado}")
    
    ahora = datetime.now()
    fecha_hora_exacta = ahora.strftime('%Y-%m-%d %H:%M:%S')
    foto_empleado = obtener_ruta_foto(id_escaneado)
    
    conexion = obtener_conexion()
    try:
        cursor = conexion.cursor()
        
        es_pase, resultado, nombre_beneficiario = procesar_pase_temporal(cursor, id_escaneado, fecha_hora_exacta, 'escaner')
        if es_pase:
            if resultado == "OK":
                conexion.commit()
                print(f"[ESCÁNER] ¡Pase Temporal canjeado! {nombre_beneficiario}")
                ultimo_evento_kiosko = {
                    "timestamp": time_lib.time(),
                    "tipo": "success",
                    "mensaje": f"¡Pase Válido! Buen provecho, {nombre_beneficiario}",
                    "nombre": nombre_beneficiario,
                    "foto": "/static/fotos/default.jpg"
                }
            else:
                print(f"[ESCÁNER] Pase inválido: {resultado}")
                ultimo_evento_kiosko = {
                    "timestamp": time_lib.time(),
                    "tipo": "danger",
                    "mensaje": resultado,
                    "nombre": nombre_beneficiario or "Invitado",
                    "foto": "/static/fotos/default.jpg"
                }
            return

        cursor.execute("SELECT firstname FROM Empleados WHERE id_employee = ?", (id_escaneado,))
        empleado = cursor.fetchone()
        
        if not empleado:
            print(f"[ESCÁNER] Error: Empleado {id_escaneado} no existe.")
            ultimo_evento_kiosko = {
                "timestamp": time_lib.time(),
                "tipo": "danger",
                "mensaje": f"La nómina {id_escaneado} no está registrada.",
                "nombre": "Desconocido",
                "foto": "/static/fotos/default.jpg"
            }
            return

        inicio_turno, fin_turno, nombre_turno = obtener_ventana_turno()
        inicio_str = inicio_turno.strftime('%Y-%m-%d %H:%M:%S')
        fin_str = fin_turno.strftime('%Y-%m-%d %H:%M:%S')

        limite_excedido, consumos_act, limite_max = verificar_limite_superado(cursor, id_escaneado, inicio_str, fin_str)

        if limite_excedido:
            msg = f"¡{empleado[0]}, ya registraste tu comida!" if limite_max == 1 else f"¡{empleado[0]}, alcanzaste el límite de {limite_max} comidas este turno!"
            ultimo_evento_kiosko = {
                "timestamp": time_lib.time(),
                "tipo": "warning",
                "mensaje": msg,
                "nombre": empleado[0],
                "foto": foto_empleado
            }
            return

        cursor.execute("INSERT INTO Consumos (id_employee, date_hour, Metodo) VALUES (?, ?, ?)", 
                       (id_escaneado, fecha_hora_exacta, 'escaner'))
        conexion.commit()
        
        ultimo_evento_kiosko = {
            "timestamp": time_lib.time(),
            "tipo": "success",
            "mensaje": f"Buen provecho, {empleado[0]} ({consumos_act + 1}/{limite_max})",
            "nombre": empleado[0],
            "foto": foto_empleado
        }
    finally:
        conexion.close()

# =========================================================
# LECTURA DE HARDWARE (EVDEV EN SEGUNDO PLANO)
# =========================================================

def obtener_ruta_escaner():
    """Busca específicamente el teclado/lector emulado Honeywell o HID."""
    # 1. Prioridad: Lector Honeywell por ID
    dispositivos_honeywell = glob.glob('/dev/input/by-id/*Honeywell*event-kbd*')
    if dispositivos_honeywell:
        return dispositivos_honeywell[0]

    # 2. Prioridad: Cualquier teclado/lector USB por ID
    todos_los_kbds = glob.glob('/dev/input/by-id/*event-kbd*')
    if todos_los_kbds:
        return todos_los_kbds[0]

    return None

def hilo_lector_codigo_barras():
    """Hilo con auto-reconexión y captura exclusiva mediante dev.grab()."""
    while True:
        try:
            ruta_dispositivo = obtener_ruta_escaner()
            
            if not ruta_dispositivo:
                time_lib.sleep(3)
                continue

            dev = InputDevice(ruta_dispositivo)
            dev.grab()  # Captura exclusiva: evita pérdida de caracteres y rebotes
            print(f"[ESCÁNER HARDWARE] Conectado exitosamente a: {ruta_dispositivo}")

            codigo = ""
            for event in dev.read_loop():
                if event.type == ecodes.EV_KEY:
                    data = categorize(event)
                    if data.keystate == 1:  # Tecla presionada
                        keycode = data.keycode
                        if keycode == 'KEY_ENTER':
                            if codigo.strip():
                                procesar_codigo_escaneado(codigo)
                            codigo = ""
                        elif keycode in KEY_MAP:
                            codigo += KEY_MAP[keycode]

        except Exception as e:
            print(f"[ESCÁNER HARDWARE] Desconexión o error ({e}). Reintentando en 3s...")
            time_lib.sleep(3)

# Iniciar hilo en segundo plano
threading.Thread(target=hilo_lector_codigo_barras, daemon=True).start()

if __name__ == '__main__':
    from waitress import serve
    print("Servidor de Comedor INICIADO (Waitress)")
    print("Accede al Kiosco en: http://localhost:5000")
    print("Accede a RH en: http://localhost:5000/rh")
    serve(app, host='0.0.0.0', port=5000)