"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from "@/components/ui/dialog";
import { useToast } from "@/components/ui/use-toast";


interface MenuImageModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function MenuImageModal({ open, onOpenChange }: MenuImageModalProps) {
  const { toast } = useToast();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [menuData, setMenuData] = useState<any>(null);

  // Manejar la selección de archivo
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] || null;
    setSelectedFile(file);
    setMenuData(null); // Limpiar datos previos

    // Crear URL de vista previa
    if (file) {
      const fileUrl = URL.createObjectURL(file);
      setPreviewUrl(fileUrl);
    } else {
      setPreviewUrl(null);
    }
  };

  // Limpiar al cerrar
  const handleClose = () => {
    setSelectedFile(null);
    setPreviewUrl(null);
    setMenuData(null);
    onOpenChange(false);
  };

  // Extraer información del menú desde la imagen
  const handleUpload = async () => {
    if (!selectedFile) {
      toast({
        variant: "destructive",
        title: "Error",
        description: "Por favor selecciona una imagen primero",
      });
      return;
    }

    try {
      setIsUploading(true);
      
      // Convertir la imagen a hexadecimal
      const arrayBuffer = await selectedFile.arrayBuffer();
      const imageHex = Array.from(new Uint8Array(arrayBuffer))
        .map(b => b.toString(16).padStart(2, '0'))
        .join('');

      const response = await fetch('http://localhost:7071/menu/extract', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ image_hex: imageHex }),
      });

      if (!response.ok) {
        throw new Error(`Error: ${response.status}`);
      }

      const result = await response.json();
      
      toast({
        title: "Éxito",
        description: "El menú ha sido actualizado correctamente",
      });

      // Cerrar el modal después de una actualización exitosa
      handleClose();
    } catch (error) {
      console.error('Error al procesar la imagen:', error);
      toast({
        variant: "destructive",
        title: "Error",
        description: error instanceof Error ? error.message : "No se pudo actualizar el menú",
      });
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Actualizar menú</DialogTitle>
          <DialogDescription>
            Selecciona una imagen del menú para actualizar la carta.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          <div className="flex flex-col gap-2">
            <label htmlFor="menu-image" className="text-sm font-medium">
              Imagen del menú
            </label>
            <input
              id="menu-image"
              type="file"
              accept="image/*"
              onChange={handleFileChange}
              className="border rounded p-2"
            />
          </div>

          {previewUrl && (
            <div className="mt-2">
              <p className="text-sm font-medium mb-2">Vista previa:</p>
              <div className="border rounded overflow-hidden max-h-[300px] overflow-y-auto">
                <img 
                  src={previewUrl} 
                  alt="Vista previa del menú" 
                  className="max-w-full h-auto" 
                />
              </div>
            </div>
          )}
        </div>

        <DialogFooter className="flex justify-between sm:justify-between">
          <Button variant="outline" onClick={handleClose} disabled={isUploading}>
            Cerrar
          </Button>
          <Button onClick={handleUpload} disabled={!selectedFile || isUploading}>
            {isUploading ? "Actualizando..." : "Actualizar menú"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}