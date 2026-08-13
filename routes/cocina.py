# routes/cocina.py
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify

from database import (
    obtener_conexion, 
    procesar_pase_temporal, 
    obtener_ventana_turno, 
    verificar_limite_superado
)

cocina_bp = Blueprint('cocina', __name__)

@cocina_bp.route('/lnc')
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

@cocina_bp.route('/lnc/registrar', methods=['POST'])
def registrar_cocina():
    id_escaneado = request.form['id_employee'].strip().upper()
    autorizo = request.form.get('autorizo', 'Supervisión').strip()
    
    if not id_escaneado:
        flash("Por favor ingresa un número de nómina.", "warning")
        return redirect(url_for('cocina.panel_cocina'))

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
            return redirect(url_for('cocina.panel_cocina'))

        cursor.execute("SELECT firstname FROM Empleados WHERE id_employee = ?", (id_escaneado,))
        empleado = cursor.fetchone()
        
        if not empleado:
            flash(f"Error: La nómina {id_escaneado} no está registrada en el sistema.", "danger")
            return redirect(url_for('cocina.panel_cocina'))

        nombre = empleado[0]
        inicio_turno, fin_turno, nombre_turno = obtener_ventana_turno()
        inicio_str = inicio_turno.strftime('%Y-%m-%d %H:%M:%S')
        fin_str = fin_turno.strftime('%Y-%m-%d %H:%M:%S')

        limite_excedido, consumos_act, limite_max = verificar_limite_superado(cursor, id_escaneado, inicio_str, fin_str)
        
        if limite_excedido:
            flash(f"Alerta: {nombre} alcanzó el límite de {limite_max} consumos en el {nombre_turno}.", "warning")
            return redirect(url_for('cocina.panel_cocina'))
        
        metodo = f"Manual ({autorizo})"
        cursor.execute("INSERT INTO Consumos (id_employee, date_hour, Metodo) VALUES (?, ?, ?)", 
                       (id_escaneado, fecha_hora_exacta, metodo))
        conexion.commit()
        flash(f"¡Éxito! Comida registrada para {nombre} ({consumos_act + 1}/{limite_max}).", "success")
        return redirect(url_for('cocina.panel_cocina'))
    finally:
        conexion.close()

@cocina_bp.route('/api/lnc/datos')
@cocina_bp.route('/api/cocina/datos')
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