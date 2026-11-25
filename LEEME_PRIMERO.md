# Tipo — instalación rápida

Tipo es un asistente local de precatalogación para monografías impresas.

## Windows

Descarga de [Releases](https://github.com/Token-Vean/Tipo/releases) el ZIP
`Tipo-…-windows.zip`, desbloquéalo (botón derecho > Propiedades >
«Desbloquear»), descomprímelo y abre **«Tipo - Instalar y abrir»**. La ayuda
está en la carpeta `ayuda` del paquete.

Desde una copia del repositorio: `Tipo-Control.bat` (panel) o `instalar.bat`.

## Linux/macOS

```bash
chmod +x instalar.sh detener.sh desinstalar.sh
./instalar.sh
```

La aplicación se abre en <http://localhost:8769> (PlumA usa el 8082).

## Límites importantes

Tipo no consulta servicios externos, no crea puntos de acceso autorizados, no asigna materias normalizadas y no opera sobre sistemas bibliotecarios. El resultado es una propuesta revisable por el profesional.
