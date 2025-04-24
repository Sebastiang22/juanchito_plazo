import pdb
import json
import os
import logging
from typing import Any, Optional, List, Dict, cast
import requests

import nest_asyncio
nest_asyncio.apply()

from langchain_core.tools import tool
from core.mysql_order_manager import MySQLOrderManager
from core.config import settings
from core.utils import genereta_id, generate_order_id
from typing import List, Dict, Any
from core.mysql_inventory_manager import MySQLInventoryManager
from dotenv import load_dotenv
import os
load_dotenv(override=True)

# Definir la URL del servidor de Baileys como una variable global
BAILEYS_SERVER_URL = "http://localhost:3001"  # Cambia esta URL según sea necesario

async def get_menu_tool() -> List[Dict[str, Any]]:
    """
    Obtiene el menú del restaurante desde MySQL.

    :param restaurant_name: Nombre del restaurante a consultar.
    :return: Lista de diccionarios con la información del menú.
    """
    print(f"\033[92m\nget_menu_tool activada \033[0m")
    
    inventory_manager = MySQLInventoryManager()
    # Updated to use the new method without restaurant_id parameter
    menu_items = await inventory_manager.get_inventory()
    return menu_items

async def confirm_order_tool(
    product_id: str,
    product_name: str,
    quantity: int,
    address: str,
    price: float,
    user_name: Optional[str],
    details: Optional[str] = None,
    restaurant_id: str = "go_papa",
    user_id: Optional[str] = None,
) -> Optional[str]:
    """
    Realiza un pedido de un producto y lo guarda en MySQL de forma segura frente a concurrencia.

    Parámetros:
        product_id (str): Identificador del producto a pedir.
        product_name (str): Nombre del producto.
        quantity (int): Cantidad del producto.
        address (str): Dirección de entrega del pedido.
        price (float): Precio unitario del producto.
        user_name (Optional[str]): Nombre del usuario que realiza el pedido.
        details (Optional[str]): Detalles adicionales del pedido.
        restaurant_id (str): Identificador del restaurante. Por defecto "go_papa".
        user_id (Optional[str]): Identificador del usuario que realiza el pedido.

    Retorna:
        Optional[str]: Mensaje de confirmación si el pedido se realiza con éxito, o None en caso de error.
    """
    try:
        order_manager = MySQLOrderManager()

        # Preparamos el payload para crear la orden.
        # No incluimos enum_order: lo genera create_order de forma atómica.
        order_payload = {
            "product_name": product_name,
            "quantity": quantity,
            "details": details,
            "price": price,
            "state": "pendiente",
            "address": address,
            "user_name": user_name,
            "user_id": user_id,
            "restaurant_id": restaurant_id
        }

        # Llamada segura: internamente bloquea y calcula enum_order
        created = await order_manager.create_order(order_payload)
        if not created:
            return None

        total_with_delivery = price * quantity

        # Formateamos la respuesta para el cliente
        response = (
            f"Perfecto, serían **{quantity} platos de {product_name}** 🍽️.\n"
            f"El pedido se ha confirmado con éxito. Detalles del pedido:\n"
            f"Producto: {product_name}\n"
            f"Cantidad: {quantity}\n"
            f"Dirección de entrega: {address}\n"
            f"Precio total: {total_with_delivery}\n"
            f"Estado: pendiente\n"
        )

        # (Opcional) Actualizar datos del usuario en background
        if user_id:
            import asyncio
            async def _update_user():
                from core.mysql_user_manager import MySQLUserManager
                um = MySQLUserManager()
                await um.update_user_by_id(str(user_id), name=user_name, address=address)
            asyncio.create_task(_update_user())

        return response

    except Exception as e:
        logging.exception("Error al confirmar el pedido: %s", e)
        return None

async def get_order_status_tool(user_id: str) -> str:
    """
    Consulta el estado de todos los pedidos de un usuario específico.
    
    Parámetros:
        user_id (str): ID del usuario que realiza la consulta.
        restaurant_id (str): Identificador del restaurante. Por defecto "go_papa".
    
    Retorna:
        str: Información formateada del pedido o un mensaje informativo si no se encuentra.
    """
    # Crear una única instancia de MySQLOrderManager
    order_manager = MySQLOrderManager()
    order_info = await order_manager.get_order_status_by_user_id(user_id)
    if order_info is None:
        return f"No tiene pedido pedientes."
    print(
        f"\033[92m\nget_order_status_tool activada\n"
        f"user_id: {user_id}\n"
        f"order_info: {json.dumps(order_info, indent=4)}\033[0m"
    )
    return f"Pedido: {order_info}"

