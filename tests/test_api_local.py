import requests
import base64
import json
import os

# ---------------- CONFIGURACIÓN ----------------
PDF_PATH = r"C:\Users\jgiraldo\OneDrive - HIBERUS SISTEMAS INFORMATICOS S.L\Documentos\ECI\ECI - PA\label samples\Cajas Piedra Coloma Garcia 2024.pdf"

# DESCOMENTA LA QUE QUIERAS USAR:

# A) ENTORNO LOCAL (Para cuando das F5 en VS Code)
URL = "http://localhost:7071/api/validatepdf"

# (Asegúrate de que la URL coincida con el nombre de tu carpeta de función)

# B) ENTORNO DESARROLLO / NUBE
# URL = "https://hiberus-juana-funcapp-dev-dkg6ahhzhmguhjhz.spaincentral-01.azurewebsites.net/api/validatepdf?code=TU_CODIGO_AQUI"

# ---------------- EJECUCIÓN ----------------
def probar_api():
    if not os.path.exists(PDF_PATH):
        print(f"❌ Error: No encuentro el archivo en: {PDF_PATH}")
        return

    filename = os.path.basename(PDF_PATH)
    print(f"--- 🚀 Probando API con: {filename} ---")
    print(f"📡 Destino: {URL}")

    try:
        # 1. Convertir a Base64
        with open(PDF_PATH, "rb") as f:
            pdf_base64 = base64.b64encode(f.read()).decode('utf-8')

        # 2. Payload
        payload = {
            "filename": filename,
            "file": pdf_base64
        }

        # 3. Enviar
        print("⏳ Enviando... (Espere, procesando OCR e imágenes)")
        response = requests.post(URL, json=payload, timeout=300) # Timeout generoso para OCR

        # 4. Resultados
        print(f"\nStatus Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("✅ ¡ÉXITO!")
            print(f"Estado: {data.get('estado_general', 'Desconocido')}")
            
            # Guardar respuesta para inspeccionar
            with open("respuesta_api.json", "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            print("📄 Respuesta guardada en 'scripts/respuesta_api.json'")
        else:
            print("❌ FALLÓ")
            print(response.text)

    except Exception as e:
        print(f"💥 Error crítico: {e}")

if __name__ == "__main__":
    probar_api()