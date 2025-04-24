from typing import Optional, Literal, List, Any, Union, TypedDict
from pydantic import SecretStr

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage, ToolMessage, AnyMessage
from langgraph.graph import StateGraph, START, MessagesState, END
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.prebuilt import ToolNode

from core.config import settings
from inference.graphs.mysql_saver import MySQLSaver
from core.utils import current_colombian_time
import pdb
from IPython.display import Image, display
from langchain_core.runnables.graph import CurveStyle, MermaidDrawMethod, NodeStyles
from datetime import datetime
from inference.tools.restaurant_tools import get_menu_tool,confirm_order_tool,get_order_status_tool,send_menu_pdf_tool, update_order_tool, send_location_tool
import json
import asyncio
from langchain_openai import ChatOpenAI
import sys
import asyncio

# Si estamos en Python 3.11 o superior, parcheamos create_task para ignorar el argumento 'context'
if sys.version_info >= (3, 11):
    original_create_task = asyncio.create_task

    def create_task_patch(coro, *, context=None, name=None):
        # Ignoramos 'context' si se pasa, pero pasamos 'name'
        return original_create_task(coro, name=name)

    asyncio.create_task = create_task_patch

######################################################
# 1) Estado del Bot (hereda messages)
######################################################
class RestaurantStateDict(TypedDict):
    thread_id: Optional[str]
    restaurant_name: Optional[str]
    user_id: Optional[str]

class RestaurantState(MessagesState):
    thread_id: Optional[str] = None
    restaurant_name: Optional[str] = None
    user_id: Optional[str] = None
        # - consultar_menu:

        #     Utiliza esta herramienta para mostrar el menú actualizado del restaurante.
        #     Informa al cliente que la consulta puede tardar unos segundos.

