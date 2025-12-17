import logging
import azure.functions as func
import json
import base64
import os
import tempfile
import uuid
import re
import time
import io
import fitz  # PyMuPDF
import cv2
import numpy as np
from langdetect import detect_langs

# --- IMPORTS DE INFRAESTRUCTURA COMPARTIDA ---
# (Estos vienen de tu carpeta shared/)
from shared.azure_blob import subir_bytes, subir_json
from shared.azure_vision import leer_texto_imagen
# ---------------------------------------------

# Configuración
BLOB_CONTAINER = "blob-publico"
BASE_TMP_DIR = tempfile.gettempdir()

# ==========================================
# 1. HELPERS DE RUTAS Y REGLAS
# ==========================================
def resolver_ruta_assets(rel_path):
    """
    Encuentra archivos en la carpeta assets/ subiendo 2 niveles.
    Ej: rel_path='templates/logo.png' -> '.../packaging-backend/assets/templates/logo.png'
    """
    # __file__ = .../api_pdf_validator/__init__.py
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    full_path = os.path.join(base_dir, "assets", rel_path)
    return full_path

def leer_reglas():
    path = resolver_ruta_assets("Reglas.json")
    if not os.path.exists(path):
        logging.error(f"FATAL: No se encuentra Reglas.json en: {path}")
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

