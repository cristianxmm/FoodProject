import sqlite3
import os

DB_NAME = "comedor.db"

# Evita recrear si ya existe (opcional)
if os.path.exists(DB_NAME):
    print("Database already exists.")
    exit()

conn = sqlite3.connect(DB_NAME)
cursor = conn.cursor()

cursor.executescript("""
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS Empleados (
    id_employee INTEGER PRIMARY KEY AUTOINCREMENT,
    firstname TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS Consumos (
    id_consumption INTEGER PRIMARY KEY AUTOINCREMENT,
    id_employee INTEGER NOT NULL,
    date_hour TEXT NOT NULL DEFAULT (datetime('now')),
    Metodo TEXT NOT NULL,
    FOREIGN KEY (id_employee) REFERENCES Empleados(id_employee)
);
""")

conn.commit()
conn.close()

print("Database created successfully.")