SYSTEM_PROMPT = """
Fecha y Hora Actual: {{fecha-hora}}

Eres un asistente de IA especializado en la atención a clientes para nuestro restaurante {{restaurant_name}}. Tu misión es guiar a los comensales en el proceso de selección y confirmación de cada producto o plato de su pedido. Responde de manera amigable, utilizando emojis de restaurante ocasionalmente, y siempre indaga los datos necesarios para completar la orden.

*Información del Cliente:*
Nombre: {{user_name}}
Dirección: {{user_address}}
user_id: {{user_id}}

---

### Información Adicional
- Nuestro restaurante es **pet friendly**. 🐾
- Los domicilios se realizan desde la clínica de oncólogos, la zona industrial hasta Pro gel.

### Instrucciones de Saludo

Cuando el cliente saluda o es el primer mensaje de la conversación, SIEMPRE responde presentándote como el chatbot de Juanchito Plaza, con un mensaje similar a:

- Si el nombre del cliente no está disponible en la información del cliente, omite la parte de "¡Hola user_name!" y simplemente responde con "¡Hola! 👋 ..."

"¡Hola{{user_name_saludo}}! 👋 Soy el chatbot de Juanchito Plaza 👨🏽‍🍳. Estoy aquí para ayudarte con la toma de tu pedido. Tenemos servicio de domicilio disponible exclusivamente en la zona industrial, y solo recibimos pedidos **antes de las 11 de la mañana**. ¿En qué puedo ayudarte hoy? ¿Deseas ver nuestro menú o realizar un pedido?"

IMPORTANTE: Responde SIEMPRE en español, sin importar el idioma que use el cliente.

---

### Herramientas Disponibles

1. *get_menu_tool*  
   - *Función:* Obtener el menú actualizado de productos disponibles.  
   - *Uso:* Utiliza esta herramienta para verificar precios y disponibilidad.

2. *confirm_order_tool*  
   - *Función:* Registra y actualiza el documento del pedido en MySQL cada vez que se confirme un producto o plato.  
   - *Procedimiento:*  
     - Antes de usar esta herramienta, llama a *get_menu_tool* para obtener en tiempo real:
       - La disponibilidad del producto.
       - El id y nombre del producto.
       - El precio unitario.
     - *Datos requeridos para confirmar un producto:*  
       - *product_id:* ID obtenido de get_menu_tool.  
       - *product_name:* Nombre obtenido de get_menu_tool.  
       - *quantity:* Cantidad a comprar (preguntar al cliente).  
       - *details:* Detalles específicos del pedido (añadir si el cliente los menciona, o dejar en blanco).  
       - *address:* Dirección de entrega (preguntar al cliente).  
       - *user_name:* Nombre del cliente (preguntar al cliente).  
       - *Si el cliente pide un churrasco, pregunta qué término lo quiere (3/4 o bien asado).*

   - *Consideraciones adicionales:*  
     - **Al confirmar el pedido, menciona siempre cuántos platos del producto ha elegido el cliente**. Ejemplo: "Perfecto, entonces serían *2 platos de Bandeja Paisa* 🍛".
     - **El agente calculará el total del pedido, sumando el costo de los productos y el costo fijo de $1000 por el domicilio.**  
     - Luego, pregunta al cliente: **¿Confirmas este pedido?**

3. *send_location_tool*  
   - *Función:* Envía la ubicación del restaurante al cliente.  
   - *Uso:* Utiliza esta herramienta cuando el cliente solicite la ubicación del restaurante.

   - *Datos requeridos para enviar la ubicación:*
       - *user_id:* ID del usuario (número de teléfono) al que se enviará la ubicación.

   - *Consideraciones adicionales:*  
     - La ubicación enviada será siempre la misma, con coordenadas fijas.

4. *get_order_status_tool*  
   - *Función:* Consulta el estado del pedido de un cliente.  
   - *Uso:*  
     - Llama a esta herramienta cuando el cliente pregunte por el estado de su pedido o su progreso.  
     - Presenta la información de forma clara y amigable.

5. *send_menu_pdf_tool*  
   - *Función:* Envía las fotos del menú completo al cliente.  
   - *Uso:*  
     - Llama a esta herramienta cuando el cliente solicite explícitamente ver el menú.  
     - Informa al cliente que ha recibido el menú y procede a tomar su pedido.

6. *update_order_tool*  
   - *Función:* Actualiza un producto específico dentro de un pedido existente.  
   - *Uso:*  
     - Utiliza esta herramienta cuando el cliente desee modificar un producto de su pedido actual.  
     - **DEBES** usar esta herramienta cuando el cliente menciona observaciones o modificaciones sin especificar un producto en la conversación actual, lo que indica que quiere modificar un pedido existente en la base de datos.
     - Solo funciona con pedidos en estado 'pendiente' o 'en preparación'.  
   - *Datos requeridos para actualizar un producto:*  
     - *enum_order:* Identificador del pedido a actualizar (obtenido de get_order_status_tool).  
     - *product_name:* Nombre del producto a actualizar.  
     - *user_id:* ID del cliente (ya incluido automáticamente).  
     - *quantity:* (Opcional) Nueva cantidad del producto.  
     - *details:* (Opcional) Nuevas observaciones para el producto.  
     - *new_product_name:* (Opcional) Nuevo nombre de producto (para cambiar el producto).  
     - *new_product_id:* (Opcional) Nuevo ID de producto (para cambiar el producto).  
     - *price:* (Opcional) Nuevo precio.  
   - *Procedimiento:*  
     - Primero, verifica el estado del pedido con get_order_status_tool.  
     - Si el cliente quiere cambiar el producto por otro diferente, usa get_menu_tool para obtener la información del nuevo producto.  
     - Confirma todos los cambios con el cliente antes de ejecutar la actualización.  
     - Informa al cliente sobre el resultado de la actualización.

---

### Flujo de Conversación y Proceso de Pedido

1. *Saludo y Cortesía:*  
   - Inicia cada conversación con un saludo amigable, profesional y cálido.
   - Si el cliente envía un saludo (ej: "hola", "buenos días", etc.), responde presentándote como el chatbot de Juanchito Plaza y menciona que solo tienen domicilios en la zona industrial.
   - Luego ofrece ayuda para tomar el pedido o enviar el menú:
     "¡Hola! 👨🏽‍🍳 ¿En qué puedo ayudarte hoy? Puedo ayudarte a tomar tu pedido o enviarte nuestro menú completo. ¿Qué prefieres?"

2. *Verificación de Órdenes Pendientes:*  
   - Si el cliente no tiene órdenes pendientes (verifica con *get_order_status_tool*), muestra el menú y ayuda a iniciar un pedido.  
   - Si hay órdenes pendientes, informa al cliente sobre su estado y pregunta si desea agregar más productos.

3. *Proceso para Confirmar un Pedido:*  
   - Antes de confirmar cualquier producto, *verifica la disponibilidad* usando *get_menu_tool*.  
   - Una vez confirmada la disponibilidad y seleccionado el producto, confirma la elección con el cliente mencionando cuántos platos ordenó y el precio total.
   - Luego pregunta: **¿Confirmas este pedido?**  
   - Si el cliente tiene una orden en curso y desea agregar productos, asegúrate de:
     - Usar la misma dirección y nombre del cliente (a menos que la orden esté completada).  
     - No agregar productos si el pedido está "en entrega"; en ese caso, sugiere iniciar un nuevo pedido.
   - Si el cliente pide ver el menú, utiliza *send_menu_pdf_tool* y luego continúa el proceso de toma de pedido.

4. *Claridad y Asistencia:*  
   - Responde de forma clara, precisa y amable.  
   - Si ocurre algún error o la herramienta falla, informa al cliente de manera comprensiva y brinda alternativas.  
   - Siempre ofrece ayuda adicional preguntando si el cliente desea agregar bebidas u otros productos.

---

### Notas Adicionales

- *Consistencia:* Asegúrate de usar términos y nombres de herramientas de forma consistente (por ejemplo, "confirm_order_tool" en lugar de "confirmar_pedido").  
- *Interacción Amigable:* Aprovecha el uso de emojis y un lenguaje cercano para mejorar la experiencia del cliente.
"""

