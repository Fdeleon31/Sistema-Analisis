"""Ficha 15 y Ficha 21 · Flujo de revisión por roles (Preparador, Revisor, Socio), firmas Ed25519 y NIA 220/230."""
from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .bitacora import Bitacora
from .cripto import firmar_ed25519, sellar_corrida
from .seguridad import ErrorSeguridad
from .usuarios import puede_firmar_rol

ROLES_FIRMA = ("Preparador", "Revisor", "Socio")
ESTADOS_REVISION = (
    "Pendiente",
    "En revisión",
    "Aclarado con evidencia",
    "Hallazgo confirmado",
)


def _ahora_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ruta_revisiones(carpeta: str | Path) -> Path:
    return Path(carpeta) / "revisiones.json"


def cargar_revisiones(carpeta: str | Path, pruebas_ids: list[str] | None = None) -> dict[str, Any]:
    """Carga el estado de revisiones/firmas de una corrida, completando IDs faltantes."""
    ruta = ruta_revisiones(carpeta)
    if ruta.exists():
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    else:
        datos = {"bloqueado": False, "por_prueba": {}, "firmas": {}}

    datos.setdefault("bloqueado", False)
    datos.setdefault("por_prueba", {})
    datos.setdefault("firmas", {})

    for pid in pruebas_ids or []:
        datos["por_prueba"].setdefault(
            pid,
            {
                "estado": "Pendiente",
                "conclusion": "",
                "auditor": "",
                "rol": "",
                "fecha_utc": "",
            },
        )
    return datos


