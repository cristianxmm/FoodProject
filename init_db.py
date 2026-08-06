import os
import sqlite3
import pandas as pd

DB_NAME = "comedor.db"
EXCEL_FILE = "empleados.xlsx"  # Cambia esto si tu archivo se llama diferente (ej: empleados.xls)

def inicializar_base_de_datos():
    conexion = sqlite3.connect(DB_NAME)
    cursor = conexion.cursor()

    # 1. Crear tablas de la base de datos
    cursor.executescript("""
    PRAGMA foreign_keys = ON;

    CREATE TABLE IF NOT EXISTS Empleados (
        id_employee TEXT PRIMARY KEY,
        firstname TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS Consumos (
        id_consumption INTEGER PRIMARY KEY AUTOINCREMENT,
        id_employee TEXT NOT NULL,
        date_hour TEXT NOT NULL DEFAULT (datetime('now')),
        Metodo TEXT NOT NULL,
        FOREIGN KEY (id_employee) REFERENCES Empleados(id_employee)
    );
    """)

    # 2. Cargar datos desde el Excel con tus encabezados exactos
    if os.path.exists(EXCEL_FILE):
        print(f"Cargando empleados desde '{EXCEL_FILE}'...")
        try:
            # Forzar la lectura como texto para conservar formatos exactos de ID
            df = pd.read_excel(EXCEL_FILE, dtype=str)
            
            # Limpiar posibles espacios extra en los encabezados
            df.columns = df.columns.str.strip()

            columnas_requeridas = ['ID', 'First Name', 'Last Name']
            if all(col in df.columns for col in columnas_requeridas):
                # Eliminar filas vacías en la columna ID
                df = df.dropna(subset=['ID'])

                # Limpiar espacios
                df['ID'] = df['ID'].str.strip()
                df['First Name'] = df['First Name'].fillna('').str.strip()
                df['Last Name'] = df['Last Name'].fillna('').str.strip()

                # Concatenar First Name + Last Name
                df['NombreCompleto'] = (df['First Name'] + ' ' + df['Last Name']).str.strip()

                # Preparar lista de tuplas para SQLite (id_employee, firstname)
                registros = list(zip(df['ID'], df['NombreCompleto']))

                # Insertar o actualizar empleados
                cursor.executemany("""
                    INSERT OR REPLACE INTO Empleados (id_employee, firstname) 
                    VALUES (?, ?)
                """, registros)

                print(f"¡Éxito! Se procesaron {len(registros)} empleados correctamente.")
            else:
                print(f"Error: No se encontraron las columnas 'ID', 'First Name' y 'Last Name'.")
                print(f"Columnas detectadas en el Excel: {list(df.columns)}")

        except Exception as e:
            print(f"Error al leer el archivo Excel: {e}")
    else:
        print(f"Aviso: No se encontró el archivo '{EXCEL_FILE}'. Se generó la BD vacía.")

    conexion.commit()
    conexion.close()
    print("Base de datos inicializada correctamente.")

if __name__ == "__main__":
    inicializar_base_de_datos()