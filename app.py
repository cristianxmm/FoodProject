import os
import sqlite3
import threading
import time as time_lib
from datetime import datetime, time as time_obj, timedelta
from functools import wraps

import pandas as pd
from dotenv import load_dotenv
from evdev import InputDevice, categorize, ecodes
from flask import Flask, render_template, request, redirect, url_for, send_file, session, flash, jsonify

load_dotenv()

app = Flask(__name__)

# =========================================================
# CONFIGURACIÓN Y AUTENTICACIÓN
# =========================================================
app.secret_key = os.getenv('SECRET_KEY', 'clave_secreta_por_defecto')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=20)

# Variable global para notificaciones en tiempo real al kiosco
ultimo_evento_kiosko = {
    "timestamp": 0,
    "tipo": "",      # "success", "warning", "danger"
    "mensaje": "",
    "nombre": ""
}

# Mapeo de códigos de evento de evdev a caracteres
KEY_MAP = {
    'KEY_0': '0', 'KEY_1': '1', 'KEY_2': '2', 'KEY_3': '3', 'KEY_4': '4',
    'KEY_5': '5', 'KEY_6': '6', 'KEY_7': '7', 'KEY_8': '8', 'KEY_9': '9',
    'KEY_A': 'A', 'KEY_B': 'B', 'KEY_C': 'C', 'KEY_D': 'D', 'KEY_E': 'E',
    'KEY_F': 'F', 'KEY_G': 'G', 'KEY_H': 'H', 'KEY_I': 'I', 'KEY_J': 'J',
    'KEY_K': 'K', 'KEY_L': 'L', 'KEY_M': 'M', 'KEY_N': 'N', 'KEY_O': 'O',
    'KEY_P': 'P', 'KEY_Q': 'Q', 'KEY_R': 'R', 'KEY_S': 'S', 'KEY_T': 'T',
    'KEY_U': 'U', 'KEY_V': 'V', 'KEY_W': 'W', 'KEY_X': 'X', 'KEY_Y': 'Y', 'KEY_Z': 'Z'
}