async def send_menu_pdf_tool(user_id: str) -> str:
    """
    Envía las imágenes del menú del restaurante al usuario.
    
    Parámetros:
        user_id (str): Identificador del usuario (número de teléfono) al que se enviarán las imágenes.
    
    Retorna:
        str: Mensaje de confirmación si el envío se realiza con éxito, o mensaje de error en caso contrario.
    """
    print(f"\033[92m\nsend_menu_pdf_tool activada\nuser_id: {user_id}\033[0m")
    
    try:
        from core.mysql_inventory_manager import MySQLInventoryManager
        
        # Obtener todas las imágenes del menú
        inventory_manager = MySQLInventoryManager()
        menu_images = await inventory_manager.get_all_menu_images()
        
        if not menu_images:
            return "No se encontraron imágenes del menú para enviar."
        
        whatsapp_api_url = f"{BAILEYS_SERVER_URL}/api/send-images"
        success_count = 0
        error_count = 0
        
        # Enviar cada imagen individualmente
        for menu in menu_images:
            payload = {
                "phone": user_id,
                "imageHex": menu["image_hex"]
            }
            
            try:
                response = requests.post(whatsapp_api_url, json=payload)
                if response.status_code == 200:
                    success_count += 1
                else:
                    error_count += 1
                    logging.error(f"Error al enviar imagen  {response.json().get('message', 'Error desconocido')}")
            except Exception as e:
                error_count += 1
                logging.error(f"Error al enviar imagen {str(e)}")
        
        # Preparar mensaje de respuesta
        if success_count > 0:
            message = f"Se enviaron {success_count} imágenes del menú exitosamente."
            if error_count > 0:
                message += f" Hubo {error_count} errores al enviar algunas imágenes."
            return message
        else:
            return f"No se pudo enviar ninguna imagen del menú. Hubo {error_count} errores."
    
    except Exception as e:
        logging.exception("Error al enviar las imágenes del menú: %s", e)
        return f"Error al enviar las imágenes del menú: {str(e)}"

async def update_order_tool(
    enum_order: str,
    product_name: str,
    user_id: Optional[str] = None,
    quantity: Optional[int] = None,
    details: Optional[str] = None,
    price: Optional[float] = None,
    new_product_name: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Actualiza un producto específico dentro de un pedido existente.

    Parámetros:
        enum_order (str): Identificador único del pedido.
        product_name (str): Nombre del producto a actualizar.
        user_id (Optional[str]): ID del usuario que realiza la actualización.
        quantity (Optional[int]): Nueva cantidad del producto.
        details (Optional[str]): Nuevas observaciones o detalles del producto.
        price (Optional[float]): Nuevo precio del producto.
        new_product_name (Optional[str]): Nuevo nombre para el producto.

    Retorna:
        Optional[Dict[str, Any]]: El pedido actualizado o None en caso de error.
    """
    print(f"\033[92m\nupdate_order_tool activada\nenum_order: {enum_order}\nproduct_name: {product_name}\nuser_id: {user_id}\nquantity: {quantity}\ndetails: {details}\nprice: {price}\nnew_product_name: {new_product_name}\033[0m")
    
    try:
        order_manager = MySQLOrderManager()
        
        # Preparar las actualizaciones
        updates = {}
        if quantity is not None:
            updates["quantity"] = quantity
        if details is not None:
            updates["details"] = details
        if price is not None:
            updates["price"] = price
        if new_product_name is not None:
            updates["new_product_name"] = new_product_name
        
        # Actualizar el producto
        updated_order = await order_manager.update_order_product(enum_order, product_name, updates)
        
        if updated_order:
            logging.info(f"Producto actualizado en el pedido {enum_order}: {product_name}")
            return updated_order
        else:
            logging.warning(f"No se pudo actualizar el producto {product_name} en el pedido {enum_order}")
            return None
    except Exception as e:
        logging.exception(f"Error al actualizar el producto: {e}")
        return None

async def send_location_tool(user_id: str) -> str:
    """
    Envía la ubicación del restaurante al cliente.

    Parámetros:
        user_id (str): ID del usuario (número de teléfono) al que se enviará la ubicación.

    Retorna:
        str: Mensaje de confirmación si el envío se realiza con éxito, o mensaje de error en caso contrario.
    """
    print(f"\033[92m\nsend_location_tool activada\033[0m")
    try:
        # Definir la ubicación del restaurante
        location_data = {
            "number": user_id
        }

        # Hacer la solicitud al endpoint para enviar la ubicación
        response = requests.post(f'{BAILEYS_SERVER_URL}/api/send-location', json=location_data)

        if response.status_code == 200:
            return "Ubicación del restaurante enviada correctamente."
        else:
            return f"Error al enviar la ubicación: {response.json().get('error', 'Error desconocido')}"

    except Exception as e:
        return f"Error al enviar la ubicación: {str(e)}"
