import os
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, send_file, session, flash
import sqlite3
from datetime import datetime, time, timedelta
import pandas as pd
from functools import wraps

load_dotenv()

app = Flask(__name__)

# =========================================================
# CONFIGURACIÓN Y AUTENTICACIÓN
# =========================================================
app.secret_key = os.getenv('SECRET_KEY', 'clave_secreta_por_defecto')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=20)

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
    
    if time(6, 0) <= hora_actual < time(14, 0):
        inicio = ahora.replace(hour=6, minute=0, second=0, microsecond=0)
        fin = ahora.replace(hour=13, minute=59, second=59)
        nombre_turno = "Turno 1"
    elif time(14, 0) <= hora_actual < time(22, 0):
        inicio = ahora.replace(hour=14, minute=0, second=0, microsecond=0)
        fin = ahora.replace(hour=21, minute=59, second=59)
        nombre_turno = "Turno 2"
    else:
        nombre_turno = "Turno 3"
        if hora_actual >= time(22, 0):
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

    conexion.close()
    return render_template('dashboard_rh.html', estadisticas=estadisticas, estadisticas_mes=estadisticas_mes)

    

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

if __name__ == '__main__':
    from waitress import serve
    print("Servidor de Comedor INICIADO (Waitress)")
    print("Accede al Kiosco en: http://localhost:5000")
    print("Accede a RH en: http://localhost:5000/rh")
    serve(app, host='0.0.0.0', port=5000)