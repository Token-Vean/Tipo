# Instalación de Tipo

Tipo se ejecuta localmente con Docker y Ollama. La guía completa está en el
[README](README.md#instalación-rápida-en-windows).

## Windows

- **Paquete de la release** (recomendado): descarga `Tipo-…-windows.zip` de
  [Releases](https://github.com/Token-Vean/Tipo/releases), desbloquéalo
  (botón derecho > Propiedades > «Desbloquear»), descomprímelo y abre
  «Tipo - Instalar y abrir». Instrucciones en `ayuda/LEEME.txt`.
- **Desde el repositorio**: `Tipo-Control.bat` abre el mismo panel;
  `instalar.bat` instala sin panel.

## Linux/macOS

```bash
chmod +x instalar.sh detener.sh desinstalar.sh
./instalar.sh
```

La URL local por defecto es `http://localhost:8769`.

## Generar el paquete de Windows

```bash
python scripts/empaquetar_windows.py --ref v0.3.1-beta.1
python scripts/empaquetar_windows.py --verificar dist/Tipo-0_3_1-beta_1-windows.zip --ref v0.3.1-beta.1
```

El paquete se construye a partir de los objetos de Git de la referencia (no
del directorio de trabajo) y es reproducible: el mismo commit produce el mismo
ZIP. Junto a él se escribe el `.sha256` que se adjunta a la release.
