# scanner.py
import glob
import threading
import time as time_lib
from datetime import datetime
try:
    from evdev import InputDevice, categorize, ecodes
except ImportError:
    print("evdev no disponible en este sistema")
from database import (
    obtener_conexion, 
    procesar_pase_temporal, 
    obtener_ventana_turno, 
    verificar_limite_superado
)
from utils import obtener_ruta_foto

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

ultimo_evento_kiosko = {
    "timestamp": 0,
    "tipo": "",
    "mensaje": "",
    "nombre": "",
    "foto": "/static/fotos/default.jpg"
}

def procesar_codigo_escaneado(id_escaneado):
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
                ultimo_evento_kiosko.update({
                    "timestamp": time_lib.time(),
                    "tipo": "success",
                    "mensaje": f"¡Pase Válido! Buen provecho, {nombre_beneficiario}",
                    "nombre": nombre_beneficiario,
                    "foto": "/static/fotos/default.jpg"
                })
            else:
                print(f"[ESCÁNER] Pase inválido: {resultado}")
                ultimo_evento_kiosko.update({
                    "timestamp": time_lib.time(),
                    "tipo": "danger",
                    "mensaje": resultado,
                    "nombre": nombre_beneficiario or "Invitado",
                    "foto": "/static/fotos/default.jpg"
                })
            return

        cursor.execute("SELECT firstname FROM Empleados WHERE id_employee = ?", (id_escaneado,))
        empleado = cursor.fetchone()
        
        if not empleado:
            print(f"[ESCÁNER] Error: Empleado {id_escaneado} no existe.")
            ultimo_evento_kiosko.update({
                "timestamp": time_lib.time(),
                "tipo": "danger",
                "mensaje": f"La nómina {id_escaneado} no está registrada.",
                "nombre": "Desconocido",
                "foto": "/static/fotos/default.jpg"
            })
            return

        inicio_turno, fin_turno, nombre_turno = obtener_ventana_turno()
        inicio_str = inicio_turno.strftime('%Y-%m-%d %H:%M:%S')
        fin_str = fin_turno.strftime('%Y-%m-%d %H:%M:%S')

        limite_excedido, consumos_act, limite_max = verificar_limite_superado(cursor, id_escaneado, inicio_str, fin_str)

        if limite_excedido:
            msg = f"¡{empleado[0]}, ya registraste tu comida!" if limite_max == 1 else f"¡{empleado[0]}, alcanzaste el límite de {limite_max} comidas este turno!"
            ultimo_evento_kiosko.update({
                "timestamp": time_lib.time(),
                "tipo": "danger",
                "mensaje": msg,
                "nombre": empleado[0],
                "foto": foto_empleado
            })
            return

        cursor.execute("INSERT INTO Consumos (id_employee, date_hour, Metodo) VALUES (?, ?, ?)", 
                       (id_escaneado, fecha_hora_exacta, 'escaner'))
        conexion.commit()
        
        ultimo_evento_kiosko.update({
            "timestamp": time_lib.time(),
            "tipo": "success",
            "mensaje": f"Buen provecho, {empleado[0]} ({consumos_act + 1}/{limite_max})",
            "nombre": empleado[0],
            "foto": foto_empleado
        })
    finally:
        conexion.close()

def obtener_ruta_escaner():
    dispositivos_honeywell = glob.glob('/dev/input/by-id/*Honeywell*event-kbd*')
    if dispositivos_honeywell:
        return dispositivos_honeywell[0]

    todos_los_kbds = glob.glob('/dev/input/by-id/*event-kbd*')
    if todos_los_kbds:
        return todos_los_kbds[0]

    return None

def hilo_lector_codigo_barras():
    while True:
        try:
            ruta_dispositivo = obtener_ruta_escaner()
            if not ruta_dispositivo:
                time_lib.sleep(3)
                continue

            dev = InputDevice(ruta_dispositivo)
            dev.grab()
            print(f"[ESCÁNER HARDWARE] Conectado exitosamente a: {ruta_dispositivo}")

            codigo = ""
            for event in dev.read_loop():
                if event.type == ecodes.EV_KEY:
                    data = categorize(event)
                    if data.keystate == 1:
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

def iniciar_escaneo():
    threading.Thread(target=hilo_lector_codigo_barras, daemon=True).start()