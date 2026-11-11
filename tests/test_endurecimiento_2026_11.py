"""Regresiones de los endurecimientos portados desde PlumA (2026-11)."""

from __future__ import annotations

import re
from pathlib import Path

import httpx

APP = Path(__file__).resolve().parents[1] / "backend" / "app"


def test_cliente_local_ignora_proxy_de_entorno(monkeypatch):
    """Un proxy en el entorno no debe recibir el tráfico de Ollama."""
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.invalid:3128")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:3128")
    monkeypatch.setenv("ALL_PROXY", "http://proxy.invalid:3128")
    from app.http_local import cliente_local

    cliente = cliente_local(httpx.Timeout(5.0))
    assert cliente.trust_env is False
    assert cliente.follow_redirects is False


def test_ningun_modulo_crea_clientes_httpx_directamente():
    """Todas las llamadas HTTP salen de http_local.cliente_local."""
    patron = re.compile(r"httpx\.(AsyncClient|Client)\(|httpx\.(get|post|stream|request)\(")
    infractores = [
        ruta.name
        for ruta in sorted(APP.glob("*.py"))
        if ruta.name != "http_local.py" and patron.search(ruta.read_text(encoding="utf-8"))
    ]
    assert infractores == []


def test_cabeceras_de_seguridad_es_el_middleware_mas_externo():
    """El último add_middleware es el más externo: debe ser CabecerasSeguridad,
    para que los rechazos de los demás middlewares también lleven CSP."""
    fuente = (APP / "main.py").read_text(encoding="utf-8")
    registrados = re.findall(r"^app\.add_middleware\((\w+)\)", fuente, flags=re.MULTILINE)
    assert registrados[-1] == "CabecerasSeguridad"
    assert registrados.index("ProteccionAccesoLocal") > registrados.index("ProteccionAutenticacion")


def test_pbkdf2_no_se_calcula_en_el_event_loop():
    """Dentro de los handlers async, _hash_password solo se invoca vía to_thread."""
    fuente = (APP / "auth.py").read_text(encoding="utf-8")
    handlers = re.split(r"^(?=@router\.)", fuente, flags=re.MULTILINE)[1:]
    for bloque in handlers:
        cuerpo = bloque.split("\ndef ", 1)[0]
        directas = re.findall(r"(?<!to_thread\()_hash_password\(", cuerpo)
        assert directas == [], cuerpo.splitlines()[1]
