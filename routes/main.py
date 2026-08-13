# routes/main.py
import asyncio
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, Response

from database import (
    obtener_datos_hoy, 
    obtener_conexion, 
    procesar_pase_temporal, 
    obtener_ventana_turno, 
    verificar_limite_superado
)
from tts_service import sintetizar_voz_neural
from scanner import ultimo_evento_kiosko

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    total, consumos = obtener_datos_hoy()
    return render_template('index.html', consumos=consumos, total_hoy=total)

@main_bp.route('/kiosk_split')
def kiosk_split():
    return render_template('kiosk_split.html')

@main_bp.route('/escanear', methods=['POST'])
def escanear():
    id_escaneado = request.form['id_employee'].strip().upper()
    metodo_ingreso = request.form.get('metodo_ingreso', 'escaner') 
    ahora = datetime.now()
    fecha_hora_exacta = ahora.strftime('%Y-%m-%d %H:%M:%S')
    
    conexion = obtener_conexion()
    try:
        cursor = conexion.cursor()
        
        es_pase, resultado, nombre_beneficiario = procesar_pase_temporal(cursor, id_escaneado, fecha_hora_exacta, metodo_ingreso)
        if es_pase:
            if resultado == "OK":
                conexion.commit()
                flash(f"¡Éxito! Pase canjeado. Buen provecho, {nombre_beneficiario}.", "success")
            else:
                flash(f"Pase Inválido: {resultado}", "danger")
            return redirect(url_for('main.index'))

        cursor.execute("SELECT firstname FROM Empleados WHERE id_employee = ?", (id_escaneado,))
        empleado = cursor.fetchone()
        
        if not empleado:
            flash(f"Error: Gafete {id_escaneado} no registrado.", "danger")
            return redirect(url_for('main.index'))

        nombre = empleado[0]
        inicio_turno, fin_turno, nombre_turno = obtener_ventana_turno()
        inicio_str = inicio_turno.strftime('%Y-%m-%d %H:%M:%S')
        fin_str = fin_turno.strftime('%Y-%m-%d %H:%M:%S')

        limite_excedido, consumos_act, limite_max = verificar_limite_superado(cursor, id_escaneado, inicio_str, fin_str)

        if limite_excedido:
            msg = f"Alerta: {nombre} ya comió en el {nombre_turno}." if limite_max == 1 else f"Alerta: {nombre} alcanzó el límite de {limite_max} consumos en el {nombre_turno}."
            flash(msg, "warning")
            return redirect(url_for('main.index'))
        
        cursor.execute("INSERT INTO Consumos (id_employee, date_hour, Metodo) VALUES (?, ?, ?)", 
                       (id_escaneado, fecha_hora_exacta, metodo_ingreso))
        conexion.commit()

        if metodo_ingreso == 'manual':
            flash(f"¡Éxito! {nombre} registrado manualmente ({consumos_act + 1}/{limite_max}).", "success")
        else:
            flash(f"¡Éxito! Buen provecho, {nombre} ({consumos_act + 1}/{limite_max}).", "success")
            
        return redirect(url_for('main.index'))
    finally:
        conexion.close()

@main_bp.route('/api/tts')
def api_tts():
    texto = request.args.get('texto', 'Buen provecho')
    try:
        audio_bytes = asyncio.run(sintetizar_voz_neural(texto))
        return Response(audio_bytes, mimetype="audio/mpeg")
    except Exception as e:
        print(f"Error generando TTS neural: {e}")
        return ("Error TTS", 500)

@main_bp.route('/api/kiosko/ultimo_evento')
def api_ultimo_evento():
    return jsonify(ultimo_evento_kiosko)