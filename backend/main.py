# app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import azure.functions as func
import os

from api.chat_agent import chat_agent_router
from api.orders import orders_router
from api.inventory_router import inventory_router

from fastapi.staticfiles import StaticFiles
from starlette.responses import Response

# Configuración de la aplicación FastAPI sin root_path
app = FastAPI(title="TARS Agents Graphs")

@app.middleware("http")
async def no_cache_middleware(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# Configuración específica de CORS para permitir credenciales
allowed_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registrar routers
app.include_router(chat_agent_router, prefix="/agent/chat", tags=["RestaurantsAgents"])
app.include_router(inventory_router, prefix="/inventory/stock", tags=["StockRestaurants"])
app.include_router(orders_router, prefix="/orders", tags=["Orders"])
#app.include_router(auth_router, prefix="/auth", tags=["Auth"])


# Función principal para Azure Functions
def main(req: func.HttpRequest) -> func.HttpResponse:
    """Handle the HTTP request using the ASGI middleware."""
    return func.AsgiMiddleware(app).handle(req)
