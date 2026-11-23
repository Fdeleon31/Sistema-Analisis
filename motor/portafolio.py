"""Ficha 15 · Gestión de portafolio de encargos (.yaml) e historial de corridas auditadas."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from .bitacora import Bitacora
from .revision import ROLES_FIRMA, cargar_revisiones
from .rutas import raiz_salidas, raiz_trabajo


def carpeta_encargos() -> Path:
    carpeta = raiz_trabajo() / "encargos"
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def carpeta_salidas() -> Path:
    carpeta = raiz_salidas()
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def listar_encargos(ruta_carpeta: str | Path | None = None) -> list[dict[str, Any]]:
    """Lista los encargos guardados en encargos/*.yaml ordenados por nombre de archivo."""
    carpeta = Path(ruta_carpeta) if ruta_carpeta else carpeta_encargos()
    if not carpeta.exists():
        return []
    salida: list[dict[str, Any]] = []
    for ruta in sorted(carpeta.glob("*.yaml")):
        try:
            datos = yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}
        except Exception:  # noqa: BLE001
            continue
        salida.append({
            "ruta": ruta,
            "archivo": ruta.name,
            "cliente": str(datos.get("cliente") or ruta.stem),
            "fecha_cierre": str(datos.get("fecha_cierre") or ""),
            "marco": str(datos.get("marco") or "NIIF"),
            "materialidad": float(datos.get("materialidad") or 0.0),
            "materialidad_ejecucion": float(datos.get("materialidad_ejecucion") or 0.0),
            "umbral_trivial": float(datos.get("umbral_trivial") or 0.0),
            "umbral_aprobacion": float(datos.get("umbral_aprobacion") or 0.0),
            "preparo": str(datos.get("preparo") or ""),
            "reviso": str(datos.get("reviso") or ""),
            "aprobo": str(datos.get("aprobo") or ""),
            "datos": datos,
        })
    return salida


def _slug_archivo(texto: str) -> str:
    limpio = re.sub(r"[^a-zA-Z0-9_-]+", "-", texto.strip().lower()).strip("-")
    return limpio or "encargo"


def guardar_encargo_yaml(datos: dict[str, Any], nombre_o_ruta: str | Path) -> Path:
    """Guarda los parámetros de un encargo como YAML reutilizable en encargos/."""
    destino = Path(nombre_o_ruta)
    if not destino.is_absolute() and destino.parent == Path("."):
        nombre = _slug_archivo(destino.stem)
        destino = carpeta_encargos() / f"{nombre}.yaml"
    else:
        destino.parent.mkdir(parents=True, exist_ok=True)
        if destino.suffix.lower() != ".yaml":
            destino = destino.with_suffix(".yaml")

    serializable: dict[str, Any] = {}
    for k, v in datos.items():
        if str(k).startswith("_"):
            continue
        if isinstance(v, date):
            serializable[k] = v.isoformat()
        else:
            serializable[k] = v

    destino.write_text(
        yaml.safe_dump(serializable, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return destino


def resumen_corrida_carpeta(carpeta: Path) -> dict[str, Any] | None:
    """Lee un directorio histórico de salida y verifica su bitácora SHA-256 y firmas."""
    bit_ruta = carpeta / "bitacora.jsonl"
    if not bit_ruta.exists():
        return None
    bit = Bitacora(bit_ruta)
    try:
        registros = bit.leer()
        integra = bit.verificar()
    except Exception:  # noqa: BLE001
        return {
            "carpeta": carpeta,
            "nombre": carpeta.name,
            "paquete": "—",
            "cliente": "Registro corrupto",
            "fecha_utc": "",
            "eventos": 0,
            "pruebas_ejecutadas": [],
            "sha256_integro": False,
            "cedula": carpeta / "cedula.xlsx",
            "cedula_existe": (carpeta / "cedula.xlsx").exists(),
            "revisiones": {"bloqueado": False, "por_prueba": {}, "firmas": {}},
            "estado_firmas": "Bitácora corrupta",
        }

    inicio = next((r for r in registros if r.get("evento") == "inicio"), None)
    datos_ini = (inicio or {}).get("datos", {})
    paquete = str(datos_ini.get("paquete") or "—")
    cliente = str(datos_ini.get("cliente") or "Sin cliente")
    fecha_utc = str((inicio or (registros[0] if registros else {})).get("fecha_hora_utc") or "")

    pruebas_exec: list[dict[str, Any]] = []
    for r in registros:
        if r.get("evento") == "prueba":
            d = r.get("datos", {})
            pruebas_exec.append({
                "id": str(d.get("prueba") or ""),
                "filas": int(d.get("filas_resultado") or 0),
                "resumen": d.get("resumen") or {},
            })

    rev = cargar_revisiones(carpeta, [p["id"] for p in pruebas_exec if p["id"]])
    firmas = rev.get("firmas", {})
    roles_ok = [rol for rol in ROLES_FIRMA if rol in firmas]
    estado_firmas = ("Cerrado · " if rev.get("bloqueado") else "") + (" → ".join(roles_ok) if roles_ok else "Sin firmas")

    cedula = carpeta / "cedula.xlsx"
    return {
        "carpeta": carpeta,
        "nombre": carpeta.name,
        "paquete": paquete,
        "cliente": cliente,
        "fecha_utc": fecha_utc,
        "eventos": len(registros),
        "pruebas_ejecutadas": pruebas_exec,
        "sha256_integro": integra,
        "cedula": cedula,
        "cedula_existe": cedula.exists(),
        "revisiones": rev,
        "estado_firmas": estado_firmas,
    }


def listar_corridas_recientes(ruta_salidas: str | Path | None = None, limite: int = 40) -> list[dict[str, Any]]:
    """Lista corridas históricas más recientes en salidas/ con estado SHA-256 y firmas."""
    carpeta = Path(ruta_salidas) if ruta_salidas else carpeta_salidas()
    if not carpeta.exists():
        return []
    dirs = sorted((d for d in carpeta.iterdir() if d.is_dir()), key=lambda d: d.name, reverse=True)
    salida: list[dict[str, Any]] = []
    for d in dirs:
        info = resumen_corrida_carpeta(d)
        if info is not None:
            salida.append(info)
            if len(salida) >= limite:
                break
    return salida
