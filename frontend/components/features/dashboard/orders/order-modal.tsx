"use client"

import { useState, useEffect } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Separator } from "@/components/ui/separator"
import { Clock, User, CalendarDays, RefreshCw, AlertCircle, Loader2, Trash2, MapPin } from "lucide-react"
import { 
  Order, 
  OrderState, 
  OrderStatusCallback, 
  OrderDeleteCallback 
} from "@/lib/types"
import { formatCOP, formatDateLong } from "@/lib/utils/format"

interface OrderModalProps {
  order: Order | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onStatusUpdate: OrderStatusCallback
  onDeleteOrder: OrderDeleteCallback
  isUpdating?: boolean
  orderIndex?: number // Nuevo prop para recibir el índice del pedido
}

/**
 * Modal para mostrar detalles y gestionar un pedido
 */
export function OrderModal({ 
  order, 
  open, 
  onOpenChange, 
  onStatusUpdate, 
  onDeleteOrder, 
  isUpdating = false,
  orderIndex // Recibir el índice del pedido
}: OrderModalProps) {
  if (!order) return null

  // Crear un estado local para el estado del pedido
  const [currentOrderState, setCurrentOrderState] = useState(order.state);
  
  // Actualizar el estado local cuando cambie el pedido externo
  useEffect(() => {
    if (order) {
      setCurrentOrderState(order.state);
    }
  }, [order, order.state]);

  const statusColors = {
    [OrderState.PENDING]: "bg-yellow-500",
    [OrderState.PREPARING]: "bg-blue-500",
    [OrderState.COMPLETED]: "bg-green-500",
  }
  
  const handleStatusChange = async (value: string) => {
    try {
      // Actualizar inmediatamente el estado local para actualizar la UI
      setCurrentOrderState(value);
      
      // Llamar a la función para actualizar en el backend
      await onStatusUpdate(order.id, value);
    } catch (err) {
      console.error("Error al actualizar estado:", err);
      // Revertir al estado original en caso de error
      setCurrentOrderState(order.state);
    }
  }

  // Calcular el total del pedido
  const orderTotal = order.products.reduce((total, product) => {
    return total + product.price * product.quantity
  }, 0)

  // Determinar el número a mostrar (usar el índice si está disponible, o mostrar el ID como fallback)
  const displayNumber = typeof orderIndex === 'number' ? orderIndex + 1 : order.id;

  return (
    <Dialog open={open} onOpenChange={(newOpen) => !isUpdating && onOpenChange(newOpen)}>
      <DialogContent className="w-[95%] max-w-[550px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
            <DialogTitle className="text-xl">Pedido #{displayNumber}</DialogTitle>
            <Badge className={`${statusColors[currentOrderState as OrderState] || "bg-gray-500"} whitespace-nowrap`}>
              {currentOrderState.charAt(0).toUpperCase() + currentOrderState.slice(1)}
            </Badge>
          </div>
          <DialogDescription>
            Detalles y gestión del pedido
          </DialogDescription>
        </DialogHeader>

        {/* Información del cliente y pedido */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
          <div className="flex items-start gap-2">
            <User className="h-4 w-4 mt-1 text-muted-foreground" />
            <div>
              <p className="text-sm font-medium">Cliente</p>
              <p className="text-sm text-muted-foreground">{order.customer_name}</p>
            </div>
          </div>
          <div className="flex items-start gap-2">
            <MapPin className="h-4 w-4 mt-1 text-muted-foreground" />
            <div>
              <p className="text-sm font-medium">Dirección</p>
              <p className="text-sm text-muted-foreground">{order.table_id}</p>
            </div>
          </div>
          <div className="flex items-start gap-2">
            <CalendarDays className="h-4 w-4 mt-1 text-muted-foreground" />
            <div>
              <p className="text-sm font-medium">Fecha de creación</p>
              <p className="text-sm text-muted-foreground">{formatDateLong(order.created_at)}</p>
            </div>
          </div>
          <div className="flex items-start gap-2">
            <Clock className="h-4 w-4 mt-1 text-muted-foreground" />
            <div>
              <p className="text-sm font-medium">Última actualización</p>
              <p className="text-sm text-muted-foreground">{formatDateLong(order.updated_at)}</p>
            </div>
          </div>
        </div>

        {/* Estado del pedido */}
        <div className="mb-4">
          <p className="text-sm font-medium mb-2">Estado del pedido</p>
          <Select 
            value={currentOrderState} 
            onValueChange={handleStatusChange}
            disabled={isUpdating}
          >
            <SelectTrigger className="w-full">
              <SelectValue placeholder="Seleccionar estado" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={OrderState.PENDING}>Pendiente</SelectItem>
              <SelectItem value={OrderState.PREPARING}>En preparación</SelectItem>
              <SelectItem value={OrderState.COMPLETED}>Completado</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Lista de productos */}
        <div>
          <p className="text-sm font-medium mb-2">Productos</p>
          <div className="space-y-2">
            {order.products.map((product, index) => (
              <Card key={index}>
                <CardContent className="p-3">
                  <div className="flex justify-between items-start">
                    <div>
                      <p className="font-medium">{product.name}</p>
                      <p className="text-sm text-muted-foreground">
                        Cantidad: {product.quantity}
                      </p>
                      {product.observations && (
                        <p className="text-sm text-muted-foreground">
                          Observaciones: {product.observations}
                        </p>
                      )}
                    </div>
                    <p className="font-medium">${product.price.toLocaleString()}</p>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>

        <Separator className="my-4" />

        {/* Total del pedido */}
        <div className="flex justify-between items-center font-medium">
          <span>Total</span>
          <span>${orderTotal.toLocaleString()}</span>
        </div>

        <DialogFooter className="flex flex-col-reverse sm:flex-row gap-2 sm:gap-0">
          <Button 
            variant="outline" 
            onClick={() => onOpenChange(false)}
            disabled={isUpdating}
          >
            Cerrar
          </Button>
          <Button 
            variant="destructive" 
            onClick={() => onDeleteOrder(order.id)}
            disabled={isUpdating}
            className="sm:mr-auto"
          >
            {isUpdating ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Eliminando...
              </>
            ) : (
              <>
                <Trash2 className="mr-2 h-4 w-4" />
                Eliminar Pedido
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}