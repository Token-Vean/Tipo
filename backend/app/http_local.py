"""
Cliente HTTP para hablar con Ollama local.

Todas las llamadas a Ollama llevan el texto íntegro de los documentos, así que
el cliente se construye siempre aquí, con dos garantías explícitas:

- ``trust_env=False``. Por defecto httpx honra HTTP_PROXY / HTTPS_PROXY /
  ALL_PROXY del entorno. Docker puede inyectar esas variables en el contenedor
  (configuración ``proxies`` del cliente o de Docker Desktop), y entonces las
  peticiones a ``http://ollama:11434`` o ``host.docker.internal`` saldrían por
  el proxy corporativo con el contenido de los documentos. Tipo nunca debe
  enrutar el tráfico de Ollama a través de un proxy.
- ``follow_redirects=False``. Es el valor por defecto actual de httpx, pero se
  fija para que una redirección no pueda llevar una petición fuera del host
  validado en ``llm._validar_ollama_url``.

Mismo criterio que ``cliente_local`` en PlumA.
"""

from __future__ import annotations

import httpx


def cliente_local(timeout: httpx.Timeout) -> httpx.AsyncClient:
    """Devuelve un AsyncClient que ignora proxies de entorno y redirecciones."""
    return httpx.AsyncClient(
        timeout=timeout,
        trust_env=False,
        follow_redirects=False,
    )
