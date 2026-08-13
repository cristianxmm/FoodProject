# utils.py
import os
from functools import wraps
from flask import redirect, url_for, session, current_app

def requiere_login(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario_autenticado' not in session:
            # Corregido: 'rh.login' en lugar de 'login'
            return redirect(url_for('rh.login'))
        return f(*args, **kwargs)
    return decorated_function

def obtener_ruta_foto(id_employee):
    if not id_employee or str(id_employee).startswith("TMP"):
        return "/static/fotos/default.jpg"

    id_limpio = str(id_employee).strip()
    extensiones = ['.jpg', '.jpeg', '.png', '.webp', '.JPG', '.JPEG', '.PNG', '.WEBP']
    
    try:
        static_folder = current_app.static_folder or os.path.join(current_app.root_path, 'static')
    except RuntimeError:
        root_dir = os.path.dirname(os.path.abspath(__file__))
        static_folder = os.path.join(root_dir, 'static')

    carpeta_fotos = os.path.join(static_folder, 'fotos')

    for ext in extensiones:
        nombre_archivo = f"{id_limpio}{ext}"
        if os.path.isfile(os.path.join(carpeta_fotos, nombre_archivo)):
            return f"/static/fotos/{nombre_archivo}"

    return "/static/fotos/default.jpg"