"""Gestión local de usuarios, RBAC, políticas de seguridad y llaves Ed25519 (Ficha 21 · Oleada 2)."""
from __future__ import annotations

import base64
import json
import os
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .bitacora import Bitacora
from .cripto import (
    cifrar_clave_privada,
    clave_publica_ed25519,
    firmar_ed25519,
    verificar_ed25519,
    descifrar_clave_privada,
    generar_par_ed25519,
    hashear_contrasena,
    huella_clave_publica,
    requiere_migracion_scrypt,
    verificar_contrasena,
)
from . import cripto as _cripto_mod
from .rutas import raiz_trabajo
from .seguridad import ErrorSeguridad

PERFIL_ADMIN = "Administrador"
PERFIL_PREPARADOR = "Preparador"
PERFIL_REVISOR = "Revisor"
PERFIL_SOCIO = "Socio"

PERFILES_VALIDOS = ("Administrador", "Preparador", "Revisor", "Socio")
PERFILES_AUDITORIA = ("Preparador", "Revisor", "Socio")

MAX_INTENTOS_FALLIDOS = 5
BLOQUEO_MINUTOS = 15

_RE_USUARIO_VALIDO = re.compile(r"^[A-Za-z0-9._@-]{2,64}$")
_POLITICAS_DEFECTO: dict[str, Any] = {
    "segregacion_estricta": True,
    "ventana_archivo_dias": 60,
    "max_intentos": MAX_INTENTOS_FALLIDOS,
    "bloqueo_minutos": BLOQUEO_MINUTOS,
    "alerta_nube": True,
}


def _ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


def _ahora_iso() -> str:
    return _ahora_utc().isoformat(timespec="seconds")


def _parsear_iso(valor: str | None) -> datetime | None:
    if not valor:
        return None
    try:
        dt = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _validar_usuario(usuario: str) -> str:
    limpio = (usuario or "").strip() if isinstance(usuario, str) else ""
    if not _RE_USUARIO_VALIDO.fullmatch(limpio):
        raise ErrorSeguridad(
            "El identificador de usuario debe tener entre 2 y 64 caracteres sin espacios (letras, números, ., _, @, -)."
        )
    return limpio


def _validar_nombre_completo(nombre: str) -> str:
    limpio = (nombre or "").strip() if isinstance(nombre, str) else ""
    if len(limpio) < 2 or any(ord(c) < 32 for c in limpio):
        raise ErrorSeguridad("Indica el nombre completo válido del usuario.")
    return limpio


def validar_politica_contrasena(contrasena: str) -> None:
    """Valida complejidad mínima: >= 10 caracteres, >= 1 mayúscula, >= 1 minúscula y >= 1 dígito."""
    if not isinstance(contrasena, str):
        raise ErrorSeguridad("La contraseña debe entregarse como texto.")
    faltantes: list[str] = []
    if len(contrasena) < 10:
        faltantes.append("al menos 10 caracteres")
    if not any(c.isupper() for c in contrasena):
        faltantes.append("al menos una letra mayúscula")
    if not any(c.islower() for c in contrasena):
        faltantes.append("al menos una letra minúscula")
    if not any(c.isdigit() for c in contrasena):
        faltantes.append("al menos un dígito")
    if faltantes:
        raise ErrorSeguridad("La contraseña no cumple la política de seguridad: requiere " + ", ".join(faltantes) + ".")


@dataclass
class SesionAutenticada:
    """Representa una sesión local verificada con llave Ed25519 en memoria."""

    usuario: str
    nombre_completo: str
    perfil: str
    rol_auditoria: str | None
    clave_publica_b64: str
    huella_clave: str
    fecha_login_utc: str
    _semilla_privada: bytes | None = field(default=None, repr=False)

    @property
    def es_admin(self) -> bool:
        return self.perfil == PERFIL_ADMIN

    @property
    def etiqueta_ui(self) -> str:
        rol_txt = (
            f"{self.perfil} / {self.rol_auditoria}"
            if self.rol_auditoria and self.rol_auditoria != self.perfil
            else self.perfil
        )
        return f"{self.nombre_completo} ({self.usuario}) · {rol_txt}"

    @property
    def clave_publica_bytes(self) -> bytes:
        return base64.b64decode(self.clave_publica_b64)

    @property
    def semilla_privada_bytes(self) -> bytes | None:
        return self._semilla_privada


def _semilla_de(actor: "SesionAutenticada") -> bytes:
    semilla = getattr(actor, "semilla_privada_bytes", None)
    if not semilla:
        raise ErrorSeguridad("La sesión del Administrador no tiene su clave de firma en memoria; vuelve a iniciar sesión.")
    return semilla