def requiere_login(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario_autenticado' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        user_input = request.form['username']
        pass_input = request.form['password']
        
        if user_input == os.getenv('RH_USER') and pass_input == os.getenv('RH_PASS'):
            session.permanent = True 
            session['usuario_autenticado'] = True
            return redirect(url_for('panel_rh'))
        else:
            error = "Credenciales incorrectas. Intenta de nuevo."
            
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('usuario_autenticado', None)
    flash("Sesión cerrada correctamente.", "info")
    return redirect(url_for('login'))

# =========================================================
# FUNCIONES AUXILIARES (EL "CEREBRO")
# =========================================================

def obtener_datos_hoy():
    conexion = sqlite3.connect('comedor.db')
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
    
    lista_consumos = cursor.fetchall()
    conexion.close()
    
    return total, lista_consumos

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

# =========================================================
# RUTAS DEL KIOSCO (PANTALLA PRINCIPAL)
# =========================================================

@app.route('/')
def index():
    total, consumos = obtener_datos_hoy()
    return render_template('index.html', consumos=consumos, total_hoy=total)

@app.route('/escanear', methods=['POST'])
def escanear():
    id_escaneado = request.form['id_employee'].strip()
    metodo_ingreso = request.form.get('metodo_ingreso', 'escaner') 
    
    ahora = datetime.now()
    fecha_hora_exacta = ahora.strftime('%Y-%m-%d %H:%M:%S')
    
    conexion = sqlite3.connect('comedor.db')
    cursor = conexion.cursor()
    
    # 1. Verificar si el empleado existe
    cursor.execute("SELECT firstname FROM Empleados WHERE id_employee = ?", (id_escaneado,))
    empleado = cursor.fetchone()
    
    if not empleado:
        conexion.close()
        flash(f"Error: Gafete {id_escaneado} no registrado.", "danger")
        return redirect(url_for('index'))

    nombre = empleado[0]
    
    # 2. Verificar si ya comió EN ESTE TURNO
    inicio_turno, fin_turno, nombre_turno = obtener_ventana_turno()
    inicio_str = inicio_turno.strftime('%Y-%m-%d %H:%M:%S')
    fin_str = fin_turno.strftime('%Y-%m-%d %H:%M:%S')

    cursor.execute('''
        SELECT id_consumption FROM Consumos 
        WHERE id_employee = ? AND date_hour >= ? AND date_hour <= ?
    ''', (id_escaneado, inicio_str, fin_str))
    
    if cursor.fetchone():
        flash(f"Alerta: {nombre} ya comió en el {nombre_turno}.", "warning")
        return redirect(url_for('index'))
    
    # 3. Registrar con el Método
    cursor.execute("INSERT INTO Consumos (id_employee, date_hour, Metodo) VALUES (?, ?, ?)", (id_escaneado, fecha_hora_exacta, metodo_ingreso))
    conexion.commit()
    conexion.close()

    if metodo_ingreso == 'manual':
        flash(f"¡Éxito! {nombre} registrado manualmente. Toma tu ticket.", "success")
    else:
        flash(f"¡Éxito! Buen provecho, {nombre}.", "success")
        
    return redirect(url_for('index'))

# =========================================================
# RUTAS DE RECURSOS HUMANOS (/rh)
# =========================================================

@app.route('/rh')
@requiere_login
def panel_rh():
    conexion = sqlite3.connect('comedor.db')
    cursor = conexion.cursor()

    hace_una_semana = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    hoy = datetime.now().strftime('%Y-%m-%d') 
    hace_30_dias = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    
    # CONSULTA 1: Detalle por turnos (Últimos 7 días)
    cursor.execute('''
        SELECT substr(date_hour, 1, 10) as dia,
               COUNT(*) as total,
               SUM(CASE WHEN (strftime('%H:%M', date_hour) BETWEEN '06:00' AND '13:59') THEN 1 ELSE 0 END) as T1,
               SUM(CASE WHEN (strftime('%H:%M', date_hour) BETWEEN '14:00' AND '21:59') THEN 1 ELSE 0 END) as T2,
               SUM(CASE WHEN (strftime('%H:%M', date_hour) >= '22:00' OR strftime('%H:%M', date_hour) < '06:00') THEN 1 ELSE 0 END) as T3
        FROM Consumos
        WHERE substr(date_hour, 1, 10) BETWEEN ? AND ?
        GROUP BY dia
        ORDER BY dia DESC
    ''', (hace_una_semana, hoy))
    estadisticas = cursor.fetchall()
    
    # CONSULTA 2: Totales diarios (Últimos 30 días)
    cursor.execute('''
        SELECT substr(date_hour, 1, 10) as dia, COUNT(*) as total
        FROM Consumos
        WHERE substr(date_hour, 1, 10) BETWEEN ? AND ?
        GROUP BY dia ORDER BY dia ASC
    ''', (hace_30_dias, hoy))
    estadisticas_mes = cursor.fetchall()

    # CONSULTA 3: Últimos 15 marcajes en vivo
    cursor.execute('''
        SELECT 
            c.date_hour, 
            e.id_employee, 
            e.firstname,
            CASE 
                WHEN time(c.date_hour) >= '06:00:00' AND time(c.date_hour) < '14:00:00' THEN 'T1'
                WHEN time(c.date_hour) >= '14:00:00' AND time(c.date_hour) < '22:00:00' THEN 'T2'
                ELSE 'T3'
            END as turno
        FROM Consumos c
        JOIN Empleados e ON c.id_employee = e.id_employee
        ORDER BY c.date_hour DESC
        LIMIT 15
    ''')
    ultimos_registros = cursor.fetchall()

    conexion.close()
    
    return render_template(
        'dashboard_rh.html', 
        estadisticas=estadisticas, 
        estadisticas_mes=estadisticas_mes,
        ultimos_registros=ultimos_registros
    )

@app.route('/exportar')
@requiere_login
def exportar_excel():
    fecha_inicio = request.args.get('inicio')
    fecha_fin = request.args.get('fin')

    conexion = sqlite3.connect('comedor.db')
    
    query = f"""
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
        WHERE date(c.date_hour) BETWEEN '{fecha_inicio}' AND '{fecha_fin}'
        ORDER BY c.date_hour ASC
    """
    
    df = pd.read_sql_query(query, conexion)
    conexion.close()

    nombre_archivo = f"reporte_comedor_{fecha_inicio}_al_{fecha_fin}.xlsx"
    df.to_excel(nombre_archivo, index=False)

    return send_file(nombre_archivo, as_attachment=True)

# =========================================================
# RUTAS DE COCINA (REGISTRO MANUAL SIN CREDENCIAL)
# =========================================================

@app.route('/lnc')
def panel_cocina():
    conexion = sqlite3.connect('comedor.db')
    cursor = conexion.cursor()
    
    fecha_hoy = datetime.now().strftime('%Y-%m-%d')
    
    cursor.execute("SELECT COUNT(*) FROM Consumos WHERE date(date_hour) = ?", (fecha_hoy,))
    total_hoy = cursor.fetchone()[0]
    
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
        ORDER BY c.date_hour DESC
        LIMIT 10
    ''')
    ultimos_registros = cursor.fetchall()
    conexion.close()
    
    return render_template('lnc.html', total_hoy=total_hoy, ultimos_registros=ultimos_registros)

@app.route('/lnc/registrar', methods=['POST'])
def registrar_cocina():
    id_escaneado = request.form['id_employee'].strip()
    autorizo = request.form.get('autorizo', 'Supervisión').strip()
    
    if not id_escaneado:
        flash("Por favor ingresa un número de nómina.", "warning")
        return redirect(url_for('panel_cocina'))

    ahora = datetime.now()
    fecha_hora_exacta = ahora.strftime('%Y-%m-%d %H:%M:%S')
    
    conexion = sqlite3.connect('comedor.db')
    cursor = conexion.cursor()
    
    cursor.execute("SELECT firstname FROM Empleados WHERE id_employee = ?", (id_escaneado,))
    empleado = cursor.fetchone()
    
    if not empleado:
        conexion.close()
        flash(f"Error: La nómina {id_escaneado} no está registrada en el sistema.", "danger")
        return redirect(url_for('panel_cocina'))

    nombre = empleado[0]
    
    inicio_turno, fin_turno, nombre_turno = obtener_ventana_turno()
    inicio_str = inicio_turno.strftime('%Y-%m-%d %H:%M:%S')
    fin_str = fin_turno.strftime('%Y-%m-%d %H:%M:%S')

    cursor.execute('''
        SELECT id_consumption FROM Consumos 
        WHERE id_employee = ? AND date_hour >= ? AND date_hour <= ?
    ''', (id_escaneado, inicio_str, fin_str))
    
    if cursor.fetchone():
        conexion.close()
        flash(f"Alerta: {nombre} ya registró consumo en el {nombre_turno}.", "warning")
        return redirect(url_for('panel_cocina'))
    
    metodo = f"Manual ({autorizo})"
    cursor.execute("INSERT INTO Consumos (id_employee, date_hour, Metodo) VALUES (?, ?, ?)", 
                   (id_escaneado, fecha_hora_exacta, metodo))
    conexion.commit()
    conexion.close()

    flash(f"¡Éxito! Comida autorizada y registrada para {nombre}.", "success")
    return redirect(url_for('panel_cocina'))

# =========================================================
# ENDPOINTS API (AJAX / TIEMPO REAL)
# =========================================================

@app.route('/api/lnc/datos')
@app.route('/api/cocina/datos')
def api_lnc_datos():
    conexion = sqlite3.connect('comedor.db')
    cursor = conexion.cursor()
    fecha_hoy = datetime.now().strftime('%Y-%m-%d')
    
    cursor.execute("SELECT COUNT(*) FROM Consumos WHERE date(date_hour) = ?", (fecha_hoy,))
    total_hoy = cursor.fetchone()[0]
    
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
        ORDER BY c.date_hour DESC LIMIT 10
    ''')
    registros = cursor.fetchall()
    conexion.close()

    lista_registros = []
    for reg in registros:
        lista_registros.append({
            'hora': reg[0][11:16],
            'id': reg[1],
            'nombre': reg[2],
            'turno': reg[3],
            'metodo': reg[4]
        })
        
    return jsonify({'total_hoy': total_hoy, 'registros': lista_registros})