######################################################
# 2) main_agent_node (asíncrono) + tools usage
######################################################
async def main_agent_node(state: RestaurantState) -> RestaurantState:
    """
    1) Inyecta system prompt
    2) Llama repetidamente al LLM (con .bind_tools([...]))
       Si el LLM produce tool_calls (ej: name="search_tool"), se ejecutan
       y se añade un AIMessage con los resultados. 
       Se repite hasta que no haya más tool_calls.
    3) Devuelve el estado final
    """
    # Preparar la conversacion
    max_messages = 10 
    # Obtener información del usuario si está disponible en el estado
    user_info = ""
    user_id = state["user_id"]
        
        # Importar el gestor de usuarios
    from core.mysql_user_manager import MySQLUserManager
    user_manager = MySQLUserManager()
    
    # Obtener información del usuario
    user_data = await user_manager.get_user(user_id)
    print(f"Información del Usuario: {user_data}")

    # Extraer individualmente los valores
    user_name = user_data.get('name', 'No disponible') if user_data else 'No disponible'
    user_address = user_data.get('address', 'No disponible') if user_data else 'No disponible'
    user_id_str = str(user_id)

    # Reemplazar los campos individuales en el SYSTEM_PROMPT
    system_prompt_with_user = (
        SYSTEM_PROMPT
        .replace("{{fecha-hora}}", current_colombian_time())
        .replace("{{user_name}}", user_name)
        .replace("{{user_address}}", user_address)
        .replace("{{user_id}}", user_id_str)
    )

    # Crear el mensaje de sistema con el prompt personalizado
    system_msg = SystemMessage(content=system_prompt_with_user)
    new_messages = [system_msg] + state["messages"][-max_messages:]

    # 1) Preparamos el LLM que tenga "search_tool" enlazado
    llm_raw = ChatOpenAI(api_key=SecretStr(settings.openai_api_key),
                        model=settings.openai_model)
    # bind_tools => el LLM sabe formatear la tool call como 
    # {"tool_calls": [{"name": "search_tool", "args": "..."}]}
    # In main_agent_node function
    llm_with_tools = llm_raw.bind_tools(
    tools=[confirm_order_tool, get_menu_tool, get_order_status_tool, send_menu_pdf_tool, update_order_tool, send_location_tool]
        )
    # 2) Usar ainvoke en lugar de invoke para un procesamiento verdaderamente asíncrono
    response_msg = await llm_with_tools.ainvoke(new_messages)
    
    # Verificar y procesar llamadas a herramientas
    tool_calls_verified = []
    if isinstance(response_msg, AIMessage) and hasattr(response_msg, 'tool_calls') and response_msg.tool_calls:
        for tool_call in response_msg.tool_calls:

            if tool_call["name"] == "get_menu_tool":
                print(f"\033[32m Tool Call: {tool_call['name']}\033[0m")

                arguments = tool_call["args"]
                # Ensure restaurant_name is always a valid value, not user input
                if "restaurant_name" in arguments and not (arguments["restaurant_name"] == "go_papa" or arguments["restaurant_name"] is None):
                    # If restaurant_name is not valid, use the default
                    arguments["restaurant_name"] = state.get("restaurant_name") if state.get("restaurant_name") else "go_papa"
                else:
                    # If restaurant_name is not in arguments, add it
                    arguments["restaurant_name"] = state.get("restaurant_name") if state.get("restaurant_name") else "go_papa"
                tool_call["args"] = arguments
                tool_calls_verified.append(tool_call)

            elif tool_call["name"] == "confirm_order_tool":
                print(f"\033[32m Tool Call: {tool_call['name']} \033[0m")

                arguments = tool_call["args"]
                arguments["user_id"] = state.get("user_id")
                
                # Asegurarse de que details esté presente en los argumentos incluso si es None
                if "details" not in arguments:
                    arguments["details"] = None
                
                tool_call["args"] = arguments
                tool_calls_verified.append(tool_call)

            elif tool_call["name"] == "get_order_status_tool":
                print(f"\033[32m Tool Call: {tool_call['name']} \033[0m")

                arguments = tool_call["args"]
                arguments["user_id"] = state.get("user_id")
                tool_call["args"] = arguments
                tool_calls_verified.append(tool_call)

            elif tool_call["name"] == "update_order_tool":
                print(f"\033[32m Tool Call: {tool_call['name']} \033[0m")

                arguments = tool_call["args"]
                # Asegurarse de que user_id esté presente en los argumentos
                if "user_id" not in arguments or not arguments["user_id"]:
                    arguments["user_id"] = state.get("user_id")
                # Asegurarse de que restaurant_id esté presente en los argumentos
                tool_call["args"] = arguments
                tool_calls_verified.append(tool_call)

            else:
                tool_calls_verified.append(tool_call)

        response_msg.tool_calls = tool_calls_verified 
        
    new_messages.append(response_msg)

    # 3) Retornar el estado final
    return {
        "messages": new_messages
    }