def guardar_revisiones(carpeta: str | Path, estado: dict[str, Any]) -> Path:
    ruta = ruta_revisiones(carpeta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(estado, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return ruta


def registrar_revision_prueba(
    carpeta: str | Path,
    prueba_id: str,
    estado_rev: str,
    conclusion: str,
    auditor: str,
    rol: str,
    bitacora: Bitacora | None = None,
) -> dict[str, Any]:
    """Registra o actualiza la conclusión y estado de una prueba con trazabilidad SHA-256."""
    if estado_rev not in ESTADOS_REVISION:
        raise ValueError(f"Estado de revisión inválido: {estado_rev!r}. Válidos: {', '.join(ESTADOS_REVISION)}")
    if rol not in ROLES_FIRMA:
        raise ValueError(f"Rol de firma inválido: {rol!r}. Válidos: {', '.join(ROLES_FIRMA)}")
    aud_limpio = (auditor or "").strip()
    if not aud_limpio:
        raise ValueError("Indica el nombre del auditor antes de registrar la revisión.")

    estado = cargar_revisiones(carpeta, [prueba_id])
    if estado.get("bloqueado"):
        raise ValueError(
            "El papel de trabajo está cerrado con firma de Socio. Reábrelo con motivo antes de modificar conclusiones."
        )

    ahora = _ahora_utc()
    estado["por_prueba"][prueba_id] = {
        "estado": estado_rev,
        "conclusion": (conclusion or "").strip(),
        "auditor": aud_limpio,
        "rol": rol,
        "fecha_utc": ahora,
    }
    guardar_revisiones(carpeta, estado)

    if bitacora is not None:
        bitacora.registrar(
            "revision_prueba",
            prueba=prueba_id,
            estado=estado_rev,
            conclusion=(conclusion or "").strip(),
            auditor=aud_limpio,
            rol=rol,
        )
    return estado


def firmar_papel_trabajo(
    carpeta: str | Path,
    rol: str,
    auditor: str,
    observacion: str = "",
    bitacora: Bitacora | None = None,
    pruebas_ejecutadas: list[str] | None = None,
    exigir_segregacion: bool = False,
    sesion: Any = None,
    ventana_archivo_dias: int = 60,
    regenerar_cedula: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    """Estampa firma de Preparador, Revisor o Socio cumpliendo controles de calidad NIA 220 y sellado Ed25519.

    `regenerar_cedula` (opcional) se llama después de guardar la firma y ANTES de sellar, para que la cédula
    con las firmas quede dentro del sello. Regenerarla después del sello la deja marcada como alterada.
    """
    if rol not in ROLES_FIRMA:
        raise ValueError(f"Rol inválido: {rol!r}. Usa {', '.join(ROLES_FIRMA)}.")
    aud_limpio = (auditor or "").strip()
    if not aud_limpio:
        raise ValueError(f"Indica el nombre completo de quien firma como {rol}.")

    if sesion is not None and not puede_firmar_rol(sesion, rol):
        raise ErrorSeguridad(
            f"El usuario '{getattr(sesion, 'usuario', '')}' con perfil "
            f"'{getattr(sesion, 'perfil', '')}' no está autorizado para firmar como {rol}."
        )

    estado = cargar_revisiones(carpeta, pruebas_ejecutadas)
    if estado.get("bloqueado") and rol != "Socio":
        raise ValueError("El papel ya está cerrado por Socio. Reábrelo para volver a firmar.")

    if exigir_segregacion:
        usuario_actual = (getattr(sesion, "usuario", None) or "").strip().lower()
        nombre_actual = " ".join(aud_limpio.split()).lower()
        for otro_rol, info in (estado.get("firmas") or {}).items():
            if otro_rol == rol or not isinstance(info, dict):
                continue
            otro_usuario = (info.get("usuario") or "").strip().lower()
            otro_nombre = " ".join(str(info.get("auditor") or "").split()).lower()
            misma_persona = (
                (usuario_actual and otro_usuario and usuario_actual == otro_usuario)
                or ((not usuario_actual or not otro_usuario) and nombre_actual == otro_nombre)
            )
            if misma_persona:
                raise ErrorSeguridad(
                    f"Segregación NIA 220: la misma persona no puede firmar los roles '{otro_rol}' y '{rol}'."
                )

    if rol == "Socio":
        if "Preparador" not in estado.get("firmas", {}):
            raise ValueError("El rol 'Preparador' debe firmar antes del cierre definitivo por Socio.")
        pendientes = [
            pid
            for pid in (pruebas_ejecutadas or list(estado["por_prueba"].keys()))
            if estado["por_prueba"].get(pid, {}).get("estado", "Pendiente") == "Pendiente"
        ]
        if pendientes:
            raise ValueError(
                f"No puedes cerrar como Socio mientras existan pruebas en estado 'Pendiente': {', '.join(pendientes)}."
            )

    obs_limpia = (observacion or "").strip()
    hash_cadena = ""
    if bitacora is not None:
        datos_ev: dict[str, Any] = {
            "rol": rol,
            "auditor": aud_limpio,
            "observacion": obs_limpia,
        }
        if sesion is not None and getattr(sesion, "usuario", None):
            datos_ev["usuario"] = sesion.usuario
        reg = bitacora.registrar("firma_papel_trabajo", **datos_ev)
        hash_cadena = reg["hash"]

    ahora = _ahora_utc()
    datos_firma: dict[str, Any] = {
        "auditor": aud_limpio,
        "fecha_utc": ahora,
        "observacion": obs_limpia,
        "hash_bitacora": hash_cadena,
    }
    if sesion is not None:
        usuario_ses = getattr(sesion, "usuario", None)
        if usuario_ses:
            datos_firma["usuario"] = usuario_ses
        semilla = getattr(sesion, "semilla_privada_bytes", None)
        if semilla:
            payload_firma = json.dumps(
                {
                    "rol": rol,
                    "auditor": aud_limpio,
                    "usuario": usuario_ses or "",
                    "fecha_utc": ahora,
                    "observacion": obs_limpia,
                    "hash_bitacora": hash_cadena,
                },
                sort_keys=True,
                ensure_ascii=False,
            ).encode("utf-8")
            firma_bytes = firmar_ed25519(semilla, payload_firma)
            datos_firma["huella_clave"] = getattr(sesion, "huella_clave", "")
            datos_firma["firma_ed25519_b64"] = base64.b64encode(firma_bytes).decode("ascii")

    estado["firmas"][rol] = datos_firma
    if rol == "Socio":
        estado["bloqueado"] = True
        estado["fecha_cierre_utc"] = ahora
        estado["ventana_archivo_dias"] = int(ventana_archivo_dias)

    guardar_revisiones(carpeta, estado)
    if regenerar_cedula is not None:
        regenerar_cedula()

    if rol == "Socio" and sesion is not None and getattr(sesion, "semilla_privada_bytes", None):
        sellar_corrida(
            carpeta,
            usuario=sesion.usuario,
            rol=rol,
            semilla_privada=sesion.semilla_privada_bytes,
            clave_publica=sesion.clave_publica_bytes,
            bitacora=bitacora,
        )
    return estado


def reabrir_papel_trabajo(
    carpeta: str | Path,
    motivo: str,
    auditor: str,
    rol: str = "Socio",
    bitacora: Bitacora | None = None,
    sesion: Any = None,
) -> dict[str, Any]:
    """Reabre un papel cerrado dejando constancia obligatoria del motivo en la bitácora SHA-256."""
    motivo_limpio = (motivo or "").strip()
    aud_limpio = (auditor or "").strip()
    if not motivo_limpio:
        raise ValueError("Debes indicar el motivo de reapertura del papel de trabajo.")
    if not aud_limpio:
        raise ValueError("Indica el auditor responsable de la reapertura.")

    if sesion is not None:
        perfil_ses = getattr(sesion, "perfil", None)
        rol_aud_ses = getattr(sesion, "rol_auditoria", None)
        if perfil_ses != "Socio" and rol_aud_ses != "Socio":
            raise ErrorSeguridad("Solo un usuario con perfil o rol de 'Socio' puede reabrir un papel cerrado.")

    estado = cargar_revisiones(carpeta)
    estado["bloqueado"] = False
    estado.get("firmas", {}).pop("Socio", None)
    estado.pop("fecha_cierre_utc", None)
    guardar_revisiones(carpeta, estado)

    sello_path = Path(carpeta) / "sello.json"
    hash_sello_anterior = ""
    if sello_path.exists():
        hash_sello_anterior = hashlib.sha256(sello_path.read_bytes()).hexdigest()
        sello_path.unlink()

    if bitacora is not None:
        datos_ev: dict[str, Any] = {
            "motivo": motivo_limpio,
            "auditor": aud_limpio,
            "rol": rol,
        }
        if sesion is not None and getattr(sesion, "usuario", None):
            datos_ev["usuario"] = sesion.usuario
        if hash_sello_anterior:
            datos_ev["hash_sello_anterior"] = hash_sello_anterior
        bitacora.registrar("reapertura_papel_trabajo", **datos_ev)
    return estado


def estado_archivo_nia230(carpeta: str | Path, ventana_dias: int = 60) -> dict[str, Any]:
    """Calcula el estado de la ventana de compilación/archivo definitivo (60 días por defecto, NIA 230)."""
    estado = cargar_revisiones(carpeta)
    ventana = int(ventana_dias) if ventana_dias != 60 else int(estado.get("ventana_archivo_dias") or 60)
    ventana = max(1, ventana)
    cerrado = bool(estado.get("bloqueado"))
    fecha_cierre = str(
        estado.get("fecha_cierre_utc")
        or ((estado.get("firmas") or {}).get("Socio") or {}).get("fecha_utc")
        or ""
    )

    if not cerrado or not fecha_cierre:
        return {
            "cerrado": False,
            "fecha_cierre_utc": "",
            "dias_transcurridos": 0,
            "dias_restantes": ventana,
            "ventana_dias": ventana,
            "archivado_definitivo": False,
        }

    dt_cierre = datetime.fromisoformat(fecha_cierre.replace("Z", "+00:00"))
    if dt_cierre.tzinfo is None:
        dt_cierre = dt_cierre.replace(tzinfo=timezone.utc)
    dias_transcurridos = max(0, (datetime.now(timezone.utc) - dt_cierre).days)
    dias_restantes = max(0, ventana - dias_transcurridos)
    return {
        "cerrado": True,
        "fecha_cierre_utc": fecha_cierre,
        "dias_transcurridos": dias_transcurridos,
        "dias_restantes": dias_restantes,
        "ventana_dias": ventana,
        "archivado_definitivo": dias_transcurridos >= ventana,
    }
