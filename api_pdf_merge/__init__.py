import azure.functions as func
import logging
import fitz  # PyMuPDF
import base64
import json

def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Iniciando Validación de PDF (JSON Base64).')

    try:
        # 1. Obtener JSON
        try:
            req_body = req.get_json()
        except ValueError:
            return func.HttpResponse(
                json.dumps({"valid": False, "error": "El cuerpo no es un JSON válido"}),
                status_code=400,
                mimetype="application/json"
            )

        # 2. Obtener el string Base64
        # Esperamos: { "base64_pdf": "..." }
        b64_str = req_body.get('base64_pdf')

        if not b64_str:
            return func.HttpResponse(
                json.dumps({"valid": False, "error": "Falta la clave 'base64_pdf'"}),
                status_code=400,
                mimetype="application/json"
            )

        # 3. Intentar Validar
        try:
            # Decodificar
            file_bytes = base64.b64decode(b64_str)
            
            # Intentar abrir con PyMuPDF
            with fitz.open(stream=file_bytes, filetype="pdf") as doc:
                page_count = doc.page_count
                # Si llega aquí, el PDF es legible
                
                return func.HttpResponse(
                    json.dumps({
                        "valid": True,
                        "page_count": page_count,
                        "metadata": doc.metadata
                    }),
                    status_code=200,
                    mimetype="application/json"
                )

        except Exception as e:
            logging.warning(f"Validación fallida: {e}")
            return func.HttpResponse(
                json.dumps({
                    "valid": False,
                    "error": f"El archivo está corrupto o no es un PDF válido. Detalle: {str(e)}"
                }),
                status_code=200, # Devolvemos 200 OK porque la validación se ejecutó correctamente (el resultado es que es inválido)
                mimetype="application/json"
            )

    except Exception as ex:
        logging.error(f"Error crítico en validador: {str(ex)}")
        return func.HttpResponse(f"Error interno: {str(ex)}", status_code=500)