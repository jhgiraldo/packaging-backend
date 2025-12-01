import os
import json
import logging
from azure.storage.blob import BlobServiceClient, ContentSettings

def get_blob_service():
    """Obtiene el cliente de Blob usando la variable de entorno."""
    conn = os.getenv("AzureWebJobsStorage")
    if not conn:
        logging.error("Falta la configuración 'AzureWebJobsStorage'.")
        return None
    return BlobServiceClient.from_connection_string(conn)

def subir_bytes(data: bytes, container: str, blob_name: str, content_type: str = None):
    """Sube bytes a una ruta específica."""
    try:
        service = get_blob_service()
        if service:
            # Crear contenedor si no existe (opcional, pero útil)
            container_client = service.get_container_client(container)
            if not container_client.exists():
                container_client.create_container()

            blob_client = container_client.get_blob_client(blob_name)
            settings = ContentSettings(content_type=content_type) if content_type else None
            blob_client.upload_blob(data, overwrite=True, content_settings=settings)
            logging.info(f"Subido: {blob_name}")
    except Exception as e:
        logging.error(f"Error subiendo blob {blob_name}: {e}")

def subir_json(data_dict: dict, container: str, blob_name: str):
    """Helper para subir diccionarios como JSON."""
    json_bytes = json.dumps(data_dict, ensure_ascii=False, indent=2).encode("utf-8")
    subir_bytes(json_bytes, container, blob_name, content_type="application/json")