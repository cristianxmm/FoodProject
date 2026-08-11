import os
import glob

def renombrar_fotos_hikvision():
    carpeta = "static/fotos"
    archivos = glob.glob(os.path.join(carpeta, "*.jpeg")) + glob.glob(os.path.join(carpeta, "*.jpg"))
    
    for ruta_archivo in archivos:
        nombre_original = os.path.basename(ruta_archivo)
        if "_" in nombre_original:
            # Extrae la nómina ubicada después del último '_'
            id_empleado = nombre_original.rsplit("_", 1)[-1].split(".")[0].strip()
            nueva_ruta = os.path.join(carpeta, f"{id_empleado}.jpg")
            
            # Evita sobrescribir si ya se llama igual
            if ruta_archivo != nueva_ruta:
                os.rename(ruta_archivo, nueva_ruta)
                print(f"Renombrado: {nombre_original} -> {id_empleado}.jpg")

if __name__ == "__main__":
    renombrar_fotos_hikvision()