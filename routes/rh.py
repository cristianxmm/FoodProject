# routes/rh.py
import os
from datetime import datetime, timedelta
import pandas as pd
from flask import Blueprint, render_template, request, redirect, url_for, send_file, session, flash

from database import (
    obtener_conexion, 
    obtener_ventana_turno, 
    verificar_limite_superado, 
    generar_id_pase_unico
)
from pdf_generator import construir_pdf_pases
from utils import requiere_login

rh_bp = Blueprint('rh', __name__)

@rh_bp.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        user_input = request.form['username']
        pass_input = request.form['password']
        if user_input == os.getenv('RH_USER') and pass_input == os.getenv('RH_PASS'):
            session.permanent = True 
            session['usuario_autenticado'] = True
            return redirect(url_for('rh.menu_rh'))
        else:
            error = "Credenciales incorrectas. Intenta de nuevo."
    return render_template('login.html', error=error)

@rh_bp.route('/logout')
def logout():
    session.pop('usuario_autenticado', None)
    flash("Sesión cerrada correctamente.", "info")
    return redirect(url_for('rh.login'))

@rh_bp.route('/rh')
@requiere_login
def menu_rh():
    return render_template('rh_menu.html')

@rh_bp.route('/rh/rh_pases')
@rh_bp.route('/rh/pases')
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

@rh_bp.route('/rh/pases/generar', methods=['POST'])
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

    pdf_buffer = construir_pdf_pases(lista_generados)
    nombre_descarga = f"Pases_{tipo_pase}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
    
    return send_file(
        pdf_buffer, 
        as_attachment=True, 
        download_name=nombre_descarga,
        mimetype='application/pdf'
    )

@rh_bp.route('/rh/pases/reimprimir/<id_pase>')
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
            return redirect(url_for('rh.rh_pases'))

        autorizo_txt = pase[3] or 'RH'
        tipo_pase = 'PASE'
        if '[' in autorizo_txt and ']' in autorizo_txt:
            tipo_pase = autorizo_txt.split('[')[-1].replace(']', '').strip()
            autorizo_txt = autorizo_txt.split('[')[0].strip()

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

@rh_bp.route('/rh/dashboard')
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

# routes/rh.py

@rh_bp.route('/rh/authorization', methods=['GET', 'POST'])
@requiere_login
def authorization():
    if request.method == 'POST':
        id_employee = request.form.get('id_employee', '').strip().upper()
        autorizo = request.form.get('autorizo', '').strip()
        
        if not id_employee or not autorizo:
            flash('Debes ingresar la nómina y el nombre de quien autoriza.', 'danger')
            return redirect(url_for('rh.authorization'))
            
        conexion = obtener_conexion()
        try:
            cursor = conexion.cursor()
            cursor.execute('SELECT firstname FROM Empleados WHERE id_employee = ?', (id_employee,))
            empleado = cursor.fetchone()
            
            if not empleado:
                flash(f'Error: La nómina "{id_employee}" no existe.', 'danger')
                return redirect(url_for('rh.authorization'))

            inicio_turno, fin_turno, nombre_turno = obtener_ventana_turno()
            inicio_str = inicio_turno.strftime('%Y-%m-%d %H:%M:%S')
            fin_str = fin_turno.strftime('%Y-%m-%d %H:%M:%S')

            limite_excedido, consumos_act, limite_max = verificar_limite_superado(cursor, id_employee, inicio_str, fin_str)
            
            if limite_excedido:
                flash(f'¡Alerta! {empleado[0]} ({id_employee}) ya alcanzó su límite de {limite_max} consumos en el {nombre_turno}.', 'warning')
                return redirect(url_for('rh.authorization'))
                
            ahora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute('''
                INSERT INTO Consumos (date_hour, id_employee, Metodo) 
                VALUES (?, ?, ?)
            ''', (ahora, id_employee, f'Manual ({autorizo})'))
            conexion.commit()
            flash(f'✓ Pase registrado para {empleado[0]} ({id_employee}) [{consumos_act + 1}/{limite_max}].', 'success')
        finally:
            conexion.close()
            
    # Si es petición GET, simplemente renderiza la plantilla limpia
    return render_template('rh_authorization.html')

@rh_bp.route('/exportar')
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