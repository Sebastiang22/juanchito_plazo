from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from services.openia_service import OpenAIService, get_openai_service
from core.mysql_inventory_manager import MySQLInventoryManager

router = APIRouter()

# Crear una instancia del gestor de inventario
inventory_manager = MySQLInventoryManager()

class MenuImageRequest(BaseModel):
    image_hex: str

@router.post("/extract", response_model=dict)
async def extract_menu_from_image(
    request: MenuImageRequest,
    openai_service: OpenAIService = Depends(get_openai_service)
):
    """
    Recibe una imagen del menú en formato hexadecimal, extrae su contenido en formato JSON utilizando el servicio de OpenAI
    y actualiza la base de datos con los nuevos productos.
    """
    try:
        # Guardar el menú en la base de datos
        success = await inventory_manager.insert_menu(request.image_hex)
        if not success:
            raise HTTPException(
                status_code=500,
                detail="Error al guardar el menú en la base de datos"
            )
        
        # Procesar la imagen con el servicio de OpenAI
        menu_data = await openai_service.extract_menu_from_image(
            image_hex=request.image_hex,
            prompt="Extrae toda la información del menú de esta imagen en formato JSON. "
                  "Incluye nombres de platos, descripciones, precios y categorías."
        )
        
        # Insertar los productos del menú en la base de datos
        success = await inventory_manager.insert_menu_products(menu_data)
        if not success:
            raise HTTPException(
                status_code=500,
                detail="Error al actualizar el menú en la base de datos"
            )

        # Obtener el menú actualizado de la base de datos
        updated_menu = await inventory_manager.get_inventory()
        
        return {
            "message": "Menú actualizado exitosamente",
            "menu_data": menu_data,
            "updated_inventory": updated_menu
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al procesar el menú: {str(e)}"
        )