@app.route('/api/kiosko/estado')
def api_kiosko_estado():
    return jsonify(ultimo_evento_kiosko)

# =========================================================
# LECTURA DE HARDWARE (EVDEV EN SEGUNDO PLANO)
# =========================================================

def procesar_codigo_escaneado(id_escaneado):
    global ultimo_evento_kiosko
    print(f"[ESCÁNER DIRECTO] Código recibido: {id_escaneado}")
    
    ahora = datetime.now()
    fecha_hora_exacta = ahora.strftime('%Y-%m-%d %H:%M:%S')
    
    conexion = sqlite3.connect('comedor.db')
    cursor = conexion.cursor()
    
    cursor.execute("SELECT firstname FROM Empleados WHERE id_employee = ?", (id_escaneado,))
    empleado = cursor.fetchone()
    
    if not empleado:
        print(f"[ESCÁNER] Error: Empleado {id_escaneado} no existe.")
        ultimo_evento_kiosko = {
            "timestamp": time_lib.time(),
            "tipo": "danger",
            "mensaje": f"La nómina {id_escaneado} no está registrada.",
            "nombre": ""
        }
        conexion.close()
        return

    inicio_turno, fin_turno, _ = obtener_ventana_turno()
    inicio_str = inicio_turno.strftime('%Y-%m-%d %H:%M:%S')
    fin_str = fin_turno.strftime('%Y-%m-%d %H:%M:%S')

    cursor.execute('''
        SELECT id_consumption FROM Consumos 
        WHERE id_employee = ? AND date_hour >= ? AND date_hour <= ?
    ''', (id_escaneado, inicio_str, fin_str))
    
    if cursor.fetchone():
        print(f"[ESCÁNER] Alerta: {empleado[0]} ya registró consumo este turno.")
        ultimo_evento_kiosko = {
            "timestamp": time_lib.time(),
            "tipo": "warning",
            "mensaje": f"¡{empleado[0]}, ya registraste tu comida!",
            "nombre": empleado[0]
        }
        conexion.close()
        return

    cursor.execute("INSERT INTO Consumos (id_employee, date_hour, Metodo) VALUES (?, ?, ?)", 
                   (id_escaneado, fecha_hora_exacta, 'escaner'))
    conexion.commit()
    conexion.close()
    
    print(f"[ESCÁNER] ¡Éxito! Registro guardado para {empleado[0]}")
    ultimo_evento_kiosko = {
        "timestamp": time_lib.time(),
        "tipo": "success",
        "mensaje": f"¡Buen provecho, {empleado[0]}!",
        "nombre": empleado[0]
    }

