import os
import time
import logging
from msrest.authentication import CognitiveServicesCredentials
from azure.cognitiveservices.vision.computervision import ComputerVisionClient
from azure.cognitiveservices.vision.computervision.models import OperationStatusCodes

def get_vision_client():
    endpoint = os.getenv("VISION_ENDPOINT")
    key = os.getenv("VISION_KEY")
    if not endpoint or not key:
        return None
    return ComputerVisionClient(endpoint, CognitiveServicesCredentials(key))

def leer_texto_imagen(image_stream):
    """
    Envía un stream de imagen a Azure y devuelve el texto plano.
    Retorna: (texto_str, error_msg)
    """
    client = get_vision_client()
    if not client:
        return "", "Faltan credenciales de Vision"

    try:
        read_response = client.read_in_stream(image_stream, raw=True)
        operation_location = read_response.headers["Operation-Location"]
        operation_id = operation_location.split("/")[-1]

        while True:
            read_result = client.get_read_result(operation_id)
            if read_result.status not in ['notStarted', 'running']:
                break
            time.sleep(0.3)

        if read_result.status == OperationStatusCodes.succeeded:
            texto = []
            for result in read_result.analyze_result.read_results:
                for line in result.lines:
                    texto.append(line.text)
            return "\n".join(texto), None
        else:
            return "", f"Error Azure Vision: {read_result.status}"
            
    except Exception as e:
        return "", str(e)