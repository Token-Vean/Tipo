"""Paquete de Windows generado desde el código versionado (0.3.1-beta.1)."""

from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "empaquetar_windows", ROOT / "scripts" / "empaquetar_windows.py"
)
emp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(emp)

V = "0.3.1-beta.1"
R = f"Tipo-{V}"


@pytest.mark.parametrize("ruta, esperado", [
    ("docker-compose.yml", f"{R}/programa/docker-compose.yml"),
    (".dockerignore", f"{R}/programa/.dockerignore"),
    (".env.example", f"{R}/programa/.env.example"),
    ("backend/app/llm.py", f"{R}/programa/backend/app/llm.py"),
    ("tools/windows/Tipo-Control.ps1", f"{R}/programa/tools/windows/Tipo-Control.ps1"),
    ("instalar.bat", f"{R}/programa/instalar.bat"),
    ("ejemplos/README.md", f"{R}/programa/ejemplos/README.md"),
    ("packaging/windows/Tipo - Instalar y abrir.vbs", f"{R}/Tipo - Instalar y abrir.vbs"),
    ("packaging/windows/ayuda/LEEME.txt", f"{R}/ayuda/LEEME.txt"),
    (f"packaging/windows/ayuda/Novedades {V}.txt", f"{R}/ayuda/Novedades {V}.txt"),
    ("packaging/windows/ayuda/Novedades 0.3.0-beta.2.txt", None),
    ("tests/test_seguridad.py", None),
    ("backend/tests/test_zonas.py", None),
    ("scripts/empaquetar_windows.py", None),
    ("examples/construir_ejemplos_bne.py", None),
    (".github/workflows/security-checks.yml", None),
    (".gitignore", None),
    ("LEEME_PRIMERO.md", None),
])
def test_ruta_en_paquete(ruta, esperado):
    assert emp.ruta_en_paquete(ruta, V) == esperado


@pytest.mark.parametrize("ruta", [
    ".env", "backend/.env.local", "data/tipo_auth.sqlite3", "x/users.json",
    "secrets/clave.txt", "certs/servidor.pem", "ejemplos/libro.pdf", "build.log",
    "modelos/gemma.gguf",
])
def test_ficheros_no_distribuibles(ruta):
    assert emp.motivo_prohibido(ruta)


@pytest.mark.parametrize("ruta", [
    ".env.example", "ejemplos/README.md", "backend/app/main.py", "Tipo.png",
    "frontend/static/app.js", "backend/app/datos_ejemplo.py",
])
def test_ficheros_distribuibles(ruta):
    assert emp.motivo_prohibido(ruta) is None


def test_crlf_y_bom_obligatorio():
    assert emp._ajustar_contenido("x/a.bat", b"@echo off\nexit /b 0\n") == b"@echo off\r\nexit /b 0\r\n"
    assert emp._ajustar_contenido("x/a.bat", b"a\r\nb\n") == b"a\r\nb\r\n"
    assert emp._ajustar_contenido("x/a.md", b"a\nb\n") == b"a\nb\n"
    assert emp._ajustar_contenido("x/a.sh", b"a\nb\n") == b"a\nb\n"
    assert emp._ajustar_contenido("tools/windows/Tipo-Control.ps1", b"\xef\xbb\xbfa\n") == b"\xef\xbb\xbfa\r\n"
    assert emp._ajustar_contenido("packaging/windows/ayuda/LEEME.txt", b"\xef\xbb\xbfa\n") == b"\xef\xbb\xbfa\r\n"
    with pytest.raises(emp.ErrorEmpaquetado, match="BOM"):
        emp._ajustar_contenido("tools/windows/Tipo-Control.ps1", b"a\n")
    with pytest.raises(emp.ErrorEmpaquetado, match="BOM"):
        emp._ajustar_contenido("packaging/windows/ayuda/LEEME.txt", b"a\n")


def test_lanzadores_apuntan_al_panel_del_paquete():
    panel = "programa\\tools\\windows\\Tipo-Control.ps1"
    vbs = (ROOT / "packaging" / "windows" / "Tipo - Instalar y abrir.vbs").read_text(encoding="ascii")
    bat = (ROOT / "packaging" / "windows" / "ayuda" / "Abrir sin VBScript.bat").read_text(encoding="ascii")
    assert panel in vbs and "-STA" in vbs and "WindowStyle Hidden" in vbs
    assert "..\\" + panel in bat
    assert (ROOT / "tools" / "windows" / "Tipo-Control.ps1").exists()