def lector_hardware_escaner():
    ruta_dispositivo = '/dev/input/by-id/usb-Honeywell_Scanning___Mobility_Voyager-1250_24026N058C-event-kbd'
    try:
        dev = InputDevice(ruta_dispositivo)
        dev.grab()
        buffer_codigo = ""
        
        for event in dev.read_loop():
            if event.type == ecodes.EV_KEY:
                data = categorize(event)
                if data.keystate == 1:
                    keycode = data.keycode
                    if keycode in KEY_MAP:
                        buffer_codigo += KEY_MAP[keycode]
                    elif keycode == 'KEY_ENTER':
                        if buffer_codigo:
                            procesar_codigo_escaneado(buffer_codigo.strip())
                            buffer_codigo = ""
    except Exception as e:
        print(f"[ERROR ESCÁNER HARDWARE] No se pudo conectar al escáner directo: {e}")

# Iniciar hilo de lectura por hardware
hilo_escaner = threading.Thread(target=lector_hardware_escaner, daemon=True)
hilo_escaner.start()

if __name__ == '__main__':
    from waitress import serve
    print("Servidor de Comedor INICIADO (Waitress)")
    print("Accede al Kiosco en: http://localhost:5000")
    print("Accede a RH en: http://localhost:5000/rh")
    serve(app, host='0.0.0.0', port=5000)