_SENUELO: dict[str, Any] = {}


def _registro_senuelo() -> dict[str, Any]:
    """Registro scrypt ficticio (se calcula una vez) para igualar el tiempo de un login con usuario inexistente."""
    if not _SENUELO or int(_SENUELO.get("n", 0)) != _cripto_mod.SCRYPT_N:
        _SENUELO.clear()
        _SENUELO.update(hashear_contrasena(secrets.token_urlsafe(24)))
    return _SENUELO


def puede_firmar_rol(sesion: SesionAutenticada, rol: str) -> bool:
    """Determina si la sesión está autorizada para firmar el rol de auditoría indicado."""
    if sesion is None or rol not in PERFILES_AUDITORIA:
        return False
    perfil = getattr(sesion, "perfil", None)
    rol_auditoria = getattr(sesion, "rol_auditoria", None)
    if perfil == PERFIL_ADMIN:
        return rol_auditoria == rol
    return perfil == rol or rol_auditoria == rol


class GestorUsuarios:
    """Administra cuentas locales, autenticación, bloqueo por fuerza bruta y políticas."""

    def __init__(self, ruta_base: str | Path | None = None):
        self.ruta_base = Path(ruta_base) if ruta_base is not None else raiz_trabajo()
        self.carpeta_seguridad = self.ruta_base / "seguridad"
        self.ruta_usuarios = self.carpeta_seguridad / "usuarios.json"
        self.ruta_bitacora = self.carpeta_seguridad / "bitacora_accesos.jsonl"

    def _bitacora(self, usuario: str = "sistema") -> Bitacora:
        return Bitacora(self.ruta_bitacora, usuario=usuario)

    def _leer_almacen(self) -> dict[str, Any]:
        if not self.ruta_usuarios.exists():
            return {"version": 1, "politicas": dict(_POLITICAS_DEFECTO), "usuarios": []}
        try:
            datos = json.loads(self.ruta_usuarios.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ErrorSeguridad(f"No se pudo leer la configuración de usuarios: {exc}") from exc
        if not isinstance(datos, dict):
            raise ErrorSeguridad("El archivo usuarios.json tiene un formato inválido.")
        politicas = dict(_POLITICAS_DEFECTO)
        politicas.update(datos.get("politicas") or {})
        datos["politicas"] = politicas
        datos.setdefault("usuarios", [])
        return datos

    def _guardar_almacen(self, datos: dict[str, Any]) -> None:
        self.carpeta_seguridad.mkdir(parents=True, exist_ok=True)
        tmp = self.ruta_usuarios.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.ruta_usuarios)

    def _buscar_usuario(self, datos: dict[str, Any], usuario: str) -> dict[str, Any] | None:
        clave = (usuario or "").strip().lower()
        for reg in datos.get("usuarios", []):
            if str(reg.get("usuario", "")).strip().lower() == clave:
                return reg
        return None

    def _exigir_admin(self, actor: SesionAutenticada) -> None:
        if not isinstance(actor, SesionAutenticada) or not actor.es_admin:
            raise ErrorSeguridad("Acción restringida al perfil 'Administrador'.")

    def _construir_registro_usuario(
        self,
        usuario: str,
        nombre_completo: str,
        contrasena: str,
        perfil: str,
        rol_auditoria: str | None = None,
    ) -> dict[str, Any]:
        u_limpio = _validar_usuario(usuario)
        nom_limpio = _validar_nombre_completo(nombre_completo)
        if perfil not in PERFILES_VALIDOS:
            raise ErrorSeguridad(f"Perfil inválido: {perfil!r}. Válidos: {', '.join(PERFILES_VALIDOS)}.")
        rol_extra = (rol_auditoria or "").strip() or None
        if rol_extra is not None and rol_extra not in PERFILES_AUDITORIA:
            raise ErrorSeguridad(
                f"Rol de auditoría inválido: {rol_extra!r}. Válidos: {', '.join(PERFILES_AUDITORIA)}."
            )
        validar_politica_contrasena(contrasena)

        semilla, pub = generar_par_ed25519()
        ahora = _ahora_iso()
        return {
            "usuario": u_limpio,
            "nombre_completo": nom_limpio,
            "perfil": perfil,
            "rol_auditoria": rol_extra,
            "activo": True,
            "clave_publica_b64": base64.b64encode(pub).decode("ascii"),
            "huella_clave": huella_clave_publica(pub),
            "contrasena_hash": hashear_contrasena(contrasena),
            "clave_privada_cifrada": cifrar_clave_privada(semilla, contrasena),
            "intentos_fallidos": 0,
            "bloqueado_hasta_utc": None,
            "ultimo_intento_fallido_utc": None,
            "ultimo_acceso_utc": None,
            "creado_utc": ahora,
            "actualizado_utc": ahora,
        }

    def _sanitizar_usuario(self, reg: dict[str, Any], ahora: datetime | None = None) -> dict[str, Any]:
        ref = ahora or _ahora_utc()
        bloqueo_dt = _parsear_iso(reg.get("bloqueado_hasta_utc"))
        bloqueado = bool(bloqueo_dt and ref < bloqueo_dt)
        return {
            "usuario": reg["usuario"],
            "nombre_completo": reg["nombre_completo"],
            "perfil": reg["perfil"],
            "rol_auditoria": reg.get("rol_auditoria"),
            "activo": bool(reg.get("activo", True)),
            "huella_clave": reg["huella_clave"],
            "clave_publica_b64": reg["clave_publica_b64"],
            "bloqueado": bloqueado,
            "bloqueado_hasta_utc": reg.get("bloqueado_hasta_utc") if bloqueado else None,
            "intentos_fallidos": int(reg.get("intentos_fallidos", 0)),
            "creado_utc": reg.get("creado_utc", ""),
            "ultimo_acceso_utc": reg.get("ultimo_acceso_utc"),
        }

    # --- Integridad de identidades (perfiles, roles, claves públicas y políticas) ----------------

    @staticmethod
    def _contenido_identidad(datos: dict[str, Any]) -> bytes:
        """Lo que solo un Administrador puede cambiar. Excluye contadores de login y la contraseña
        (que el propio usuario cambia; sin su clave privada no sirve para firmar)."""
        usuarios = sorted(
            (
                {
                    "usuario": str(u.get("usuario", "")).lower(),
                    "nombre_completo": u.get("nombre_completo"),
                    "perfil": u.get("perfil"),
                    "rol_auditoria": u.get("rol_auditoria"),
                    "activo": bool(u.get("activo", True)),
                    "clave_publica_b64": u.get("clave_publica_b64"),
                }
                for u in datos.get("usuarios", [])
            ),
            key=lambda x: x["usuario"],
        )
        contenido = {"politicas": datos.get("politicas", {}), "usuarios": usuarios}
        return json.dumps(contenido, sort_keys=True, ensure_ascii=False).encode("utf-8")

    def _firmar_identidad(self, datos: dict[str, Any], admin_usuario: str, semilla_admin: bytes) -> None:
        reg_admin = self._buscar_usuario(datos, admin_usuario)
        if reg_admin is None or reg_admin.get("perfil") != PERFIL_ADMIN:
            raise ErrorSeguridad("Solo un Administrador registrado puede firmar la configuración de usuarios.")
        firma = firmar_ed25519(semilla_admin, self._contenido_identidad(datos))
        datos["firma_identidad"] = {
            "algoritmo": "Ed25519",
            "administrador": reg_admin["usuario"],
            "huella_clave": reg_admin["huella_clave"],
            "fecha_utc": _ahora_iso(),
            "firma_b64": base64.b64encode(firma).decode("ascii"),
        }

    def estado_integridad(self) -> dict[str, Any]:
        """Verifica que perfiles, roles, claves públicas y políticas no se editaron fuera de la aplicación.

        estado: 'firmado' (íntegro), 'sin_firma' (archivo de una versión anterior; se firma en la próxima
        acción del Administrador) o 'alterado'.
        """
        if not self.ruta_usuarios.exists():
            return {"estado": "sin_configuracion", "motivo": "No hay usuarios configurados."}
        datos = self._leer_almacen()
        firma = datos.get("firma_identidad")
        if not firma:
            return {
                "estado": "sin_firma",
                "motivo": "usuarios.json no tiene firma de integridad (creado con una versión anterior).",
            }
        try:
            reg_admin = self._buscar_usuario(datos, str(firma.get("administrador", "")))
            if reg_admin is None or reg_admin.get("perfil") != PERFIL_ADMIN:
                raise ValueError("el administrador firmante ya no es Administrador")
            pub = base64.b64decode(str(reg_admin["clave_publica_b64"]), validate=True)
            if huella_clave_publica(pub) != firma.get("huella_clave"):
                raise ValueError("la clave del administrador firmante cambió")
            sig = base64.b64decode(str(firma["firma_b64"]), validate=True)
            if not verificar_ed25519(pub, self._contenido_identidad(datos), sig):
                raise ValueError("la firma no corresponde al contenido")
        except Exception as exc:  # noqa: BLE001
            return {
                "estado": "alterado",
                "motivo": f"usuarios.json fue modificado fuera de Folio Auditor ({exc}).",
            }
        return {"estado": "firmado", "motivo": f"Firmado por {firma['administrador']}.", "administrador": firma["administrador"]}

    def _exigir_integridad(self) -> None:
        est = self.estado_integridad()
        if est["estado"] == "alterado":
            self._bitacora("sistema").registrar("usuarios_alterados", motivo=est["motivo"])
            raise ErrorSeguridad(
                est["motivo"] + " Por seguridad no se permite iniciar sesión ni firmar; restaure el archivo "
                "desde un respaldo o reinicialice la seguridad."
            )

    def existe_configuracion(self) -> bool:
        if not self.ruta_usuarios.exists():
            return False
        datos = self._leer_almacen()
        return bool(datos.get("usuarios"))

    def politicas(self) -> dict[str, Any]:
        return dict(self._leer_almacen()["politicas"])

    def inicializar_firma(
        self,
        admin_usuario: str,
        admin_nombre: str,
        admin_contrasena: str,
        preparador: dict[str, Any] | None = None,
        segregacion_estricta: bool = True,
    ) -> dict[str, Any]:
        """Configura el primer Administrador, opcionalmente un Preparador inicial y las políticas base."""
        if self.existe_configuracion():
            raise ErrorSeguridad("La configuración inicial de seguridad ya existe.")

        usuarios_nuevos: list[dict[str, Any]] = []
        reg_admin = self._construir_registro_usuario(
            admin_usuario,
            admin_nombre,
            admin_contrasena,
            PERFIL_ADMIN,
        )
        usuarios_nuevos.append(reg_admin)

        reg_prep: dict[str, Any] | None = None
        if preparador is not None:
            if not isinstance(preparador, dict):
                raise ErrorSeguridad("Los datos del Preparador inicial deben entregarse como diccionario.")
            prep_usr = _validar_usuario(str(preparador.get("usuario", "")))
            if prep_usr.lower() == reg_admin["usuario"].lower():
                raise ErrorSeguridad("El usuario Preparador inicial debe ser distinto al Administrador.")
            reg_prep = self._construir_registro_usuario(
                prep_usr,
                str(preparador.get("nombre_completo", "")),
                str(preparador.get("contrasena", "")),
                PERFIL_PREPARADOR,
            )
            usuarios_nuevos.append(reg_prep)

        politicas = dict(_POLITICAS_DEFECTO)
        politicas["segregacion_estricta"] = bool(segregacion_estricta)
        datos = {
            "version": 1,
            "politicas": politicas,
            "usuarios": usuarios_nuevos,
        }
        semilla_admin = descifrar_clave_privada(reg_admin["clave_privada_cifrada"], admin_contrasena)
        self._firmar_identidad(datos, reg_admin["usuario"], semilla_admin)
        self._guardar_almacen(datos)

        bit = self._bitacora(reg_admin["usuario"])
        bit.registrar(
            "inicializacion_seguridad",
            administrador=reg_admin["usuario"],
            segregacion_estricta=politicas["segregacion_estricta"],
            preparador_inicial=reg_prep["usuario"] if reg_prep else None,
        )
        bit.registrar(
            "usuario_creado",
            actor=reg_admin["usuario"],
            usuario_objetivo=reg_admin["usuario"],
            perfil=PERFIL_ADMIN,
            huella_clave=reg_admin["huella_clave"],
        )
        if reg_prep is not None:
            bit.registrar(
                "usuario_creado",
                actor=reg_admin["usuario"],
                usuario_objetivo=reg_prep["usuario"],
                perfil=PERFIL_PREPARADOR,
                huella_clave=reg_prep["huella_clave"],
            )

        return {
            "politicas": dict(politicas),
            "usuarios": self.listar_usuarios(),
        }

    def crear_usuario(
        self,
        actor: SesionAutenticada,
        usuario: str,
        nombre_completo: str,
        contrasena: str,
        perfil: str,
        rol_auditoria_extra: str | None = None,
    ) -> dict[str, Any]:
        """Crea un usuario nuevo; requiere sesión activa de Administrador."""
        self._exigir_admin(actor)
        self._exigir_integridad()
        if not self.existe_configuracion():
            raise ErrorSeguridad("Debes inicializar la configuración de seguridad antes de crear usuarios.")

        datos = self._leer_almacen()
        u_limpio = _validar_usuario(usuario)
        if self._buscar_usuario(datos, u_limpio) is not None:
            raise ErrorSeguridad(f"Ya existe un usuario registrado con el identificador '{u_limpio}'.")

        nuevo = self._construir_registro_usuario(
            u_limpio,
            nombre_completo,
            contrasena,
            perfil,
            rol_auditoria=rol_auditoria_extra,
        )
        datos["usuarios"].append(nuevo)
        self._firmar_identidad(datos, actor.usuario, _semilla_de(actor))
        self._guardar_almacen(datos)

        self._bitacora(actor.usuario).registrar(
            "usuario_creado",
            actor=actor.usuario,
            usuario_objetivo=nuevo["usuario"],
            perfil=nuevo["perfil"],
            rol_auditoria=nuevo.get("rol_auditoria"),
            huella_clave=nuevo["huella_clave"],
        )
        return self._sanitizar_usuario(nuevo)

    def autenticar(self, usuario: str, contrasena: str, modo_acceso: str | None = None) -> SesionAutenticada:
        """Autentica credenciales locales, valida modo de acceso y descifra la llave Ed25519 en memoria."""
        if not self.existe_configuracion():
            raise ErrorSeguridad("La seguridad de Folio Auditor aún no ha sido inicializada.")

        modos_validos = (None, PERFIL_ADMIN, PERFIL_PREPARADOR, "Auditor", PERFIL_REVISOR, PERFIL_SOCIO)
        if modo_acceso not in modos_validos:
            raise ErrorSeguridad(f"Modo de acceso inválido: {modo_acceso!r}.")

        self._exigir_integridad()
        datos = self._leer_almacen()
        politicas = datos["politicas"]
        max_intentos = int(politicas.get("max_intentos", MAX_INTENTOS_FALLIDOS))
        bloqueo_min = int(politicas.get("bloqueo_minutos", BLOQUEO_MINUTOS))

        u_txt = (usuario or "").strip() if isinstance(usuario, str) else ""
        reg = self._buscar_usuario(datos, u_txt)
        if reg is None:
            # Mismo costo que con un usuario real para no revelar por tiempo qué usuarios existen.
            verificar_contrasena(contrasena if isinstance(contrasena, str) else "", _registro_senuelo())
            self._bitacora(u_txt or "desconocido").registrar(
                "login_fallido",
                usuario_intentado=u_txt,
                motivo="usuario_no_encontrado",
                modo_acceso=modo_acceso,
            )
            raise ErrorSeguridad("Usuario o contraseña inválidos.")

        u_id = reg["usuario"]
        if not reg.get("activo", True):
            self._bitacora(u_id).registrar("login_rechazado_inactivo", usuario=u_id, modo_acceso=modo_acceso)
            raise ErrorSeguridad("La cuenta está desactivada. Contacta al Administrador.")

        ahora = _ahora_utc()
        bloqueo_dt = _parsear_iso(reg.get("bloqueado_hasta_utc"))
        if bloqueo_dt is not None:
            if ahora < bloqueo_dt:
                self._bitacora(u_id).registrar(
                    "login_bloqueado",
                    usuario=u_id,
                    bloqueado_hasta_utc=reg["bloqueado_hasta_utc"],
                    modo_acceso=modo_acceso,
                )
                raise ErrorSeguridad(
                    f"Cuenta bloqueada temporalmente por múltiples intentos fallidos (hasta {reg['bloqueado_hasta_utc']})."
                )
            reg["intentos_fallidos"] = 0
            reg["bloqueado_hasta_utc"] = None
            reg["ultimo_intento_fallido_utc"] = None

        ultimo_fallo_dt = _parsear_iso(reg.get("ultimo_intento_fallido_utc"))
        if ultimo_fallo_dt is not None and (ahora - ultimo_fallo_dt) > timedelta(minutes=bloqueo_min):
            reg["intentos_fallidos"] = 0

        if not isinstance(contrasena, str) or not verificar_contrasena(contrasena, reg.get("contrasena_hash", {})):
            intentos = int(reg.get("intentos_fallidos", 0)) + 1
            reg["intentos_fallidos"] = intentos
            reg["ultimo_intento_fallido_utc"] = ahora.isoformat(timespec="seconds")
            if intentos >= max_intentos:
                hasta = (ahora + timedelta(minutes=bloqueo_min)).isoformat(timespec="seconds")
                reg["bloqueado_hasta_utc"] = hasta
                self._guardar_almacen(datos)
                self._bitacora(u_id).registrar(
                    "cuenta_bloqueada",
                    usuario=u_id,
                    intentos_fallidos=intentos,
                    bloqueado_hasta_utc=hasta,
                    modo_acceso=modo_acceso,
                )
                raise ErrorSeguridad(
                    f"Cuenta bloqueada durante {bloqueo_min} minutos tras alcanzar {max_intentos} intentos fallidos."
                )
            self._guardar_almacen(datos)
            self._bitacora(u_id).registrar(
                "login_fallido",
                usuario=u_id,
                intentos_fallidos=intentos,
                motivo="contrasena_incorrecta",
                modo_acceso=modo_acceso,
            )
            raise ErrorSeguridad("Usuario o contraseña inválidos.")

        perfil = reg["perfil"]
        rol_aud = reg.get("rol_auditoria")
        if modo_acceso == PERFIL_ADMIN and perfil != PERFIL_ADMIN:
            self._bitacora(u_id).registrar(
                "login_modo_no_autorizado",
                usuario=u_id,
                perfil=perfil,
                modo_acceso=modo_acceso,
            )
            raise ErrorSeguridad(f"El perfil '{perfil}' no puede ingresar en modo Administrador.")
        if modo_acceso in (PERFIL_PREPARADOR, "Auditor") and perfil not in PERFILES_AUDITORIA:
            self._bitacora(u_id).registrar(
                "login_modo_no_autorizado",
                usuario=u_id,
                perfil=perfil,
                modo_acceso=modo_acceso,
            )
            raise ErrorSeguridad(f"El perfil '{perfil}' debe ingresar en modo Administrador.")
        if modo_acceso in (PERFIL_REVISOR, PERFIL_SOCIO) and perfil != modo_acceso and rol_aud != modo_acceso:
            self._bitacora(u_id).registrar(
                "login_modo_no_autorizado",
                usuario=u_id,
                perfil=perfil,
                modo_acceso=modo_acceso,
            )
            raise ErrorSeguridad(f"El usuario '{u_id}' no corresponde al modo '{modo_acceso}'.")

        semilla = descifrar_clave_privada(reg["clave_privada_cifrada"], contrasena)
        if clave_publica_ed25519(semilla) != base64.b64decode(str(reg["clave_publica_b64"])):
            self._bitacora(u_id).registrar("clave_privada_no_corresponde", usuario=u_id)
            raise ErrorSeguridad(
                "La clave privada guardada no corresponde a la clave pública registrada: usuarios.json fue alterado."
            )
        if requiere_migracion_scrypt(reg.get("contrasena_hash")) or requiere_migracion_scrypt(
            reg.get("clave_privada_cifrada")
        ):
            # Sube el costo scrypt de registros antiguos (2^14 -> vigente) con la contraseña recién verificada.
            n_anterior = int((reg.get("contrasena_hash") or {}).get("n", 0) or 0)
            reg["contrasena_hash"] = hashear_contrasena(contrasena)
            reg["clave_privada_cifrada"] = cifrar_clave_privada(semilla, contrasena)
            self._bitacora(u_id).registrar(
                "migracion_kdf", usuario=u_id, n_anterior=n_anterior, n_nuevo=reg["contrasena_hash"]["n"]
            )
        ahora_iso = ahora.isoformat(timespec="seconds")
        reg["intentos_fallidos"] = 0
        reg["bloqueado_hasta_utc"] = None
        reg["ultimo_intento_fallido_utc"] = None
        reg["ultimo_acceso_utc"] = ahora_iso
        if perfil == PERFIL_ADMIN and not datos.get("firma_identidad"):
            # Archivo de una versión anterior: el primer Administrador que entra lo firma.
            self._firmar_identidad(datos, u_id, semilla)
            self._bitacora(u_id).registrar("usuarios_firmados", administrador=u_id)
        self._guardar_almacen(datos)

        self._bitacora(u_id).registrar(
            "login_exitoso",
            usuario=u_id,
            perfil=perfil,
            modo_acceso=modo_acceso or "general",
            huella_clave=reg["huella_clave"],
        )
        return SesionAutenticada(
            usuario=u_id,
            nombre_completo=reg["nombre_completo"],
            perfil=perfil,
            rol_auditoria=rol_aud,
            clave_publica_b64=reg["clave_publica_b64"],
            huella_clave=reg["huella_clave"],
            fecha_login_utc=ahora_iso,
            _semilla_privada=semilla,
        )

    def cambiar_contrasena(self, usuario: str, contrasena_actual: str, contrasena_nueva: str) -> None:
        """Cambia la contraseña del usuario re-cifrando la misma semilla Ed25519 (conserva su clave pública)."""
        if not self.existe_configuracion():
            raise ErrorSeguridad("La seguridad aún no ha sido inicializada.")
        datos = self._leer_almacen()
        reg = self._buscar_usuario(datos, usuario)
        if reg is None:
            raise ErrorSeguridad("Usuario no encontrado.")
        if not reg.get("activo", True):
            raise ErrorSeguridad("La cuenta está desactivada.")
        if not isinstance(contrasena_actual, str) or not verificar_contrasena(
            contrasena_actual, reg.get("contrasena_hash", {})
        ):
            raise ErrorSeguridad("La contraseña actual es incorrecta.")

        validar_politica_contrasena(contrasena_nueva)
        semilla = descifrar_clave_privada(reg["clave_privada_cifrada"], contrasena_actual)
        reg["contrasena_hash"] = hashear_contrasena(contrasena_nueva)
        reg["clave_privada_cifrada"] = cifrar_clave_privada(semilla, contrasena_nueva)
        reg["actualizado_utc"] = _ahora_iso()
        self._guardar_almacen(datos)

        self._bitacora(reg["usuario"]).registrar(
            "cambio_contrasena",
            usuario=reg["usuario"],
            huella_clave=reg["huella_clave"],
        )

    def restablecer_contrasena_admin(
        self,
        actor: SesionAutenticada,
        usuario_objetivo: str,
        nueva_contrasena: str,
    ) -> None:
        """Restablece contraseña y desbloquea cuenta desde Administrador, rotando el par Ed25519."""
        self._exigir_admin(actor)
        self._exigir_integridad()
        if not self.existe_configuracion():
            raise ErrorSeguridad("La seguridad aún no ha sido inicializada.")
        validar_politica_contrasena(nueva_contrasena)

        datos = self._leer_almacen()
        reg = self._buscar_usuario(datos, usuario_objetivo)
        if reg is None:
            raise ErrorSeguridad(f"No existe el usuario '{usuario_objetivo}'.")

        huella_prev = reg["huella_clave"]
        nueva_semilla, nueva_pub = generar_par_ed25519()
        nueva_huella = huella_clave_publica(nueva_pub)

        reg["clave_publica_b64"] = base64.b64encode(nueva_pub).decode("ascii")
        reg["huella_clave"] = nueva_huella
        reg["contrasena_hash"] = hashear_contrasena(nueva_contrasena)
        reg["clave_privada_cifrada"] = cifrar_clave_privada(nueva_semilla, nueva_contrasena)
        reg["intentos_fallidos"] = 0
        reg["bloqueado_hasta_utc"] = None
        reg["ultimo_intento_fallido_utc"] = None
        reg["actualizado_utc"] = _ahora_iso()
        self._firmar_identidad(datos, actor.usuario, _semilla_de(actor))
        self._guardar_almacen(datos)

        self._bitacora(actor.usuario).registrar(
            "restablecimiento_contrasena_admin",
            actor=actor.usuario,
            usuario_objetivo=reg["usuario"],
            huella_anterior=huella_prev,
            huella_nueva=nueva_huella,
        )

    def cambiar_estado_usuario(self, actor: SesionAutenticada, usuario_objetivo: str, activo: bool) -> None:
        """Activa o desactiva un usuario protegiendo que quede al menos un Administrador activo."""
        self._exigir_admin(actor)
        self._exigir_integridad()
        if not self.existe_configuracion():
            raise ErrorSeguridad("La seguridad aún no ha sido inicializada.")

        datos = self._leer_almacen()
        reg = self._buscar_usuario(datos, usuario_objetivo)
        if reg is None:
            raise ErrorSeguridad(f"No existe el usuario '{usuario_objetivo}'.")

        nuevo_estado = bool(activo)
        if not nuevo_estado and reg["perfil"] == PERFIL_ADMIN and reg.get("activo", True):
            admins_activos = sum(
                1
                for u in datos["usuarios"]
                if u.get("perfil") == PERFIL_ADMIN and u.get("activo", True)
            )
            if admins_activos <= 1:
                raise ErrorSeguridad("No se puede desactivar al último Administrador activo.")

        reg["activo"] = nuevo_estado
        reg["actualizado_utc"] = _ahora_iso()
        self._firmar_identidad(datos, actor.usuario, _semilla_de(actor))
        self._guardar_almacen(datos)

        self._bitacora(actor.usuario).registrar(
            "cambio_estado_usuario",
            actor=actor.usuario,
            usuario_objetivo=reg["usuario"],
            activo=nuevo_estado,
        )

    def actualizar_politicas(self, actor: SesionAutenticada, **cambios: Any) -> dict[str, Any]:
        """Actualiza las políticas locales de seguridad; solo permitido para Administrador."""
        self._exigir_admin(actor)
        self._exigir_integridad()
        if not self.existe_configuracion():
            raise ErrorSeguridad("La seguridad aún no ha sido inicializada.")

        datos = self._leer_almacen()
        politicas = dict(datos["politicas"])
        permitidas = set(_POLITICAS_DEFECTO.keys())
        desconocidas = set(cambios.keys()) - permitidas
        if desconocidas:
            raise ErrorSeguridad(f"Políticas desconocidas: {', '.join(sorted(desconocidas))}.")

        for clave, valor in cambios.items():
            if clave in ("segregacion_estricta", "alerta_nube"):
                if not isinstance(valor, bool):
                    raise ErrorSeguridad(f"La política '{clave}' debe ser booleana.")
                politicas[clave] = valor
            elif clave in ("ventana_archivo_dias", "max_intentos", "bloqueo_minutos"):
                if isinstance(valor, bool) or not isinstance(valor, int) or valor < 1:
                    raise ErrorSeguridad(f"La política '{clave}' debe ser un entero positivo.")
                politicas[clave] = valor

        datos["politicas"] = politicas
        self._firmar_identidad(datos, actor.usuario, _semilla_de(actor))
        self._guardar_almacen(datos)

        self._bitacora(actor.usuario).registrar(
            "politicas_actualizadas",
            actor=actor.usuario,
            cambios=cambios,
            politicas=politicas,
        )
        return dict(politicas)

    def listar_usuarios(self) -> list[dict[str, Any]]:
        """Lista los usuarios registrados sin exponer hashes ni llaves privadas cifradas."""
        datos = self._leer_almacen()
        ahora = _ahora_utc()
        return [self._sanitizar_usuario(reg, ahora=ahora) for reg in datos.get("usuarios", [])]

    def registro_claves(self) -> dict[str, dict[str, Any]]:
        """Registro público de claves de firma: {huella: {usuario, nombre_completo, perfil, rol_auditoria, activo, clave_publica_b64}}.

        Sirve de ancla para `verificar_sello_corrida(..., claves_registradas=...)` y se puede exportar
        a un auditor externo (no contiene hashes de contraseña ni llaves privadas).
        """
        if not self.ruta_usuarios.exists():
            return {}
        self._exigir_integridad()
        registro: dict[str, dict[str, Any]] = {}
        for u in self.listar_usuarios():
            registro[u["huella_clave"]] = {
                "usuario": u["usuario"],
                "nombre_completo": u["nombre_completo"],
                "perfil": u["perfil"],
                "rol_auditoria": u.get("rol_auditoria"),
                "activo": u["activo"],
                "clave_publica_b64": u["clave_publica_b64"],
            }
        return registro

    def leer_bitacora_accesos(self) -> tuple[list[dict[str, Any]], bool]:
        """Lee los eventos de `bitacora_accesos.jsonl` y verifica su cadena SHA-256."""
        if not self.ruta_bitacora.exists():
            return [], True
        bit = self._bitacora()
        return bit.leer(), bit.verificar()

    def puede_firmar_rol(self, sesion: SesionAutenticada, rol: str) -> bool:
        """Verifica si una sesión autenticada puede firmar el rol de auditoría solicitado."""
        return puede_firmar_rol(sesion, rol)


def verificar_sello_anclado(carpeta: str | Path, ruta_base: str | Path | None = None) -> dict[str, Any]:
    """Verifica el sello de una corrida anclando la clave al registro local de usuarios, si existe.

    Si la firma tiene usuarios configurados, una clave no registrada invalida el sello. Si no los tiene,
    el resultado queda con `firmante_verificado = None` para que la interfaz lo advierta.
    """
    from motor.cripto import verificar_sello_corrida

    try:
        registro = GestorUsuarios(ruta_base).registro_claves()
    except ErrorSeguridad as exc:
        return {
            "valido": False, "motivo": str(exc), "detalle": {}, "huella_clave": "", "usuario": "", "rol": "",
            "firmante_verificado": False,
        }
    return verificar_sello_corrida(carpeta, claves_registradas=registro or None)


def texto_estado_sello(res: dict[str, Any]) -> str:
    """Etiqueta corta y honesta del resultado de verificación de sello."""
    if not res.get("valido"):
        return "INVÁLIDO"
    if res.get("firmante_verificado"):
        return "VÁLIDO"
    return "ÍNTEGRO, FIRMANTE SIN VERIFICAR"
