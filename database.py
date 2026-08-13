# database.py
import sqlite3
import os
import random
import string
from datetime import datetime, time as time_obj, timedelta


# Fuerza la localización exacta de comedor.db en la raíz del proyecto
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'comedor.db')

LIMITES_POR_TURNO = {
    'EX000001': 6,   # EXTERNOS: Máximo 6 comidas por turno
    'PRV001': 5,     # PROVEEDORES: Máximo 5 comidas por turno
    'VST001': 10     # VISITAS: Máximo 10 comidas por turno
}

def inicializar_base_datos():
    """Configura el modo WAL y crea las tablas necesarias si no existen."""
    try:
        conexion = sqlite3.connect(DB_PATH, timeout=30.0)
        conexion.execute('PRAGMA journal_mode=WAL;')
        conexion.execute('PRAGMA synchronous=NORMAL;')
        
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

def obtener_conexion():
    return sqlite3.connect(DB_PATH, timeout=30.0)

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

def generar_id_pase_unico(cursor):
    while True:
        sufijo = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        nuevo_id = f"TMP{sufijo}"
        cursor.execute("SELECT 1 FROM PasesTemporales WHERE id_pase = ?", (nuevo_id,))
        if not cursor.fetchone():
            return nuevo_id