import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

import aiomysql
from aiomysql import Error

from core.config import settings
from core.db_pool import DBConnectionPool
from core.utils import current_colombian_time


class MySQLInventoryManager:
    def __init__(self):
        """
        Inicializa el gestor de inventario MySQL.
        Usa el pool de conexiones compartido en lugar de crear uno propio.
        """
        self.db_pool = DBConnectionPool()
        logging.info(
            "Gestor de inventario MySQL inicializado. Base de datos: '%s'",
            settings.db_database
        )
    
    async def get_inventory(self) -> List[Dict[str, Any]]:
        """
        Obtiene todo el inventario.
        """
        try:
            pool = await self.db_pool.get_pool()
            
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    try:
                        query = "SELECT * FROM inventory"
                        await cursor.execute(query)
                        products = await cursor.fetchall()
                        
                        return products
                    except Error as err:
                        logging.exception("Error al obtener inventario: %s", err)
                        return []
        except Exception as e:
            logging.exception("Error general al obtener productos del inventario: %s", e)
            return []
    
    async def update_product(self, product_id: str, updated_fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Actualiza la información de un producto en el inventario.
        """
        try:
            pool = await self.db_pool.get_pool()
            
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    try:
                        # First, get the current product
                        query = "SELECT * FROM inventory WHERE id = %s"
                        await cursor.execute(query, (product_id,))
                        product = await cursor.fetchone()
                        
                        if not product:
                            logging.warning("Producto no encontrado: %s", product_id)
                            return None
                        
                        # Update the product with new fields
                        product.update(updated_fields)
                        
                        # Prepare the update query
                        fields = [f"{key} = %s" for key in updated_fields.keys()]
                        query = f"UPDATE inventory SET {', '.join(fields)} WHERE id = %s"
                        
                        # Prepare values for the query
                        values = list(updated_fields.values())
                        values.append(product_id)
                        
                        await cursor.execute(query, values)
                        await conn.commit()
                        
                        # Get the updated product
                        query = "SELECT * FROM inventory WHERE id = %s"
                        await cursor.execute(query, (product_id,))
                        updated_product = await cursor.fetchone()
                        
                        logging.info("Producto actualizado: %s", product_id)
                        return updated_product
                    except Error as err:
                        await conn.rollback()
                        logging.exception("Error al actualizar producto: %s", err)
                        return None
        except Exception as e:
            logging.exception("Error general al actualizar producto: %s", e)
            return None
    
    async def close(self):
        """Cierra el pool de conexiones."""
        if self.db_pool:
            await self.db_pool.close()

    async def insert_menu_products(self, menu_data: Dict[str, Any]) -> bool:
        """
        Inserta los productos extraídos de un menú en la tabla inventory.
        Primero elimina todos los productos de tipo 'ejecutivo' existentes.
        
        Args:
            menu_data (Dict[str, Any]): Diccionario con los datos del menú extraído.
                Debe contener una lista de productos con sus detalles.
        
        Returns:
            bool: True si la inserción fue exitosa, False en caso contrario.
        """
        try:
            pool = await self.db_pool.get_pool()
            
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    try:
                        # Verificar si menu_data es un diccionario válido
                        if not isinstance(menu_data, dict):
                            logging.error("Los datos del menú no son un diccionario válido")
                            return False

                        # Primero, eliminar todos los productos ejecutivos existentes
                        delete_query = "DELETE FROM inventory WHERE tipo_producto = 'ejecutivo'"
                        await cursor.execute(delete_query)
                        deleted_count = cursor.rowcount
                        logging.info(f"Se eliminaron {deleted_count} productos ejecutivos anteriores")

                        # Preparar la consulta de inserción
                        insert_query = """
                        INSERT INTO inventory 
                        (name, quantity, unit, price, descripcion, tipo_producto) 
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """
                        
                        # Obtener la lista de productos del menú
                        productos = menu_data.get('menu', [])
                        if not productos:
                            logging.error("No se encontraron productos en el menú")
                            await conn.rollback()
                            return False

                        # Procesar cada producto del menú
                        inserted_count = 0
                        for product in productos:
                            # Determinar el tipo de menú basado en la categoría
                            tipo_producto = 'ejecutivo' if 'Ejecutivo' in product.get('categoria', '') else 'carta'
                            
                            values = (
                                product.get('nombre', ''),
                                100,  # Cantidad inicial por defecto
                                'plato',  # Unidad por defecto
                                float(product.get('precio', 0)),
                                product.get('descripcion', ''),
                                tipo_producto
                            )
                            
                            await cursor.execute(insert_query, values)
                            inserted_count += 1
                        
                        await conn.commit()
                        logging.info(f"Se insertaron {inserted_count} nuevos productos")
                        return True
                        
                    except Error as err:
                        await conn.rollback()
                        logging.exception("Error al insertar productos del menú: %s", err)
                        return False
                        
        except Exception as e:
            logging.exception("Error general al insertar productos del menú: %s", e)
            return False

    async def insert_menu(self, image_hex: str) -> bool:
        """
        Inserta un nuevo registro de menú en la tabla menus.
        Primero elimina los registros existentes de tipo 'ejecutivo'.

        Args:
            image_hex (str): Imagen en formato hexadecimal.

        Returns:
            bool: True si la inserción fue exitosa, False en caso contrario.
        """
        try:
            pool = await self.db_pool.get_pool()
            
            async with pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    try:
                        # Primero, eliminar los registros existentes de tipo 'ejecutivo'
                        delete_query = "DELETE FROM menus WHERE tipo_menu = 'ejecutivo'"
                        await cursor.execute(delete_query)
                        deleted_count = cursor.rowcount
                        logging.info(f"Se eliminaron {deleted_count} registros de menú ejecutivo anteriores")

                        # Insertar el nuevo registro en la tabla menus
                        query = """
                            INSERT INTO menus (tipo_menu, image_hex, created_at)
                            VALUES (%s, %s, NOW())
                        """
                        await cursor.execute(
                            query,
                            ("ejecutivo", image_hex)
                        )
                        await conn.commit()
                        
                        logging.info("Menú ejecutivo guardado exitosamente en la base de datos")
                        return True
                        
                    except Error as err:
                        await conn.rollback()
                        logging.exception(f"Error al insertar el menú: {err}")
                        return False
        except Exception as e:
            logging.exception(f"Error general al insertar el menú: {e}")
            return False

    async def get_all_menu_images(self) -> List[Dict[str, Any]]:
        """
        Obtiene todas las imágenes de menú almacenadas en la tabla menus.
        
        Returns:
            List[Dict[str, Any]]: Lista de diccionarios con la información de cada menú.
                Cada diccionario contiene:
                - id: ID del registro
                - tipo_menu: Tipo de menú (ejecutivo, carta, etc.)
                - image_hex: Imagen en formato hexadecimal
                - created_at: Fecha de creación
        """
        try:
            pool = await self.db_pool.get_pool()
            
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    try:
                        # Primero verificar si hay registros
                        count_query = "SELECT COUNT(*) as total FROM menus"
                        await cursor.execute(count_query)
                        count_result = await cursor.fetchone()
                        total_records = count_result['total']
                        logging.info(f"Total de registros en la tabla menus: {total_records}")
                        
                        if total_records == 0:
                            logging.warning("No se encontraron registros en la tabla menus")
                            return []
                        
                        # Obtener todos los registros
                        query = "SELECT id, tipo_menu, image_hex, created_at FROM menus"
                        await cursor.execute(query)
                        menus = await cursor.fetchall()
                        
                        logging.info(f"Se obtuvieron {len(menus)} registros de la tabla menus")
                        for menu in menus:
                            logging.info(f"Registro encontrado - ID: {menu['id']}, Tipo: {menu['tipo_menu']}")
                        
                        return menus
                    except Error as err:
                        logging.exception("Error al obtener imágenes de menú: %s", err)
                        return []
        except Exception as e:
            logging.exception("Error general al obtener imágenes de menú: %s", e)
            return []