def test_la_ayuda_describe_los_botones_del_panel():
    panel = (ROOT / "tools" / "windows" / "Tipo-Control.ps1").read_text(encoding="utf-8-sig")
    botones = set(re.findall(r'^New-Button "([^"]+)"', panel, re.MULTILINE))
    leeme = (ROOT / "packaging" / "windows" / "ayuda" / "LEEME.txt").read_text(encoding="utf-8-sig")
    seccion = leeme.split("QUÉ HACE CADA BOTÓN", 1)[1].split("TUS DATOS", 1)[0]
    descritos = {b for b in botones if b in seccion}
    assert descritos == botones, f"botones sin describir: {sorted(botones - descritos)}"
    assert "8769" in leeme and "0.35.0" in leeme


def test_version_y_notas_alineadas():
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert (ROOT / "packaging" / "windows" / "ayuda" / f"Novedades {version}.txt").exists()
    panel = (ROOT / "tools" / "windows" / "Tipo-Control.ps1").read_text(encoding="utf-8-sig")
    assert f"Tipo {version}" in panel


def test_compose_con_nombre_de_proyecto_fijo():
    # En el paquete, la carpeta del Compose se llama «programa», como en el de
    # PlumA: sin nombre fijo las dos aplicaciones compartirían proyecto.
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert re.search(r"^name:\s*tipo\s*$", compose, re.MULTILINE)


def _repo_con_paquete() -> bool:
    if shutil.which("git") is None:
        return False
    try:
        emp._git("cat-file", "-e", "HEAD:packaging/windows/ayuda/LEEME.txt")
        return True
    except subprocess.CalledProcessError:
        return False


@pytest.mark.skipif(not _repo_con_paquete(), reason="requiere el repositorio Git con packaging/ en HEAD")
def test_construccion_desde_head(tmp_path):
    destino, resumen = emp.construir("HEAD", tmp_path / "a")
    version = emp.version_de("HEAD")
    raiz = f"Tipo-{version}"

    with zipfile.ZipFile(destino) as zf:
        nombres = set(zf.namelist())
        assert f"{raiz}/Tipo - Instalar y abrir.vbs" in nombres
        assert f"{raiz}/ayuda/LEEME.txt" in nombres
        assert f"{raiz}/ayuda/Novedades {version}.txt" in nombres
        assert f"{raiz}/programa/tools/windows/Tipo-Control.ps1" in nombres
        assert f"{raiz}/programa/docker-compose.yml" in nombres
        assert f"{raiz}/programa/.dockerignore" in nombres
        assert not any(
            "/tests/" in n or "/.github/" in n or "/scripts/" in n or n.endswith("/.env")
            for n in nombres
        )
        # Una sola cosa que abrir en la raíz: el lanzador. El resto, en carpetas.
        en_raiz = {n[len(raiz) + 1:] for n in nombres if n.count("/") == 1}
        assert en_raiz == {"Tipo - Instalar y abrir.vbs"}
        for n in nombres:
            if n.endswith((".bat", ".ps1", ".vbs")) or "/ayuda/" in n:
                datos = zf.read(n)
                assert b"\n" not in datos.replace(b"\r\n", b""), f"{n} sin CRLF"
            if n.endswith(".sh"):
                assert b"\r\n" not in zf.read(n), f"{n} con CRLF"
        assert zf.read(f"{raiz}/programa/tools/windows/Tipo-Control.ps1").startswith(b"\xef\xbb\xbf")

    # Mismo commit, mismo paquete.
    _, resumen2 = emp.construir("HEAD", tmp_path / "b")
    assert resumen == resumen2
    assert (tmp_path / "a" / f"{destino.name}.sha256").read_text(encoding="ascii") == f"{resumen}  {destino.name}\n"
    assert emp.verificar(destino, "HEAD") == []


@pytest.mark.skipif(not _repo_con_paquete(), reason="requiere el repositorio Git con packaging/ en HEAD")
def test_verificar_detecta_un_zip_manipulado(tmp_path):
    destino, _ = emp.construir("HEAD", tmp_path)
    version = emp.version_de("HEAD")
    manipulado = tmp_path / "manipulado.zip"
    with zipfile.ZipFile(destino) as origen, zipfile.ZipFile(manipulado, "w") as zf:
        for info in origen.infolist():
            datos = origen.read(info)
            if info.filename.endswith("/programa/docker-compose.yml"):
                datos = datos.replace(b'OLLAMA_NO_CLOUD: "1"', b'OLLAMA_NO_CLOUD: "0"')
            zf.writestr(info, datos)
        zf.writestr(f"Tipo-{version}/programa/extra.bat", b"@echo off\r\n")
    diferencias = emp.verificar(manipulado, "HEAD")
    assert any("contenido distinto" in d and "docker-compose.yml" in d for d in diferencias)
    assert any("sobra en el ZIP" in d and "extra.bat" in d for d in diferencias)
