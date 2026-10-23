"""Los controles de seguridad de docker-compose.yml no deben leerse de .env.

Un .env manipulado o heredado podía sustituir la imagen de Ollama, apagar el
sandbox de parsers o desactivar el inicio de sesión. Estos valores están
fijados como literales en docker-compose.yml; este test impide que vuelvan a
ser interpolaciones ${VAR:-...}.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))

BLOQUEADOS = {
    "USAR_SANDBOX_PARSERS": "true",
    "SANDBOX_TIMEOUT_SEGUNDOS": "90",
    "SANDBOX_MEMORIA_MB": "1536",
    "ALLOW_REMOTE_OLLAMA": "false",
    "ALLOW_NETWORK_EXPOSURE": "false",
    "TIPO_AUTH_DISABLED": "false",
}


@pytest.mark.parametrize("servicio", ["app", "app-external"])
@pytest.mark.parametrize("variable,valor", sorted(BLOQUEADOS.items()))
def test_control_de_seguridad_es_literal(servicio, variable, valor):
    entorno = COMPOSE["services"][servicio]["environment"]
    assert str(entorno[variable]) == valor, (
        f"{servicio}.{variable} debe ser el literal {valor!r}, no leerse de .env"
    )


def test_imagen_ollama_fijada_por_digest_y_sin_variable():
    imagen = COMPOSE["services"]["ollama"]["image"]
    assert "${" not in imagen
    assert "@sha256:" in imagen


def test_env_example_no_ofrece_variables_bloqueadas():
    lineas = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    activas = {linea.split("=", 1)[0] for linea in lineas if linea and not linea.startswith("#") and "=" in linea}
    assert not activas & (set(BLOQUEADOS) | {"OLLAMA_IMAGE"})
