#!/usr/bin/env python3
"""
Construye y verifica el paquete de Tipo para Windows.

    python scripts/empaquetar_windows.py                            # paquete desde HEAD
    python scripts/empaquetar_windows.py --ref v0.3.1-beta.1        # desde una etiqueta
    python scripts/empaquetar_windows.py --verificar dist/Tipo-0_3_1-beta_1-windows.zip --ref v0.3.1-beta.1

Mismo procedimiento que PlumA desde la 0.7.4. Sustituye a
scripts/crear_release_windows.ps1, que solo funcionaba en Windows y producía un
ZIP distinto en cada ejecución.

- El contenido se lee de los objetos de Git de la referencia indicada, no del
  directorio de trabajo: los cambios sin commit y los ficheros ignorados (un
  .env, documentos de prueba, la base de datos local) no entran en el paquete.
- packaging/windows/ va a la raíz del paquete (lanzador «Tipo - Instalar y
  abrir.vbs» y carpeta ayuda); el resto del repositorio, salvo lo que solo
  sirve para desarrollo, va a programa/.
- Los .bat, .cmd, .ps1, .vbs y los .txt de la ayuda se escriben con CRLF:
  cmd.exe interpreta mal algunos .bat con LF y el Bloc de notas antiguo no
  muestra bien los saltos de línea.
- Los .ps1 del panel deben estar en UTF-8 con BOM: Windows PowerShell 5.1 lee
  como ANSI los scripts sin BOM y estropea las tildes.
- Segunda barrera: si algo que no debe distribuirse llegó a versionarse por
  error (.env, claves, bases de datos, documentos en ejemplos/), el
  empaquetado se detiene.
- Orden de entradas, fecha (la del commit), permisos y compresión son fijos:
  el mismo commit produce el mismo ZIP, byte a byte.

--verificar compara un ZIP, fichero a fichero, con lo que produciría la
referencia indicada. Sirve para comprobar que un paquete publicado coincide
con su etiqueta sin depender de que la compresión sea idéntica byte a byte.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
import time
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]

# Solo sirven para desarrollo o para generar el propio paquete.
EXCLUIR_PREFIJOS = (
    ".github/",
    "backend/tests/",
    "examples/",
    "packaging/",
    "scripts/",
    "tests/",
)
EXCLUIR_FICHEROS = {
    ".gitattributes",
    ".gitignore",
    # Guía rápida del repositorio; en el paquete la sustituye ayuda/LEEME.txt.
    "LEEME_PRIMERO.md",
}
SUFIJOS_CRLF = {".bat", ".cmd", ".ps1", ".vbs"}
PREFIJO_AYUDA = "packaging/windows/ayuda/"
PANEL = "tools/windows/Tipo-Control.ps1"
LANZADOR = "packaging/windows/Tipo - Instalar y abrir.vbs"
OBLIGATORIOS = {
    ".dockerignore",
    ".env.example",
    "docker-compose.yml",
    "backend/Dockerfile",
    "backend/requirements.txt",
    "frontend/static/index.html",
    "instalar.bat",
    "detener.bat",
    "desinstalar.bat",
    "LICENSE",
    PANEL,
    "tools/windows/comprobar-ollama.ps1",
    "tools/windows/validar-env.ps1",
    LANZADOR,
    PREFIJO_AYUDA + "LEEME.txt",
    PREFIJO_AYUDA + "Abrir sin VBScript.bat",
}

# Lo que nunca debe distribuirse aunque esté versionado.
_EXTENSIONES_PROHIBIDAS = {
    ".pem", ".key", ".crt", ".pfx", ".p12", ".sqlite", ".sqlite3", ".db",
    ".log", ".bak", ".tmp", ".gguf",
}
_CARPETAS_PROHIBIDAS = {
    "secrets", "credentials", "pruebas", "documentos_prueba", "test_documents",
    "uploads_local", "exports", "salidas", "data",
}


class ErrorEmpaquetado(RuntimeError):
    pass


def _git(*args: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], check=True, capture_output=True
    ).stdout


def version_de(ref: str) -> str:
    texto = _git("show", f"{ref}:backend/app/version.py").decode("utf-8")
    m = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', texto, re.MULTILINE)
    if not m:
        raise ErrorEmpaquetado("no se encuentra APP_VERSION en backend/app/version.py")
    version = m.group(1)
    fichero = _git("show", f"{ref}:VERSION").decode("utf-8").strip()
    if fichero != version:
        raise ErrorEmpaquetado(
            f"VERSION ({fichero}) y backend/app/version.py ({version}) no coinciden"
        )
    return version


def motivo_prohibido(ruta: str) -> str | None:
    """Por qué un fichero versionado no puede ir en el paquete, o None."""
    p = PurePosixPath(ruta)
    nombre = p.name.lower()
    if nombre.startswith(".env") and nombre != ".env.example":
        return "configuración local (.env)"
    if p.suffix.lower() in _EXTENSIONES_PROHIBIDAS:
        return f"tipo de fichero no distribuible ({p.suffix})"
    if nombre == "users.json":
        return "base de usuarios"
    if any(parte.lower() in _CARPETAS_PROHIBIDAS for parte in p.parts[:-1]):
        return "carpeta de datos locales"
    if p.parts[0] == "ejemplos" and p.suffix.lower() != ".md":
        return "documento de ejemplo (solo se admiten .md en ejemplos/)"
    return None


def ruta_en_paquete(ruta: str, version: str) -> str | None:
    """Ruta dentro del ZIP para un fichero del repositorio, o None si no va."""
    raiz = f"Tipo-{version}"
    if ruta.startswith("packaging/windows/"):
        resto = ruta[len("packaging/windows/"):]
        nombre = PurePosixPath(resto).name
        # Solo las notas de esta versión; las de versiones anteriores no.
        if resto.startswith("ayuda/Novedades ") and nombre != f"Novedades {version}.txt":
            return None
        return f"{raiz}/{resto}"
    if ruta in EXCLUIR_FICHEROS or ruta.startswith(EXCLUIR_PREFIJOS):
        return None
    return f"{raiz}/programa/{ruta}"


def _requiere_bom(ruta: str) -> bool:
    return (ruta.startswith("tools/windows/") and ruta.endswith(".ps1")) or (
        ruta.startswith(PREFIJO_AYUDA) and ruta.endswith(".txt")
    )


def _ajustar_contenido(ruta: str, datos: bytes) -> bytes:
    if _requiere_bom(ruta) and not datos.startswith(b"\xef\xbb\xbf"):
        raise ErrorEmpaquetado(f"{ruta} debe estar codificado en UTF-8 con BOM")
    sufijo = PurePosixPath(ruta).suffix.lower()
    if sufijo in SUFIJOS_CRLF or (ruta.startswith(PREFIJO_AYUDA) and sufijo == ".txt"):
        datos = datos.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    return datos


def contenido_paquete(ref: str) -> tuple[str, dict[str, bytes]]:
    """Devuelve la versión y {ruta en el ZIP: bytes} para la referencia."""
    version = version_de(ref)
    rutas = _git("ls-tree", "-r", "-z", "--name-only", ref).decode("utf-8").split("\0")
    rutas = [r for r in rutas if r]

    faltan = OBLIGATORIOS - set(rutas)
    notas = f"{PREFIJO_AYUDA}Novedades {version}.txt"
    if notas not in rutas:
        faltan.add(notas)
    if faltan:
        raise ErrorEmpaquetado(f"faltan ficheros en {ref}: {sorted(faltan)}")

    paquete: dict[str, bytes] = {}
    for ruta in rutas:
        destino = ruta_en_paquete(ruta, version)
        if destino is None:
            continue
        motivo = motivo_prohibido(ruta)
        if motivo:
            raise ErrorEmpaquetado(f"fichero no distribuible en el repositorio: {ruta} ({motivo})")
        datos = _git("show", f"{ref}:{ruta}")
        paquete[destino] = _ajustar_contenido(ruta, datos)
    return version, paquete


def nombre_zip(version: str) -> str:
    return f"Tipo-{version.replace('.', '_')}-windows.zip"


def _fecha_commit(ref: str) -> tuple[int, int, int, int, int, int]:
    segundos = int(_git("log", "-1", "--format=%ct", ref).decode().strip())
    fecha = time.gmtime(max(segundos, 315532800))  # ZIP no admite fechas < 1980
    return fecha[:6]


def construir(ref: str, salida: Path) -> tuple[Path, str]:
    version, paquete = contenido_paquete(ref)
    fecha = _fecha_commit(ref)
    salida.mkdir(parents=True, exist_ok=True)
    destino = salida / nombre_zip(version)
    with zipfile.ZipFile(destino, "w") as zf:
        for nombre in sorted(paquete):
            info = zipfile.ZipInfo(nombre, date_time=fecha)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            zf.writestr(info, paquete[nombre], compresslevel=9)
    resumen = hashlib.sha256(destino.read_bytes()).hexdigest()
    (salida / f"{destino.name}.sha256").write_text(
        f"{resumen}  {destino.name}\n", encoding="ascii", newline="\n"
    )
    return destino, resumen


def verificar(zip_path: Path, ref: str) -> list[str]:
    """Diferencias entre el ZIP y lo que produciría la referencia (vacío si coinciden)."""
    _, esperado = contenido_paquete(ref)
    diferencias: list[str] = []
    with zipfile.ZipFile(zip_path) as zf:
        presentes = {i.filename: i for i in zf.infolist() if not i.is_dir()}
        for nombre in sorted(set(esperado) - set(presentes)):
            diferencias.append(f"falta en el ZIP: {nombre}")
        for nombre in sorted(set(presentes) - set(esperado)):
            diferencias.append(f"sobra en el ZIP: {nombre}")
        for nombre in sorted(set(presentes) & set(esperado)):
            if zf.read(nombre) != esperado[nombre]:
                diferencias.append(f"contenido distinto: {nombre}")
    return diferencias


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--ref", default="HEAD", help="commit o etiqueta de Git (por defecto, HEAD)")
    parser.add_argument("--salida", type=Path, default=ROOT / "dist",
                        help="carpeta de salida (por defecto, dist/)")
    parser.add_argument("--verificar", type=Path, metavar="ZIP",
                        help="compara un ZIP con la referencia en lugar de construirlo")
    args = parser.parse_args(argv)
    try:
        if args.verificar:
            diferencias = verificar(args.verificar, args.ref)
            if diferencias:
                print(f"[FAIL] {args.verificar.name} no coincide con {args.ref}:")
                for d in diferencias:
                    print(f"  - {d}")
                return 1
            print(f"[OK] {args.verificar.name} coincide fichero a fichero con {args.ref}")
            return 0
        if _git("status", "--porcelain", "--untracked-files=no").strip():
            print("[AVISO] hay cambios sin commit; el paquete usa solo lo que está en "
                  f"{args.ref}", file=sys.stderr)
        destino, resumen = construir(args.ref, args.salida)
        print(f"[OK] {destino}")
        print(f"     SHA-256 {resumen}")
        return 0
    except (ErrorEmpaquetado, subprocess.CalledProcessError) as err:
        detalle = getattr(err, "stderr", b"") or b""
        print(f"[FAIL] {err} {detalle.decode('utf-8', 'replace').strip()}".rstrip(),
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
