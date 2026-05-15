"""Utilidades locales de recuperación de acceso para Tipo.

Uso previsto: ejecución desde el panel/instalador en la misma máquina donde se
ha desplegado Tipo, dentro del contenedor Docker de la aplicación. No expone
endpoints web ni permite recuperación remota.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from typing import Sequence

from . import auth


def _pedir_password(args) -> str:
    if args.password:
        return args.password
    if getattr(args, "password_env", None):
        value = os.getenv(args.password_env)
        if value:
            return value
    p1 = getpass.getpass("Nueva contraseña: ")
    p2 = getpass.getpass("Repita la contraseña: ")
    if p1 != p2:
        raise SystemExit("Las contraseñas no coinciden.")
    return p1


def reset_admin(args) -> int:
    username = auth._validar_usuario(args.username)
    password = _pedir_password(args)
    auth._validar_password(password)
    with auth._users_lock:
        store = auth._load_store()
        users = store.setdefault("users", {})
        user = users.setdefault(username, {})
        user.update({
            "password_hash": auth._hash_password(password),
            "role": "admin",
            "disabled": False,
            "password_changed_at": auth._now_iso(),
            "recovered_at": auth._now_iso(),
        })
        if "created_at" not in user:
            user["created_at"] = auth._now_iso()
        if args.disable_others:
            for other_name, other in users.items():
                if other_name != username and isinstance(other, dict):
                    other["disabled"] = True
                    other["disabled_by_recovery"] = True
        auth._save_store(store)
    print(f"Acceso recuperado. Usuario administrador activo: {username}")
    print("Vuelva a iniciar Tipo e inicie sesión con la nueva contraseña.")
    return 0


def list_users(_args) -> int:
    store = auth._load_store()
    users = store.get("users", {})
    if not users:
        print("No hay usuarios creados.")
        return 0
    for name, data in sorted(users.items()):
        role = data.get("role", "user") if isinstance(data, dict) else "?"
        disabled = "desactivado" if isinstance(data, dict) and data.get("disabled") else "activo"
        print(f"{name}\t{role}\t{disabled}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Recuperación local de acceso de Tipo")
    sub = parser.add_subparsers(dest="command", required=True)

    p_reset = sub.add_parser("reset-admin", help="Crear o restablecer un administrador local")
    p_reset.add_argument("--username", default="admin", help="Usuario administrador a crear/restablecer")
    p_reset.add_argument("--password", help="Nueva contraseña. Si se omite, se pedirá por consola.")
    p_reset.add_argument("--password-env", help="Nombre de variable de entorno que contiene la contraseña.")
    p_reset.add_argument("--disable-others", action="store_true", help="Desactivar el resto de usuarios")
    p_reset.set_defaults(func=reset_admin)

    p_list = sub.add_parser("list-users", help="Listar usuarios locales")
    p_list.set_defaults(func=list_users)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
