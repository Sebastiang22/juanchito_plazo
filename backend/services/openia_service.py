# backend/services/openai_service.py
import base64
import json
from typing import List, Dict, Any, Optional

from openai import OpenAI
from core.config import settings

class OpenAIService:
    def __init__(self):
        """Inicializa el cliente de OpenAI con la API key desde la configuración de `core.config`."""
        try:
            self.client = OpenAI(api_key=settings.openai_api_key)
            self.model = settings.openai_model
            print(f"Servicio OpenAI inicializado con modelo: {self.model}")
        except Exception as e:
            print(f"Error al inicializar el servicio OpenAI: {e}")
            raise

    def get_embedding(self, text: str) -> List[float]:
        """
        Obtiene embeddings para un texto usando el modelo de embeddings de OpenAI.
        """
        try:
            print("Generando embedding...")
            response = self.client.embeddings.create(
                model="text-embedding-3-small",
                input=text
            )
            embedding = response.data[0].embedding
            print(f"Embedding generado con dimensión: {len(embedding)}")
            return embedding
        except Exception as e:
            print(f"Error al generar embedding: {e}")
            raise

    async def analyze_image(
        self,
        image_path: Optional[str] = None,
        image_url: Optional[str] = None,
        image_base64: Optional[str] = None,
        prompt: str = "Resuelve el problema de la imagen",
        model: Optional[str] = None,
        max_tokens: int = 500,
        temperature: float = 0.7
    ) -> str:
        """
        Analiza una imagen usando la API de visión de OpenAI.
        """
        try:
            model_to_use = model or self.model
            print(f"Iniciando análisis de imagen. Prompt: {prompt}")

            sources = [image_path, image_url, image_base64]
            if sum(1 for s in sources if s) != 1:
                msg = (
                    "Debe proporcionar exactamente una fuente de imagen: "
                    "path, URL o base64."
                )
                print(msg)
                raise ValueError(msg)

            if image_path:
                print(f"Fuente: Archivo local - {image_path}")
                with open(image_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                image_content = {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
                }
            elif image_url:
                print("Fuente: URL remota")
                image_content = {
                    "type": "image_url",
                    "image_url": {"url": image_url}
                }
            elif image_base64 is not None:
                print(f"Fuente: Base64 (len={len(image_base64)})")
                image_content = {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
                }
            else:
                raise ValueError("No se encontró ninguna fuente de imagen válida.")

            messages = [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    image_content
                ]
            }]

            params = {
                "model": model_to_use,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            }

            print("Enviando petición a OpenAI Chat API")
            resp = self.client.chat.completions.create(**params)
            result = resp.choices[0].message.content

            print(f"Respuesta recibida con longitud: {len(result)} caracteres")
            return result

        except Exception as e:
            print(f"Error en analyze_image: {e}")
            raise

    async def extract_menu_from_image(
        self,
        image_hex: Optional[str] = None,
        prompt: str = (
            "Extrae toda la información del menú de esta imagen en formato JSON. "
            "Incluye nombres de platos, descripciones, precios y categorías."
        ),
        model: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.3
    ) -> Dict[str, Any]:
        """
        Extrae información estructurada del menú de una imagen usando la API de visión de OpenAI.
        """
        try:
            model_to_use = model or self.model

            if image_hex is not None:
                image_bytes = bytes.fromhex(image_hex)
                b64 = base64.b64encode(image_bytes).decode()
                image_content = {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
                }
            else:
                raise ValueError("No se encontró ninguna fuente de imagen válida.")

            messages = [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    image_content
                ]
            }]

            params = {
                "model": model_to_use,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "response_format": {"type": "json_object"}
            }

            resp = self.client.chat.completions.create(**params)
            text = resp.choices[0].message.content

            try:
                menu = json.loads(text)
            except json.JSONDecodeError as e:
                menu = {"error": "No se pudo parsear JSON", "raw": text}

            return menu

        except Exception as e:
            raise

# Para inyección en FastAPI
async def get_openai_service() -> OpenAIService:
    return OpenAIService()
