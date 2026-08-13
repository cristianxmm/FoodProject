# app.py
import os
from datetime import timedelta
from dotenv import load_dotenv
from flask import Flask
from waitress import serve

from database import inicializar_base_datos
from scanner import iniciar_escaneo
from routes.main import main_bp
from routes.cocina import cocina_bp
from routes.rh import rh_bp

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'clave_secreta_por_defecto')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=20)

# Inicialización de servicios
inicializar_base_datos()
iniciar_escaneo()

# Registro de Blueprints
app.register_blueprint(main_bp)
app.register_blueprint(cocina_bp)
app.register_blueprint(rh_bp)

if __name__ == '__main__':
    print("Servidor de Comedor INICIADO (Waitress)")
    print("Accede al Kiosco en: http://localhost:5000")
    print("Accede a RH en: http://localhost:5000/rh")
    serve(app, host='0.0.0.0', port=5000)