import logging
import json
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

import aiomysql
from aiomysql import Error

from core.config import settings
from core.db_pool import DBConnectionPool
from core.utils import current_colombian_time
import pdb

class MySQLOrderManager:
    def __init__(self):
        """
        Inicializa el gestor de pedidos MySQL.
        Usa el pool de conexiones compartido en lugar de crear uno propio.
        """
        self.db_pool = DBConnectionPool()
        logging.info(
            "Gestor de pedidos MySQL inicializado. Base de datos: '%s'",
            settings.db_database
        )
    async def create_order(self, order: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Crea una nueva orden en la base de datos de forma segura frente a concurrencia."""
        try:
            # Timestamps
            now_str = current_colombian_time()
            created_at = datetime.strptime(now_str, '%Y-%m-%d %H:%M:%S')
            updated_at = created_at

            pool = await self.db_pool.get_pool()
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    # 1) Iniciar transacción
                    await conn.begin()
                    logging.info(f"[DEBUG] Iniciando creación de orden para user_id: {order.get('user_id')}")

                    # 2) Verificar si hay pedido PENDIENTE para este usuario
                    await cursor.execute(
                        """
                        SELECT enum_order, state
                          FROM orders
                         WHERE user_id = %s
                           AND state IN ('pendiente','en preparacion')
                         FOR UPDATE
                        """,
                        (order.get("user_id"),)
                    )
                    row = await cursor.fetchone()
                    if row and row.get("enum_order") is not None:
                        enum_order = int(row["enum_order"])
                        logging.info(f"[DEBUG] Encontrado pedido existente - enum_order: {enum_order}, estado: {row.get('state')} para user_id: {order.get('user_id')}")
                    else:
                        # 3) Calcular nuevo enum_order solo de pedidos del día actual
                        today_start = datetime.strptime(current_colombian_time().split()[0], '%Y-%m-%d')
                        await cursor.execute(
                            """
                            SELECT COALESCE(MAX(enum_order), 0) AS max_enum
                              FROM orders
                             WHERE created_at >= %s
                             FOR UPDATE
                            """,
                            (today_start,)
                        )
                        max_enum_row = await cursor.fetchone()
                        max_enum = int(max_enum_row.get("max_enum", 0))
                        enum_order = max_enum + 1
                        logging.info(f"[DEBUG] Nuevo enum_order calculado: {enum_order} para user_id: {order.get('user_id')} - Fecha inicio: {today_start}")

                    # 4) Insertar la nueva línea de pedido
                    fields = [
                        "enum_order", "product_name", "quantity", "state",
                        "address", "user_name", "user_id",
                        "created_at", "updated_at"
                    ]
                    values = [
                        enum_order,
                        order.get("product_name"),
                        order.get("quantity"),
                        "pendiente",
                        order.get("address"),
                        order.get("user_name"),
                        order.get("user_id"),
                        created_at,
                        updated_at
                    ]
                    # campos opcionales
                    if "price" in order:
                        fields.append("price");   values.append(order["price"])
                    if "details" in order:
                        fields.append("details"); values.append(order["details"])

                    placeholders = ", ".join(["%s"] * len(fields))
                    fields_str    = ", ".join(fields)
                    await cursor.execute(
                        f"INSERT INTO orders ({fields_str}) VALUES ({placeholders})",
                        tuple(values)
                    )

                    # 5) Commit y devolver registro completo
                    await conn.commit()
                    last_id = cursor.lastrowid
                    await cursor.execute("SELECT * FROM orders WHERE id = %s", (last_id,))
                    result = await cursor.fetchone()
                    logging.info(f"[DEBUG] Orden creada exitosamente - id: {last_id}, enum_order: {enum_order}, user_id: {order.get('user_id')}")
                    return result

        except Exception as e:
            # Si algo falla, hacer rollback para liberar bloqueos
            try:
                await conn.rollback()
            except:
                pass
            logging.exception(f"[DEBUG] Error al crear orden concurrente para user_id {order.get('user_id')}: {e}")
            return None


    
    async def get_latest_order(self) -> Optional[Dict[str, Any]]:
        """
        Recupera el enum_order del último pedido registrado en la tabla.

        :return: El enum_order del último pedido o None si no existe o se produce algún error.
        """
        try:
            pool = await self.db_pool.get_pool()
            
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    try:
                        await cursor.execute(
                            "SELECT enum_order FROM orders ORDER BY created_at DESC LIMIT 1"
                        )
                        order = await cursor.fetchone()
                        
                        if order:
                            logging.info("Último enum_order recuperado")
                            return order
                        else:
                            logging.warning("No se encontraron pedidos en la tabla")
                            return None
                    except Error as err:
                        logging.exception("Error al recuperar el último enum_order: %s", err)
                        return None
        except Exception as e:
            logging.exception("Error general al recuperar el último enum_order: %s", e)
            return None
    
    async def get_order_status_by_user_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        try:
            pool = await self.db_pool.get_pool()
            
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    try:
                        # Forzar commit para asegurar datos actualizados
                        await conn.commit()
                        
                        # Obtener la fecha actual (solo la parte de la fecha, sin la hora)
                        today_str = current_colombian_time().split()[0]  # Obtener solo la fecha (YYYY-MM-DD)
                        today = datetime.strptime(today_str, '%Y-%m-%d').date()
                        today_start = datetime.combine(today, datetime.min.time())
                        
                        # Obtener el último pedido para el usuario del día actual
                        await cursor.execute(
                            "SELECT * FROM orders WHERE user_id = %s AND created_at >= %s ORDER BY created_at DESC LIMIT 1", 
                            (user_id, today_start)
                        )
                        latest_order = await cursor.fetchone()
                        
                        if not latest_order:
                            logging.info("No se encontró ningún pedido para el usuario %s en el día actual", user_id)
                            return None
                        
                        enum_order = latest_order.get("enum_order")
                        if not enum_order:
                            logging.info("El último pedido para el usuario %s no tiene 'enum_order'.", user_id)
                            return None

                        # Consultar todos los pedidos que compartan el mismo 'enum_order'
                        # Asegurar que enum_order sea string
                        enum_order_str = str(enum_order)
                        logging.info(f"Buscando pedidos con enum_order: {enum_order_str} (tipo: {type(enum_order_str)})")
                        await cursor.execute(
                            "SELECT * FROM orders WHERE enum_order = %s ORDER BY created_at ASC", 
                            (enum_order_str,)
                        )
                        orders_in_group = await cursor.fetchall()
                        
                        if not orders_in_group:
                            logging.warning("No se encontraron pedidos con enum_order: %s", enum_order_str)
                            return None
                        
                        logging.info(f"Encontrados {len(orders_in_group)} pedidos para enum_order {enum_order_str}")
                        for order in orders_in_group:
                            logging.info(f"Producto encontrado: {order.get('product_name')} - {order.get('quantity')}")
                        # Construir el pedido consolidado
                        first_order = orders_in_group[0]
                        last_order = orders_in_group[-1]
                        
                        consolidated_order = {
                            "id": enum_order,
                            "address": first_order["address"],
                            "customer_name": first_order.get("user_name", ""),
                            "enum_order": enum_order,
                            "products": [],
                            "created_at": first_order.get("created_at").isoformat() if isinstance(first_order.get("created_at"), datetime) else first_order.get("created_at"),
                            "updated_at": latest_order.get("updated_at").isoformat() if isinstance(latest_order.get("updated_at"), datetime) else latest_order.get("updated_at"),
                            "state": latest_order.get("state")
                        }
                        
                        # Agregar productos al pedido consolidado
                        for order in orders_in_group:
                            product = {
                                "name": order.get("product_name", ""),
                                "quantity": order.get("quantity", 0),
                                "price": order.get("price", 0.0),
                                "details": order.get("details", "")
                            }
                            consolidated_order["products"].append(product)
                        
                        return consolidated_order
                    except Error as err:
                        logging.exception("Error al recuperar el estado del pedido para usuario %s: %s", user_id, err)
                        return None
        except Exception as e:
            logging.exception("Error general al recuperar el estado del pedido: %s", e)
            return None
    
    async def get_today_orders_not_paid(self) -> Dict[str, Any]:
        """
        Retorna todos los pedidos creados el día actual (UTC) cuyo estado sea distinto de 'pagado',
        agrupando en el campo 'products' todos los productos que comparten el mismo 'enum_order'.
        """
        try:
            pool = await self.db_pool.get_pool()
            
            async with pool.acquire() as conn:
                try:
                    # Establecer nivel de aislamiento antes de iniciar la transacción
                    async with conn.cursor() as isolation_cursor:
                        await isolation_cursor.execute("SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                    
                    # Iniciar transacción explícita después de configurar el nivel de aislamiento
                    await conn.begin()
                    
                    async with conn.cursor(aiomysql.DictCursor) as cursor:
                        # Obtener la fecha actual en formato UTC
                        today = datetime.now().date()
                        today_start = datetime.combine(today, datetime.min.time())
                        today_end = datetime.combine(today, datetime.max.time())
                        
                        # Obtener todos los pedidos y procesarlos en memoria
                        await cursor.execute("""
                            SELECT * FROM orders 
                            WHERE created_at BETWEEN %s AND %s 
                            AND state != 'pagado'
                            ORDER BY enum_order, created_at ASC
                        """, (today_start, today_end))
                        
                        all_orders = await cursor.fetchall()
                        
                        # Commit la transacción explícitamente
                        await conn.commit()
                        
                        # Procesar los resultados en memoria para evitar más consultas
                        orders_by_group = {}
                        
                        # Agrupar pedidos por enum_order
                        for order in all_orders:
                            enum_order = order['enum_order']
                            if enum_order not in orders_by_group:
                                orders_by_group[enum_order] = []
                            orders_by_group[enum_order].append(order)
                        
                        # Estadísticas
                        total_orders = len(orders_by_group)
                        pending_orders = 0
                        complete_orders = 0
                        total_sales = 0.0
                        
                        # Construir la lista de pedidos consolidados
                        orders_list = []
                        
                        for enum_order, orders_in_group in orders_by_group.items():
                            if not orders_in_group:
                                continue
                            
                            first_order = orders_in_group[0]
                            last_order = orders_in_group[-1]
                            
                            consolidated_order = {
                                "id": enum_order,
                                "table_id": first_order.get("address", ""),
                                "customer_name": first_order.get("user_name", ""),
                                "products": [],
                                "created_at": first_order["created_at"].isoformat() if isinstance(first_order["created_at"], datetime) else first_order["created_at"],
                                "updated_at": last_order["updated_at"].isoformat() if isinstance(last_order["updated_at"], datetime) else last_order["updated_at"],
                                "state": last_order.get("state", "pendiente")
                            }
                            
                            # Agregar productos al pedido consolidado
                            order_total = 0.0
                            for order in orders_in_group:
                                product_price = order.get("price", 0.0)
                                product_quantity = order.get("quantity", 0)
                                product_total = product_price * product_quantity
                                
                                product = {
                                    "name": order.get("product_name", ""),
                                    "quantity": product_quantity,
                                    "price": product_price,
                                    "observations": order.get("details", "")
                                }
                                consolidated_order["products"].append(product)
                                order_total += product_total
                            
                            # Actualizar estadísticas
                            if consolidated_order["state"] == "pendiente":
                                pending_orders += 1
                            elif consolidated_order["state"] == "completado":
                                complete_orders += 1
                                total_sales += order_total
                            
                            orders_list.append(consolidated_order)
                        
                        # Construir el resultado final
                        result = {
                            "stats": {
                                "total_orders": total_orders,
                                "pending_orders": pending_orders,
                                "complete_orders": complete_orders,
                                "total_sales": total_sales
                            },
                            "orders": orders_list
                        }
                        
                        return result
                        
                except Error as err:
                    # Revertir la transacción en caso de error
                    await conn.rollback()
                    logging.exception("Error al recuperar los pedidos del día: %s", err)
                    return {"stats": {"total_orders": 0, "pending_orders": 0, "complete_orders": 0, "total_sales": 0}, "orders": []}
        except Exception as e:
            logging.exception("Error general al recuperar los pedidos del día: %s", e)
            return {"stats": {"total_orders": 0, "pending_orders": 0, "complete_orders": 0, "total_sales": 0}, "orders": []}
    
    async def get_pending_orders_by_user_id(self, user_id: Optional[str]) -> Optional[Dict[str, Any]]:
        """
        Recupera el último pedido del último enum_order del día actual para un usuario específico.
        """
        try:
            if not user_id:
                return None

            pool = await self.db_pool.get_pool()
            
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    try:
                        # Obtener la fecha actual (solo la parte de la fecha, sin la hora)
                        today = datetime.now().date()
                        today_start = datetime.combine(today, datetime.min.time())
                        
                        # Get the latest order with the most recent enum_order
                        query = """
                            SELECT * FROM orders 
                            WHERE user_id = %s 
                            AND created_at >= %s
                            ORDER BY enum_order DESC, created_at DESC 
                            LIMIT 1
                        """
                        await cursor.execute(query, (user_id, today_start))
                        order = await cursor.fetchone()
                        
                        if order:
                            # Convert datetime objects to ISO format strings
                            if isinstance(order.get('created_at'), datetime):
                                order['created_at'] = order['created_at'].isoformat()
                            if isinstance(order.get('updated_at'), datetime):
                                order['updated_at'] = order['updated_at'].isoformat()
                            return order
                        
                        return None
                    except Error as err:
                        logging.exception("Error al recuperar pedido: %s", err)
                        return None
        except Exception as e:
            logging.exception("Error general al recuperar pedido: %s", e)
            return None
    
    async def get_all_orders(self) -> Dict[str, Any]:
        """
        Retorna todos los pedidos en la base de datos,
        agrupando en el campo 'products' todos los productos que comparten el mismo 'enum_order'.
        """
        try:
            pool = await self.db_pool.get_pool()
            
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    try:
                        # Consultar todos los enum_order distintos
                        await cursor.execute("SELECT DISTINCT enum_order FROM orders")
                        
                        distinct_orders = await cursor.fetchall()
                        result = {}
                        
                        # Procesar cada grupo de pedidos
                        for order_group in distinct_orders:
                            enum_order = order_group['enum_order']
                            
                            # Obtener todos los pedidos del grupo
                            await cursor.execute("""
                                SELECT * FROM orders 
                                WHERE enum_order = %s 
                                ORDER BY created_at ASC
                            """, (enum_order,))
                            
                            orders_in_group = await cursor.fetchall()
                            if not orders_in_group:
                                continue
                            
                            # Construir el pedido consolidado
                            first_order = orders_in_group[0]
                            last_order = orders_in_group[-1]
                            
                            consolidated_order = {
                                "id": enum_order,
                                "address": first_order["address"],
                                "customer_name": first_order.get("user_name", ""),
                                "enum_order": enum_order,
                                "products": [],
                                "created_at": first_order["created_at"].isoformat() if isinstance(first_order["created_at"], datetime) else first_order["created_at"],
                                "updated_at": last_order["updated_at"].isoformat() if isinstance(last_order["updated_at"], datetime) else last_order["updated_at"],
                                "state": last_order.get("state", "pendiente")
                            }
                            
                            # Agregar productos al pedido consolidado
                            for order in orders_in_group:
                                product = {
                                    "name": order.get("product_name", ""),
                                    "quantity": order.get("quantity", 0),
                                    "price": order.get("price", 0.0),
                                    "details": order.get("details", "")
                                }
                                consolidated_order["products"].append(product)
                            
                            result[enum_order] = consolidated_order
                        
                        return result
                        
                    except Error as err:
                        logging.exception("Error al recuperar todos los pedidos: %s", err)
                        return {}
        except Exception as e:
            logging.exception("Error general al recuperar todos los pedidos: %s", e)
            return {}

    async def delete_order(self, enum_order: str) -> bool:
        """
        Elimina un pedido y todos sus productos asociados de la base de datos.

        Args:
            enum_order: Identificador único del pedido

        Returns:
            bool: True si la eliminación fue exitosa, False en caso contrario
        """
        try:
            pool = await self.db_pool.get_pool()
            
            async with pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    try:
                        # Verificar si el pedido existe
                        await cursor.execute("SELECT COUNT(*) FROM orders WHERE enum_order = %s", (enum_order,))
                        result = await cursor.fetchone()
                        count = result[0]
                        
                        if count == 0:
                            logging.warning(f"Intentando eliminar un pedido que no existe: {enum_order}")
                            return False
                        
                        # Eliminar todos los productos asociados a este pedido
                        await cursor.execute("DELETE FROM orders WHERE enum_order = %s", (enum_order,))
                        await conn.commit()
                        
                        deleted_rows = cursor.rowcount
                        logging.info(f"Pedido eliminado: {enum_order}, {deleted_rows} productos eliminados")
                        
                        return deleted_rows > 0
                        
                    except Error as err:
                        logging.exception(f"Error al eliminar el pedido {enum_order}: {err}")
                        await conn.rollback()
                        return False
        except Exception as e:
            logging.exception(f"Error general al eliminar el pedido: {e}")
            return False

    async def update_order_product(self, enum_order: str, product_name: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Actualiza un producto específico dentro de un pedido existente.
        """
        try:
            pool = await self.db_pool.get_pool()
            
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    try:
                        # Verificar si existen pedidos con ese enum_order
                        await cursor.execute(
                            "SELECT * FROM orders WHERE enum_order = %s ORDER BY created_at ASC",
                            (enum_order,)
                        )
                        orders_in_group = await cursor.fetchall()
                        
                        if not orders_in_group:
                            logging.warning("No se encontraron pedidos con enum_order: %s", enum_order)
                            return None
                        
                        # Verificar el estado del pedido (solo permitir actualización en estados 'pendiente' o 'en preparación')
                        last_order = orders_in_group[-1]
                        current_state = last_order.get("state", "")
                        
                        if current_state not in ["pendiente", "en preparacion", "en preparación"]:
                            logging.warning(
                                "No se puede actualizar el pedido %s porque su estado actual es '%s'", 
                                enum_order, current_state
                            )
                            return None
                        
                        # Buscar el producto específico a actualizar
                        product_order = None
                        for order in orders_in_group:
                            if order.get("product_name") == product_name:
                                product_order = order
                                break
                        
                        if not product_order:
                            logging.warning(
                                "No se encontró el producto '%s' en el pedido %s", 
                                product_name, enum_order
                            )
                            return None
                        
                        # Preparar los campos a actualizar
                        update_fields = []
                        update_values = []
                        
                        # Actualizar la hora de actualización usando la hora colombiana
                        now = datetime.strptime(current_colombian_time(), '%Y-%m-%d %H:%M:%S')
                        update_fields.append("updated_at = %s")
                        update_values.append(now)
                        
                        # Actualizar cantidad si se proporciona
                        if "quantity" in updates:
                            update_fields.append("quantity = %s")
                            update_values.append(updates["quantity"])
                        
                        # Actualizar observaciones si se proporcionan
                        if "details" in updates:
                            update_fields.append("details = %s")
                            update_values.append(updates["details"])
                        
                        # Actualizar adición si se proporciona
                        if "adicion" in updates:
                            update_fields.append("adicion = %s")
                            update_values.append(updates["adicion"])
                        
                        # Actualizar precio si se proporciona
                        if "price" in updates:
                            update_fields.append("price = %s")
                            update_values.append(updates["price"])
                        
                        # Actualizar nombre del producto si se proporciona
                        if "new_product_name" in updates:
                            update_fields.append("product_name = %s")
                            update_values.append(updates["new_product_name"])
                        
                        # Cambiar el nombre del producto si se proporciona
                        if "new_product_id" in updates:
                            update_fields.append("product_id = %s")
                            update_values.append(updates["new_product_id"])
                        
                        # Si no hay campos para actualizar, retornar error
                        if not update_fields:
                            logging.warning("No se proporcionaron campos para actualizar en el pedido %s", enum_order)
                            return None
                        
                        # Construir la consulta de actualización
                        update_query = f"UPDATE orders SET {', '.join(update_fields)} WHERE id = %s"
                        update_values.append(product_order["id"])
                        
                        # Ejecutar la actualización
                        await cursor.execute(update_query, update_values)
                        await conn.commit()
                        
                        # Verificar si la actualización fue exitosa
                        if cursor.rowcount == 0:
                            logging.warning("No se pudo actualizar el producto %s en el pedido %s", product_name, enum_order)
                            return None
                        
                        # Obtener todos los pedidos actualizados
                        await cursor.execute(
                            "SELECT * FROM orders WHERE enum_order = %s ORDER BY created_at ASC",
                            (enum_order,)
                        )
                        updated_orders = await cursor.fetchall()
                        
                        # Construir el pedido consolidado actualizado
                        first_order = updated_orders[0]
                        last_order = updated_orders[-1]
                        
                        consolidated_order = {
                            "id": enum_order,
                            "table_id": first_order.get("address", ""),
                            "customer_name": first_order.get("user_name", ""),
                            "products": [],
                            "created_at": first_order["created_at"].isoformat() if isinstance(first_order["created_at"], datetime) else first_order["created_at"],
                            "updated_at": now.isoformat(),
                            "state": last_order.get("state", "pendiente")
                        }
                        
                        # Agregar productos al pedido consolidado
                        for order in updated_orders:
                            product = {
                                "name": order.get("product_name", ""),
                                "quantity": order.get("quantity", 0),
                                "price": order.get("price", 0.0),
                                "observations": order.get("details", ""),
                                "adicion": order.get("adicion", "")
                            }
                            consolidated_order["products"].append(product)
                        
                        logging.info("Producto %s actualizado en el pedido %s", product_name, enum_order)
                        return consolidated_order
                        
                    except Error as err:
                        await conn.rollback()
                        logging.exception("Error al actualizar el producto %s en el pedido %s: %s", product_name, enum_order, err)
                        return None
        except Exception as e:
            logging.exception("Error general al actualizar el producto: %s", e)
            return None

    async def update_order_status(self, enum_order_table: str, state: str, partition_key: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Actualiza el estado de un pedido en la base de datos MySQL.
        
        Args:
            enum_order_table: ID único del pedido a actualizar
            state: Nuevo estado del pedido (pendiente, en preparación, completado, etc.)
            partition_key: No se utiliza en MySQL, se mantiene por compatibilidad con otras implementaciones
            
        Returns:
            Diccionario con la información del pedido actualizado o None si no se encontró
        """
        try:
            pool = await self.db_pool.get_pool()
            
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    try:
                        # Actualizar el estado del pedido
                        update_query = """
                            UPDATE orders 
                            SET state = %s, 
                                updated_at = NOW() 
                            WHERE enum_order = %s
                        """
                        await cursor.execute(update_query, (state, enum_order_table))
                        await conn.commit()
                        
                        # Verificar si se actualizó algún registro
                        if cursor.rowcount == 0:
                            logging.warning(f"No se encontró el pedido {enum_order_table} o no se pudo actualizar.")
                            return None
                            
                        # Obtener el pedido actualizado
                        await cursor.execute("""
                            SELECT * FROM orders 
                            WHERE enum_order = %s
                            ORDER BY created_at ASC
                        """, (enum_order_table,))
                        
                        orders_in_group = await cursor.fetchall()
                        
                        if not orders_in_group:
                            return None
                            
                        # Construir el pedido consolidado
                        first_order = orders_in_group[0]
                        last_order = orders_in_group[-1]
                        
                        consolidated_order = {
                            "id": enum_order_table,
                            "address": first_order.get("address", ""),
                            "customer_name": first_order.get("user_name", ""),
                            "enum_order": enum_order_table,
                            "products": [],
                            "created_at": first_order["created_at"].isoformat() if isinstance(first_order["created_at"], datetime) else first_order["created_at"],
                            "updated_at": last_order["updated_at"].isoformat() if isinstance(last_order["updated_at"], datetime) else last_order["updated_at"],
                            "state": state
                        }
                        
                        # Agregar productos al pedido consolidado
                        for order in orders_in_group:
                            product = {
                                "name": order.get("product_name", ""),
                                "quantity": order.get("quantity", 0),
                                "price": order.get("price", 0.0),
                                "details": order.get("details", "")
                            }
                            consolidated_order["products"].append(product)
                        
                        return consolidated_order
                        
                    except Error as err:
                        await conn.rollback()
                        logging.exception(f"Error al actualizar el estado del pedido {enum_order_table}: {err}")
                        return None
        except Exception as e:
            logging.exception(f"Error general al actualizar el estado del pedido: {e}")
            return None