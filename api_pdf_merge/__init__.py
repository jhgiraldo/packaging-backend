import azure.functions as func
import logging
import fitz  # PyMuPDF
import io
import base64
import json

# --- LA FUNCIÓN SE LLAMA main (OBLIGATORIO) ---
def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Iniciando Merge de PDFs desde Power Automate (JSON Base64).')

    try:
        # 1. Intentar leer el cuerpo como JSON
        try:
            req_body = req.get_json()
        except ValueError:
            return func.HttpResponse("El cuerpo de la solicitud no es un JSON válido.", status_code=400)

        # 2. Extraer la lista de base64
        # Se espera: { "list_base64": [ "base64_string_1", "base64_string_2" ] }
        files_base64 = req_body.get('list_base64')

        if not files_base64 or not isinstance(files_base64, list):
            return func.HttpResponse("Se requiere una clave 'list_base64' que sea una lista.", status_code=400)

        # 3. Crear el documento destino vacío
        merged_doc = fitz.open()

        count_ok = 0

        # 4. Procesar cada string Base64
        for i, b64_str in enumerate(files_base64):
            try:
                # Si viene vacío, saltar
                if not b64_str:
                    continue

                # Decodificar Base64 -> Bytes
                file_bytes = base64.b64decode(b64_str)
                
                # Abrir PDF desde memoria
                with fitz.open(stream=file_bytes, filetype="pdf") as src_doc:
                    # Unir al documento principal
                    merged_doc.insert_pdf(src_doc)
                    count_ok += 1
                    
            except Exception as e:
                logging.warning(f"Error al procesar el archivo índice {i}: {str(e)}")
                # Continuamos con los siguientes aunque este falle
                continue

        if count_ok == 0:
            return func.HttpResponse("No se pudo procesar ningún PDF válido de la lista.", status_code=400)

        # 5. Generar el archivo final en memoria
        output_stream = io.BytesIO()
        merged_doc.save(output_stream)
        pdf_final_bytes = output_stream.getvalue()

        logging.info(f"Merge completado exitosamente. Total PDFs unidos: {count_ok}")

        # 6. Retornar el binario (application/pdf)
        return func.HttpResponse(
            pdf_final_bytes,
            status_code=200,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": "attachment; filename=merged_result.pdf"
            }
        )

    except Exception as ex:
        logging.error(f"Error crítico en la función: {str(ex)}")
        return func.HttpResponse(f"Error interno del servidor: {str(ex)}", status_code=500)