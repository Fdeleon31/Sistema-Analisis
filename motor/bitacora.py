"""Bitácora de evidencia (Ficha 00).

Archivo JSONL de solo agregar. Cada registro guarda el hash del registro
anterior, así que cualquier edición posterior rompe la cadena y se detecta.
"""
from __future__ import annotations

import getpass
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

HASH_INICIAL = "0" * 64


def _hash_registro(registro: dict) -> str:
    texto = json.dumps(registro, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


class Bitacora:
    def __init__(self, ruta: str | Path, usuario: str | None = None):
        self.ruta = Path(ruta)
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self.usuario = usuario or _usuario_actual()

    def _ultimo_hash(self) -> str:
        if not self.ruta.exists():
            return HASH_INICIAL
        ultimo = HASH_INICIAL
        with self.ruta.open(encoding="utf-8") as f:
            for linea in f:
                if linea.strip():
                    ultimo = json.loads(linea)["hash"]
        return ultimo

    def registrar(self, evento: str, **datos) -> dict:
        registro = {
            "fecha_hora_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "usuario": self.usuario,
            "evento": evento,
            "datos": datos,
            "hash_anterior": self._ultimo_hash(),
        }
        registro["hash"] = _hash_registro(registro)
        with self.ruta.open("a", encoding="utf-8") as f:
            f.write(json.dumps(registro, ensure_ascii=False, default=str) + "\n")
        return registro

    def leer(self) -> list[dict]:
        if not self.ruta.exists():
            return []
        with self.ruta.open(encoding="utf-8") as f:
            return [json.loads(l) for l in f if l.strip()]

    def verificar(self) -> bool:
        """True si la cadena de hashes está intacta."""
        anterior = HASH_INICIAL
        for registro in self.leer():
            copia = {k: v for k, v in registro.items() if k != "hash"}
            if registro["hash_anterior"] != anterior or _hash_registro(copia) != registro["hash"]:
                return False
            anterior = registro["hash"]
        return True


def _usuario_actual() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return "desconocido"
