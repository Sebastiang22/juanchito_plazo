import sys
import os
from pathlib import Path

# Añadir el directorio src al PYTHONPATH
script_dir = Path(__file__).parent
src_dir = script_dir.parent
sys.path.insert(0, str(src_dir))

# Ahora las importaciones funcionarán
import logging
from mysql.connector import Error
import mysql.connector

from core.config import settings

def add_menu_items():
    """Add menu items to the inventory table in MySQL database."""
    connection = None
    try:
        connection = mysql.connector.connect(
            host=settings.db_host,
            user=settings.db_user,
            password=settings.db_password,
            database=settings.db_database
        )
        print("MySQL Database connection successful")
        
        cursor = connection.cursor()
        try:
            # Clear existing menu items (optional)
            cursor.execute("DELETE FROM inventory")
            print("Cleared existing inventory items")
            
            # Menu ejecutivo items
            ejecutivo_items = [
                {
                    "name": "SOBREBARRIGA SUDADA",
                    "quantity": 100,
                    "unit": "plato",
                    "price": 20000,
                    "descripcion": "CERSO Y POLLO EN TROZOS CON VEGETALES SALTEADOS, ARROZ BLANCO, JUGO, ENSALADA, SOPA CAMPESINA, TOSTON",
                    "tipo_producto": "ejecutivo"
                },
                {
                    "name": "CORDON BLEU",
                    "quantity": 100,
                    "unit": "plato",
                    "price": 19000,
                    "descripcion": "FILETE DE PECGUGA EN ROLLO RELLENO DE JAMON Y QUESO, ARROZ, ENSALADA, JUGO, PAPA Y YUCA, SOPASE SANCOCHO",
                    "tipo_producto": "ejecutivo"
                },
                {
                    "name": "BANDEJA TÍPICA CON CHICHARRÓN",
                    "quantity": 100,
                    "unit": "plato",
                    "price": 28000,
                    "descripcion": "PORCION DE FRIJOL, CHICHARRON, TAJADA, HUEVO FRITO, ARROZ BLANCO, ENSALADA, JUGO",
                    "tipo_producto": "ejecutivo"
                },
                {
                    "name": "MENU VEGETARIANO",
                    "quantity": 100,
                    "unit": "plato",
                    "price": 17000,
                    "descripcion": "FRIJOLES, HUEVO, SOPA O CREMA DEL DIA, JUGO, ENSALADA NATURAL, ACOMPANANTE",
                    "tipo_producto": "ejecutivo"
                },
                {
                    "name": "MENU SUPER PRECIO",
                    "quantity": 100,
                    "unit": "plato",
                    "price": 16000,
                    "descripcion": "90 GRS DE POLLO A LA PLANCHA CREMA O SOPA DEL DIA, JUGO, ARROZ, ENSALADA, ACOMPAÑANTE",
                    "tipo_producto": "ejecutivo"
                }
            ]
            
            # Menu a la carta items
            carta_items = [
                {
                    "name": "CHURRASCO + CHORIZO",
                    "quantity": 100,
                    "unit": "plato",
                    "price": 42000,
                    "descripcion": "300 GRS + CHORIZO, SOPA O CREMA DEL DIA, ARROZ BLANCO, JUGO, ENSALADA NATURAL",
                    "tipo_producto": "carta"
                },
                {
                    "name": "SALMON CHILENO",
                    "quantity": 100,
                    "unit": "plato",
                    "price": 42000,
                    "descripcion": "200 GRS, ENSALADA NATURAL, JUGO, ARROZ BLANCO, SOPA O CREMA DEL DIA, TOSTON",
                    "tipo_producto": "carta"
                },
                {
                    "name": "PUNTA DE ANCA DE CERDO",
                    "quantity": 100,
                    "unit": "plato",
                    "price": 30000,
                    "descripcion": "300 GRS, ARROZ, ENSALDA NATURAL, JUGO, TOSTON, SOPA O CREMA",
                    "tipo_producto": "carta"
                },
                {
                    "name": "MOJARRA FRITA",
                    "quantity": 100,
                    "unit": "plato",
                    "price": 32000,
                    "descripcion": "300 GRS, ARROZ BLANCO, SOPA O CREMA DEL DIA, JUHO, ARROZ, ENSALADA DEL DIA",
                    "tipo_producto": "carta"
                },
                {
                    "name": "FILETE DE TRUCHA",
                    "quantity": 100,
                    "unit": "plato",
                    "price": 20000,
                    "descripcion": "ENSALADA NATURAL, ARROZ, SOPA O CREMA DEL DIA, JUGO, ACOMPAÑANTE",
                    "tipo_producto": "carta"
                }
            ]
            
            # Combine all items
            all_items = ejecutivo_items + carta_items
            
            # Insert items into inventory table
            for item in all_items:
                cursor.execute("""
                INSERT INTO inventory (name, quantity, unit, price, descripcion, tipo_producto)
                VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    item["name"],
                    item["quantity"],
                    item["unit"],
                    item["price"],
                    item["descripcion"],
                    item["tipo_producto"]
                ))
            
            connection.commit()
            print(f"Added {len(all_items)} menu items to inventory")
            
        except Error as err:
            print(f"Error adding menu items: {err}")
        finally:
            cursor.close()
            
    except Error as err:
        print(f"Error connecting to MySQL: {err}")
    finally:
        if connection and connection.is_connected():
            connection.close()
            print("MySQL connection closed")


if __name__ == "__main__":
    add_menu_items()