def route_after_agent(
        state: RestaurantState,
    ) -> Literal[
        "AgentNode",
        "ToolsNode",
        "__end__"]: 
        
    """Direcciona el siguiente nodo tras la acción del agente.

    Esta función determina el siguiente paso en el proceso de investigación basándose en el
    último mensaje en el estado. Maneja tres escenarios principales:

    
    1. Scraper en Ecommerce de Bata
    """
    last_message = state["messages"][-1]

    # "If for some reason the last message is not an AIMessage (due to a bug or unexpected behavior elsewhere in the code),
    # it ensures the system doesn't crash but instead tries to recover by calling the agent model again.
    if not isinstance(last_message, AIMessage):
        return "AgentNode"
    # If the "Into" tool was called, then the model provided its extraction output. Reflect on the result
    
    if last_message.tool_calls:
            return "ToolsNode"
        # if last_message.tool_calls and last_message.tool_calls[0]["name"] == "scrape_tool":
        #     return "WebScraperNode"
        # The last message is a tool call that is not "Info" (extraction output)
    else:
        return "__end__"

######################################################
# 3) Construir el Graph + checkpoint
######################################################
class RestaurantChatAgent:
    def __init__(self):
        # 1) Creamos un StateGraph con RestaurantState
        graph = StateGraph(state_schema=RestaurantState)

        # 2) Añadimos un solo nodo (main_agent_node)
        graph.add_node("AgentNode", main_agent_node)
        # Usamos nuestro nodo personalizado en lugar de ToolNode
        graph.add_node("ToolsNode", parallel_tools_node)

        # 3)
        graph.add_edge(START, "AgentNode")
        graph.add_conditional_edges("AgentNode", route_after_agent)
        graph.add_edge("ToolsNode", "AgentNode")
        # graph.add_edge("AgentNode", END)

        # 5) Compilar
        self.app = graph.compile() 

        # (Opcional) Generar imagen del grafo
        # image_data = self.app.get_graph().draw_mermaid_png(draw_method=MermaidDrawMethod.API)
        # image = Image(image_data)
        # with open("graph_image.png", "wb") as f:
        #     f.write(image.data)

    async def invoke_flow(
    self,
    user_input: str,  # Ahora recibimos el input directo
    user_id: str,
    ) -> tuple[RestaurantState, str]:
        # 1. Recuperar historial previo
        mysql_saver = MySQLSaver()
        history_messages = await mysql_saver.get_conversation_history(
            user_id
        )
        # 2. Construir lista de mensajes completa
        new_human_message = HumanMessage(
            content=user_input,
            response_metadata={"timestamp": current_colombian_time()}
        )
        all_messages = history_messages + [new_human_message]
        # 3. Ejecutar el flujo
        new_state = await self.app.ainvoke(
            {
                "messages": all_messages,
                "user_id": user_id,
            },
            config={"configurable": {"user_id": user_id}},
        )

        # 4. Extraer y guardar solo el último intercambio
        new_messages = new_state["messages"][len(all_messages):]
        new_ai_messages = [msg for msg in new_messages if isinstance(msg, AIMessage)]
        if not new_ai_messages:
            raise ValueError("No se generó respuesta de AI")
        ai_response = new_ai_messages[-1]

        doc_id = await mysql_saver.save_conversation(
            user_message=new_human_message,
            ai_message=ai_response,
            user_id=user_id
        )
        
        # Return properly typed RestaurantState and string ID
        return RestaurantState(messages=new_state["messages"])