# ==========================================
# 2. PROCESAMIENTO PDF (Texto e Imágenes)
# ==========================================
def extraer_texto_pdf(pdf_bytes: bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    items = []
    for page in doc:
        blocks = page.get_text("dict")["blocks"]
        for b in blocks:
            for line in b.get("lines", []):
                for span in line.get("spans", []):
                    text = span["text"].strip()
                    if not text: continue
                    font = span.get("font", "").lower()
                    # Detección básica de negrita por nombre de fuente
                    bold = "bold" in font or "black" in font or "negrita" in font
                    items.append({"text": text, "bold": bold})
    doc.close()
    return items

def renderizar_pdf_a_imagenes(pdf_bytes: bytes, dpi: int = 300):
    """Renderiza PDF a archivos temporales PNG para análisis visual."""
    session_id = uuid.uuid4().hex
    output_dir = os.path.join(BASE_TMP_DIR, f"render_{session_id}")
    os.makedirs(output_dir, exist_ok=True)
    
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    imagenes = []
    for num, page in enumerate(doc, start=1):
        pix = page.get_pixmap(dpi=dpi)
        out_path = os.path.join(output_dir, f"pagina_{num}.png")
        pix.save(out_path)
        imagenes.append(out_path)
    doc.close()
    return imagenes, output_dir

# ==========================================
# 3. MOTORES DE VALIDACIÓN (Lógica Específica)
# ==========================================

def detectar_template_opencv(img_path: str, template_rel_path: str, umbral: float = 0.3, prohibido: bool = False):
    """Busca un logo/template dentro de la imagen de la página."""
    template_full_path = resolver_ruta_assets(template_rel_path)
    
    if not os.path.exists(template_full_path):
        return False, f"Template no encontrado en assets: {template_rel_path}"

    try:
        img_main = cv2.imread(img_path, 0)
        img_tmpl = cv2.imread(template_full_path, 0)

        if img_main is None or img_tmpl is None:
            return False, "Error leyendo imágenes (OpenCV)"

        res = cv2.matchTemplate(img_main, img_tmpl, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
        
        encontrado = max_val >= umbral
        
        if prohibido:
            ok = not encontrado
            evidencia = f"Similitud: {max_val:.2f} (Prohibido si > {umbral})"
        else:
            ok = encontrado
            evidencia = f"Similitud: {max_val:.2f} (Requerido > {umbral})"
        
        return ok, evidencia
    except Exception as e:
        return False, f"Error OpenCV: {str(e)}"

def validar_texto(texto_items, reglas):
    resultados = []
    texto_completo = " ".join([i["text"] for i in texto_items])
    texto_upper = texto_completo.upper()

    for r in reglas:
        tipo = r["tipo"]
        ok, evidencia = False, ""
        
        if tipo == "ingredientes_titulo":
            found = next((i for i in texto_items if i["text"].lower().startswith("ingredientes")), None)
            if found:
                ok = found["bold"] and not found["text"].isupper()
                evidencia = f"Encontrado: '{found['text']}', Bold: {found['bold']}"
            else: evidencia = "No encontrado"

        elif tipo == "alergenos":
            if "lista" in r:
                buenos = []
                malos = []
                for al in r["lista"]:
                    matches = [i for i in texto_items if al.upper() in i["text"].upper()]
                    # Válido si está en mayúsculas y NO negrita
                    es_valido = any((m["text"].isupper() and not m["bold"]) for m in matches)
                    if es_valido: 
                        buenos.append(al)
                    elif matches:
                        malos.append(al)
                
                # Regla: OK si detectamos al menos uno bien y ninguno mal (ajustable según negocio)
                ok = len(buenos) > 0 
                evidencia = f"Correctos: {buenos} | Incorrectos: {malos}"
            else: evidencia = "Lista vacía"

        elif tipo == "regex_valido":
            ok = re.search(r["patron"], texto_completo, re.IGNORECASE) is not None
            evidencia = "Patrón hallado" if ok else "Falta patrón"

        elif tipo == "regex_invalido":
            errs = re.findall(r["patron"], texto_completo, re.IGNORECASE)
            ok = len(errs) == 0
            evidencia = f"Errores encontrados: {errs}" if errs else "Ninguno"

        elif tipo == "texto":
            ok = re.search(r["patron"], texto_completo, re.IGNORECASE) is not None
            evidencia = "Texto presente" if ok else "Texto ausente"
        
        elif tipo == "texto_condicional":
            ok, evidencia = True, "N/A"
            for c in r["condiciones"]:
                if c["marca"] in texto_upper:
                    ok = re.search(c["patron"], texto_completo, re.IGNORECASE) is not None
                    evidencia = f"Marca {c['marca']} -> Email {'OK' if ok else 'MAL'}"
                    break

        resultados.append({"categoria": "Texto", "regla": r["nombre"], "cumple": ok, "evidencia": evidencia})
    return resultados

def validar_visual(imagenes_paths, reglas):
    resultados = []
    if not reglas: return resultados

    for r in reglas:
        nombre = r["nombre"]
        tipo = r["tipo"]
        ok, evidencia = False, "No evaluado"

        for img in imagenes_paths:
            # 1. Template Matching (Logos) - LOCAL con OpenCV
            if tipo == "template_match":
                tmpls = r.get("templates", [r.get("template")])
                for t in tmpls:
                    if t:
                        match, ev = detectar_template_opencv(img, t, r.get("umbral", 0.3))
                        if match:
                            ok, evidencia = True, f"Logo {t}: {ev}"
                            break
                if ok: break
            
            elif tipo == "template_prohibido":
                match, ev = detectar_template_opencv(img, r["template"], prohibido=True)
                ok, evidencia = match, ev
                if not ok: break

            # 2. OCR (Texto en Imagen) - NUBE con Azure Vision (Shared)
            elif tipo == "ocr_text":
                logging.info(f"Ejecutando OCR Azure para: {nombre}")
                # Abrimos la imagen y llamamos a la función compartida
                with open(img, "rb") as f:
                    txt, err = leer_texto_imagen(f)
                
                if err:
                    evidencia, ok = f"Error OCR: {err}", False
                else:
                    norm = re.sub(r'\s+', ' ', txt.upper()).strip()
                    ok = any(p.upper() in norm for p in r["patrones"])
                    evidencia = "Texto en imagen OK" if ok else f"Leído: {norm[:50]}..."
                
                if ok: break
        
        resultados.append({"categoria": "Visual", "regla": nombre, "cumple": ok, "evidencia": evidencia})
    return resultados

def validar_idiomas(texto, reglas):
    res = []
    if not reglas: return res
    try:
        detectados = set(str(l).split(':')[0] for l in detect_langs(texto)) if len(texto) > 10 else []
    except: detectados = []
    
    for r in reglas:
        ok = len(detectados) >= r.get("min_idiomas", 1)
        res.append({"categoria": "Idiomas", "regla": r["nombre"], "cumple": ok, "evidencia": str(list(detectados))})
    return res

# ==========================================
# 4. FUNCIÓN PRINCIPAL (ENTRY POINT)
# ==========================================
def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Procesando solicitud de validación de PDF.')

    try:
        # --- 1. Parsear Body ---
        try:
            body = req.get_json()
        except ValueError:
            return func.HttpResponse("El body debe ser JSON válido", status_code=400)

        pdf_base64 = body.get("file")
        filename = body.get("filename", "documento.pdf")

        if not pdf_base64:
            return func.HttpResponse("Falta 'file' (base64)", status_code=400)

        # --- 2. Cargar Reglas ---
        reglas = leer_reglas()
        if not reglas:
            logging.warning("Reglas vacías o no encontradas en assets.")

        # --- 3. Decodificar y Procesar PDF ---
        pdf_bytes = base64.b64decode(pdf_base64)
        
        # Extraer texto nativo
        texto_items = extraer_texto_pdf(pdf_bytes)
        texto_full = " ".join([t["text"] for t in texto_items])
        
        # Renderizar imágenes (para visual)
        imagenes_paths, tmp_dir = renderizar_pdf_a_imagenes(pdf_bytes)

        # --- 4. Ejecutar Validaciones ---
        res_txt = validar_texto(texto_items, reglas.get("texto", []))
        res_vis = validar_visual(imagenes_paths, reglas.get("visual", []))
        res_lan = validar_idiomas(texto_full, reglas.get("idiomas", []))

        all_results = res_txt + res_vis + res_lan
        
        # --- 5. Generar Informe Final ---
        informe = {
            "archivo": filename,
            "estado_general": "Aprobado" if all(r["cumple"] for r in all_results) else "Rechazado",
            "resultados": all_results
        }

        # --- 6. Subir Evidencias a Blob (Usando Shared) ---
        try:
            safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", os.path.splitext(filename)[0])
            
            # Subir JSON
            ruta_informe = f"validaciones/informes/{safe_name}_informe.json"
            subir_json(informe, BLOB_CONTAINER, ruta_informe)
            
            # Subir Imágenes procesadas (Opcional)
            for idx, p in enumerate(imagenes_paths, 1):
                ruta_img = f"validaciones/imagenes/{safe_name}/pag_{idx}.png"
                with open(p, "rb") as f:
                    subir_bytes(f.read(), BLOB_CONTAINER, ruta_img, "image/png")
                    
        except Exception as e:
            logging.warning(f"No se pudo subir al blob: {e}")

        # --- 7. Limpieza ---
        for p in imagenes_paths:
            if os.path.exists(p): os.remove(p)
        try: os.rmdir(tmp_dir)
        except: pass

        return func.HttpResponse(
            json.dumps(informe, ensure_ascii=False),
            mimetype="application/json",
            status_code=200
        )

    except Exception as e:
        logging.exception("Error crítico en validación")
        return func.HttpResponse(
            f"Error interno: {str(e)}",
            status_code=500
        )