# Nodo de herramientas personalizado que usa asyncio.gather para el paralelismo
async def parallel_tools_node(state: RestaurantState) -> RestaurantState:
    """
    Ejecuta las herramientas en el último mensaje AIMessage de forma paralela 
    usando asyncio.gather y añade los resultados como ToolMessages.
    """
    # Obtener el último mensaje, que debe ser un AIMessage con tool_calls
    last_message = state["messages"][-1]
    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        return state
    
    new_messages = list(state["messages"])
    tool_calls = last_message.tool_calls
    
    # Configurar las tareas para todas las herramientas llamadas
    tasks = []
    tool_call_indices = []
    
    for i, tool_call in enumerate(tool_calls):
        tool_name = tool_call["name"]
        tool_args = tool_call["args"].copy()  # Hacer una copia para no modificar el original
        
        # Seleccionar la herramienta adecuada
        if tool_name == "get_menu_tool":
            # Eliminar restaurant_name si existe en los argumentos
            if "restaurant_name" in tool_args:
                del tool_args["restaurant_name"]
            tasks.append(get_menu_tool(**tool_args))
            tool_call_indices.append(i)
        elif tool_name == "confirm_order_tool":
            tasks.append(confirm_order_tool(**tool_args))
            tool_call_indices.append(i)
        elif tool_name == "get_order_status_tool":
            tasks.append(get_order_status_tool(**tool_args))
            tool_call_indices.append(i)
        elif tool_name == "send_menu_pdf_tool":
            tasks.append(send_menu_pdf_tool(**tool_args))
            tool_call_indices.append(i)
        elif tool_name == "update_order_tool":
            tasks.append(update_order_tool(**tool_args))
            tool_call_indices.append(i)
        elif tool_name == "send_location_tool":
            tasks.append(send_location_tool(**tool_args))
            tool_call_indices.append(i)
    
    # Ejecutar todas las herramientas en paralelo
    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Añadir los resultados como ToolMessages
        for i, result in enumerate(results):
            tool_call_index = tool_call_indices[i]
            tool_call = tool_calls[tool_call_index]
            
            if isinstance(result, Exception):
                # Manejar errores
                tool_message = ToolMessage(
                    content=f"Error ejecutando herramienta {tool_call['name']}: {str(result)}",
                    tool_call_id=tool_call.get("id", ""),
                    name=tool_call["name"]
                )
            else:
                # Convertir resultado a string si no lo es
                result_str = json.dumps(result) if not isinstance(result, str) else result
                tool_message = ToolMessage(
                    content=result_str,
                    tool_call_id=tool_call.get("id", ""),
                    name=tool_call["name"]
                )
            
            new_messages.append(tool_message)
    
    return {
        "messages": new_messages,
        "user_id": state["user_id"]
    }

        