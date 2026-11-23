"""Privacidad, bóveda cifrada en reposo (AES-256-GCM / DPAPI) y cumplimiento Ley 81 (Ficha 22 · Oleada 3)."""
from __future__ import annotations

import base64
import binascii
from collections import Counter
from datetime import datetime, timezone
import getpass
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import tomllib
from typing import Any

from .bitacora import Bitacora
from .cripto import (
    cifrar_aes_gcm,
    derivar_clave_scrypt,
    descifrar_aes_gcm,
    desproteger_dpapi,
    proteger_dpapi,
)
from .seguridad import ErrorSeguridad

SUFIJO_BOVEDA = ".folioenc"
_BLOQUE_BORRADO = 65_536
_SCRYPT_N = 16384
_SCRYPT_R = 8
_SCRYPT_P = 1

_PROVEEDORES_NUBE: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("OneDrive", ("onedrive",)),
    ("Dropbox", ("dropbox",)),
    ("Google Drive", ("google drive", "googledrive", "my drive", "mi unidad")),
    ("iCloud Drive", ("iclouddrive", "icloud drive")),
    ("Box", ("box", "box sync", "box drive")),
)

_RE_EMAIL = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
_RE_RUC_PA = re.compile(
    r"(?i)(?<![\w-])\d{4,10}-\d{1,4}-\d{4,7}(?:\s*[,/-]?\s*(?:DV|D\.V\.)[:\s-]*\d{1,2})?(?!-\d)(?![\w])"
)
_RE_CEDULA_PA = re.compile(
    r"(?i)(?<![\w-])(?:(?:PE|E|N|PI|AV)-\d{1,4}-\d{1,6}|(?:1[0-3]|[1-9])(?:-(?:AV|PI|NT))?-\d{1,5}-\d{1,6})"
    r"(?:\s*[,/-]?\s*(?:DV|D\.V\.)[:\s-]*\d{1,2})?(?!-\d)(?![\w])"
)
_RE_FECHA_ISO = re.compile(r"^(?:19|20)\d{2}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])$")
_RE_CUENTA_GUIONES = re.compile(r"\b\d{2,4}(?:-\d{2,6}){2,4}(?:-\d{1,2})?\b")
_RE_CUENTA_DIGITOS = re.compile(r"\b\d{10,}\b")
_RE_TELEFONO_INTL = re.compile(
    r"(?:\+\d{1,3}[\s.-]?)(?:\(\d{2,4}\)[\s.-]?)?\d{3,4}(?:[\s.-]\d{3,4}){1,2}\b"
    r"|\(\d{3,4}\)[\s.-]?\d{3,4}[\s.-]\d{4}\b"
)
_RE_TELEFONO_ETIQUETA = re.compile(
    r"(?i)(\b(?:tel(?:[eé]fono)?|cel(?:ular)?|m[oó]vil|fax|phone)[:.\s#]+)\d{3,4}(?:[\s.-]\d{3,4}){1,2}\b"
)
_RE_TELEFONO_LOCAL_PA = re.compile(r"\b(?:6\d{3}|[2379]\d{2})-\d{4}\b")

_RE_RUTA_WIN_EXT = re.compile(
    r"(?i)[A-Z]:[\\/][^\r\n,;\"'<>|]*?\.[A-Za-z0-9]{1,8}(?=$|[\s,;\"'<>|])"
)
_RE_RUTA_WIN = re.compile(r"(?i)[A-Z]:[\\/][^\s,;\"'<>|]+")
_RE_RUTA_POSIX_EXT = re.compile(
    r"/(?:Users|home|tmp|var|opt|etc)/[^\r\n,;\"'<>|]*?\.[A-Za-z0-9]{1,8}(?=$|[\s,;\"'<>|])"
)
_RE_RUTA_POSIX = re.compile(r"/(?:Users|home|tmp|var|opt|etc)/[^\s,;\"'<>|]+")
_RE_MONTO = re.compile(
    r"(?:B/\.|\$|USD|PAB)\s*-?\d[\d,]*(?:\.\d{1,2})?|\b\d{1,3}(?:,\d{3})+(?:\.\d{2})?\b|\b\d+\.\d{2}(?!\.\d)\b"
)
_RE_FECHA_CARPETA_COMPLETA = re.compile(r"^(\d{8})-(\d{6})(?:[-_].*)?$")
_RE_FECHA_CARPETA_DIA = re.compile(r"^(\d{8})(?:[-_].*)?$")

_CLAVES_NUMERICAS_SENSIBLES = frozenset({
    "monto",
    "montos",
    "importe",
    "debe",
    "haber",
    "saldo",
    "saldo_inicial",
    "saldo_final",
    "saldo_calculado",
    "saldo_final_objetivo",
    "suma_monto",
    "suma_debito",
    "suma_credito",
    "min_monto",
    "max_monto",
    "materialidad",
    "materialidad_ejecucion",
    "umbral_trivial",
    "umbral_aprobacion",
    "diferencia",
    "valor",
})
_CLAVES_HASH_TECNICO = frozenset({"sha256", "sql_sha256", "huella_clave", "ultimo_hash"})


# ---------------------------------------------------------------------------
# 1. Bóveda cifrada en reposo (AES-256-GCM + DPAPI)
# ---------------------------------------------------------------------------


def _validar_modalidad_boveda(contrasena: str | None, usar_dpapi: bool) -> bool:
    """Valida que se especifique exactamente una modalidad: contraseña no vacía o DPAPI."""
    if contrasena is not None and not isinstance(contrasena, str):
        raise ErrorSeguridad("La contraseña de la bóveda debe ser texto.")
    tiene_contrasena = isinstance(contrasena, str) and len(contrasena) > 0
    if tiene_contrasena == bool(usar_dpapi):
        raise ErrorSeguridad(
            "Debe indicar exactamente una modalidad de cifrado: contraseña no vacía o usar_dpapi=True."
        )
    return bool(usar_dpapi)


def _decodificar_b64(valor: Any, nombre_campo: str) -> bytes:
    if not isinstance(valor, str) or not valor:
        raise ErrorSeguridad(f"Campo {nombre_campo!r} ausente o inválido en contenedor cifrado.")
    try:
        return base64.b64decode(valor.encode("ascii"), validate=True)
    except (ValueError, UnicodeEncodeError, binascii.Error) as exc:
        raise ErrorSeguridad(f"Codificación Base64 inválida en {nombre_campo!r}.") from exc


def _sobrescribir_y_eliminar(ruta: Path) -> None:
    """Sobrescribe el archivo original con ceros antes de eliminarlo del disco."""
    tamano = ruta.stat().st_size
    if tamano > 0:
        bloque = b"\x00" * min(_BLOQUE_BORRADO, tamano)
        with ruta.open("r+b") as f:
            restante = tamano
            while restante > 0:
                trozo = bloque if restante >= len(bloque) else b"\x00" * restante
                f.write(trozo)
                restante -= len(trozo)
            f.flush()
            os.fsync(f.fileno())
    ruta.unlink()


def cifrar_archivo_boveda(
    ruta_origen: str | Path,
    ruta_destino: str | Path | None = None,
    contrasena: str | None = None,
    usar_dpapi: bool = False,
    borrar_origen: bool = False,
) -> Path:
    """Cifra un archivo regular en reposo con AES-256-GCM usando scrypt o Windows DPAPI."""
    en_dpapi = _validar_modalidad_boveda(contrasena, usar_dpapi)
    origen = Path(ruta_origen)
    if not origen.exists() or not origen.is_file():
        raise ErrorSeguridad(f"El archivo de origen no existe o no es un archivo regular: {origen}")

    destino = (
        Path(ruta_destino)
        if ruta_destino is not None
        else origen.with_name(origen.name + SUFIJO_BOVEDA)
    )
    if borrar_origen and destino.resolve() == origen.resolve():
        raise ErrorSeguridad("La ruta cifrada de destino no puede coincidir con el origen al usar borrar_origen=True.")

    datos = origen.read_bytes()
    aad = origen.name.encode("utf-8")

    contenedor: dict[str, Any] = {
        "version": 1,
        "formato": "folio-boveda-v1",
        "nombre_origen": origen.name,
        "fecha_cifrado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    if en_dpapi:
        clave_32b = secrets.token_bytes(32)
        clave_protegida = proteger_dpapi(clave_32b)
        contenedor["modo"] = "dpapi"
        contenedor["clave_dpapi_b64"] = base64.b64encode(clave_protegida).decode("ascii")
    else:
        assert contrasena is not None
        sal = secrets.token_bytes(16)
        clave_32b = derivar_clave_scrypt(
            contrasena, sal, largo=32, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P
        )
        contenedor["modo"] = "scrypt"
        contenedor["sal_b64"] = base64.b64encode(sal).decode("ascii")
        contenedor["scrypt_n"] = _SCRYPT_N
        contenedor["scrypt_r"] = _SCRYPT_R
        contenedor["scrypt_p"] = _SCRYPT_P

    paquete = cifrar_aes_gcm(clave_32b, datos, aad=aad)
    contenedor.update(paquete)

    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(contenedor, indent=2, ensure_ascii=False), encoding="utf-8")

    if borrar_origen:
        _sobrescribir_y_eliminar(origen)

    return destino


def descifrar_archivo_boveda(
    ruta_cifrada: str | Path,
    ruta_destino: str | Path | None = None,
    contrasena: str | None = None,
) -> Path:
    """Descifra un contenedor .folioenc verificando AAD y autenticidad AES-256-GCM."""
    origen = Path(ruta_cifrada)
    if not origen.exists() or not origen.is_file():
        raise ErrorSeguridad(f"El archivo cifrado no existe o no es un archivo regular: {origen}")

    try:
        contenedor = json.loads(origen.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ErrorSeguridad(f"Contenedor cifrado ilegible o corrupto: {origen.name}") from exc

    if not isinstance(contenedor, dict):
        raise ErrorSeguridad("Estructura inválida en contenedor .folioenc.")

    nombre_origen = contenedor.get("nombre_origen")
    if not isinstance(nombre_origen, str) or not nombre_origen:
        raise ErrorSeguridad("El contenedor .folioenc no registra 'nombre_origen' para validar AAD.")

    modo = contenedor.get("modo")
    if modo == "scrypt":
        if not isinstance(contrasena, str) or not contrasena:
            raise ErrorSeguridad("Se requiere contraseña no vacía para descifrar un contenedor en modo scrypt.")
        sal = _decodificar_b64(contenedor.get("sal_b64"), "sal_b64")
        n = int(contenedor.get("scrypt_n", _SCRYPT_N))
        r = int(contenedor.get("scrypt_r", _SCRYPT_R))
        p = int(contenedor.get("scrypt_p", _SCRYPT_P))
        clave_32b = derivar_clave_scrypt(contrasena, sal, largo=32, n=n, r=r, p=p)
    elif modo == "dpapi":
        clave_dpapi = _decodificar_b64(contenedor.get("clave_dpapi_b64"), "clave_dpapi_b64")
        clave_32b = desproteger_dpapi(clave_dpapi)
    else:
        raise ErrorSeguridad(f"Modalidad de bóveda no soportada: {modo!r}")

    paquete_raw = contenedor.get("paquete") if isinstance(contenedor.get("paquete"), dict) else contenedor
    for campo in ("nonce_b64", "tag_b64", "cifrado_b64"):
        if not isinstance(paquete_raw.get(campo), str):
            raise ErrorSeguridad(f"Falta el campo cifrado {campo!r} en el contenedor .folioenc.")

    texto_plano = descifrar_aes_gcm(clave_32b, paquete_raw, aad=nombre_origen.encode("utf-8"))

    if ruta_destino is not None:
        destino = Path(ruta_destino)
    elif origen.name.lower().endswith(SUFIJO_BOVEDA) and len(origen.name) > len(SUFIJO_BOVEDA):
        destino = origen.with_name(origen.name[: -len(SUFIJO_BOVEDA)])
    else:
        destino = origen.with_suffix(".dec")

    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(texto_plano)
    return destino


def cifrar_carpeta_corrida(
    carpeta: str | Path,
    contrasena: str | None = None,
    usar_dpapi: bool = False,
    borrar_origen: bool = False,
) -> list[Path]:
    """Cifra todos los archivos regulares no cifrados (*.folioenc omitidos) dentro de una carpeta."""
    _validar_modalidad_boveda(contrasena, usar_dpapi)
    raiz = Path(carpeta)
    if not raiz.exists() or not raiz.is_dir():
        raise ErrorSeguridad(f"La carpeta a cifrar no existe o no es un directorio: {raiz}")

    archivos = [
        p
        for p in sorted(raiz.rglob("*"))
        if p.is_file() and p.suffix.lower() != SUFIJO_BOVEDA
    ]
    cifrados: list[Path] = []
    for archivo in archivos:
        cifrados.append(
            cifrar_archivo_boveda(
                archivo,
                contrasena=contrasena,
                usar_dpapi=usar_dpapi,
                borrar_origen=borrar_origen,
            )
        )
    return cifrados


def descifrar_carpeta_corrida(
    carpeta: str | Path,
    contrasena: str | None = None,
) -> list[Path]:
    """Descifra todos los archivos *.folioenc dentro de una carpeta."""
    raiz = Path(carpeta)
    if not raiz.exists() or not raiz.is_dir():
        raise ErrorSeguridad(f"La carpeta a descifrar no existe o no es un directorio: {raiz}")

    archivos = [
        p
        for p in sorted(raiz.rglob("*"))
        if p.is_file() and p.suffix.lower() == SUFIJO_BOVEDA
    ]
    descifrados: list[Path] = []
    for archivo in archivos:
        descifrados.append(descifrar_archivo_boveda(archivo, contrasena=contrasena))
    return descifrados


# ---------------------------------------------------------------------------
# 2. Guardarraíles de entorno Windows
# ---------------------------------------------------------------------------


def detectar_carpeta_sincronizada(ruta: str | Path) -> dict[str, Any]:
    """Detecta si una ruta está ubicada dentro de un proveedor de sincronización en la nube."""
    proveedor_detectado: str | None = None

    # Separar por / y \ explícitamente: Path() solo entiende el separador del sistema actual,
    # y una ruta de Windows (C:\Users\...\OneDrive) analizada en macOS/Linux quedaba como una sola parte.
    partes = [p for p in re.split(r"[\\/]+", str(ruta)) if p]
    for parte in partes:
        limpia = parte.strip().lower()
        if not limpia:
            continue
        if limpia == "onedrive" or limpia.startswith("onedrive - ") or limpia.startswith("onedrive-"):
            proveedor_detectado = "OneDrive"
            break
        if limpia == "dropbox" or limpia.startswith("dropbox ("):
            proveedor_detectado = "Dropbox"
            break
        for nombre_prov, alias_lista in _PROVEEDORES_NUBE:
            if nombre_prov in ("OneDrive", "Dropbox"):
                continue
            if limpia in alias_lista:
                proveedor_detectado = nombre_prov
                break
        if proveedor_detectado is not None:
            break

    if proveedor_detectado is not None:
        return {
            "en_nube": True,
            "proveedor": proveedor_detectado,
            "ruta": str(ruta),
            "recomendacion": (
                f"La ruta está dentro de {proveedor_detectado}. Traslade los datos de auditoría "
                "a un directorio local fuera de sincronización automática (ej. C:\\AuditoriaLocal\\) "
                "para reducir exposición conforme a la Ley 81."
            ),
        }

    return {
        "en_nube": False,
        "proveedor": None,
        "ruta": str(ruta),
        "recomendacion": "Ruta local sin carpeta de sincronización en la nube detectada.",
    }


def aplicar_acl_solo_usuario_actual(ruta: str | Path) -> dict[str, Any]:
    """Restringe permisos de archivo o directorio exclusivamente al usuario actual del sistema."""
    objetivo = Path(ruta)
    if not objetivo.exists():
        return {"aplicado": False, "detalle": f"La ruta no existe: {objetivo}"}

    if os.name == "nt":
        usuario = os.environ.get("USERNAME", "").strip() or getpass.getuser()
        dominio = os.environ.get("USERDOMAIN", "").strip()
        principal = f"{dominio}\\{usuario}" if dominio else usuario
        permiso = f"{principal}:(OI)(CI)F" if objetivo.is_dir() else f"{principal}:F"
        try:
            res = subprocess.run(
                ["icacls", str(objetivo), "/inheritance:r", "/grant:r", permiso],
                shell=False,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            return {"aplicado": False, "detalle": f"No fue posible invocar icacls: {exc}"}

        if res.returncode == 0:
            salida = (res.stdout or "").strip()
            return {
                "aplicado": True,
                "detalle": salida or f"ACL restringida exclusivamente a {principal}.",
            }
        detalle_err = (res.stderr or res.stdout or f"icacls finalizó con código {res.returncode}").strip()
        return {"aplicado": False, "detalle": detalle_err}

    modo = 0o700 if objetivo.is_dir() else 0o600
    try:
        os.chmod(objetivo, modo)
    except OSError as exc:
        return {"aplicado": False, "detalle": f"No se pudo aplicar chmod {oct(modo)}: {exc}"}
    return {"aplicado": True, "detalle": f"Permisos POSIX {oct(modo)} aplicados a {objetivo}."}


def _evaluar_streamlit_toml(ruta_toml: Path) -> tuple[bool, list[str]]:
    if not ruta_toml.exists():
        return False, ["No existe .streamlit/config.toml para validar aislamiento local de la interfaz web."]
    try:
        cfg = tomllib.loads(ruta_toml.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return False, [f"No se pudo leer .streamlit/config.toml: {exc}"]

    srv = cfg.get("server") if isinstance(cfg.get("server"), dict) else {}
    brw = cfg.get("browser") if isinstance(cfg.get("browser"), dict) else {}

    problemas: list[str] = []
    if srv.get("address") != "127.0.0.1":
        problemas.append("server.address no está fijado a '127.0.0.1' en .streamlit/config.toml.")
    if srv.get("enableXsrfProtection") is not True:
        problemas.append("server.enableXsrfProtection no está activo (true) en .streamlit/config.toml.")
    if srv.get("enableCORS") is True:
        problemas.append("server.enableCORS no debe estar habilitado (true) en .streamlit/config.toml.")
    if brw.get("gatherUsageStats") is not False:
        problemas.append("browser.gatherUsageStats no está deshabilitado (false) en .streamlit/config.toml.")
    return len(problemas) == 0, problemas


def evaluar_postura_entorno(ruta_trabajo: str | Path) -> dict[str, Any]:
    """Evalúa la postura local de seguridad y privacidad del directorio de trabajo."""
    raiz = Path(ruta_trabajo)
    nube = detectar_carpeta_sincronizada(raiz)
    hallazgos: list[dict[str, str]] = []

    if nube["en_nube"]:
        hallazgos.append({
            "codigo": "ENT-NUBE",
            "severidad": "ADVERTENCIA",
            "detalle": nube["recomendacion"],
        })

    streamlit_ok, problemas_toml = _evaluar_streamlit_toml(raiz / ".streamlit" / "config.toml")
    for prob in problemas_toml:
        hallazgos.append({
            "codigo": "ENT-WEB",
            "severidad": "ADVERTENCIA",
            "detalle": prob,
        })

    ruta_usuarios = raiz / "seguridad" / "usuarios.json"
    usuarios_configurados = ruta_usuarios.is_file()
    if not usuarios_configurados:
        hallazgos.append({
            "codigo": "ENT-AUTH",
            "severidad": "ADVERTENCIA",
            "detalle": "No se ha inicializado seguridad/usuarios.json para control de acceso local.",
        })

    estado = "OK" if not hallazgos else "ADVERTENCIA"
    resumen = (
        "Postura de entorno conforme: ruta fuera de nube, web local aislada y control de usuarios configurado."
        if estado == "OK"
        else f"Postura con {len(hallazgos)} advertencia(s) de entorno."
    )
    return {
        "estado": estado,
        "ruta_trabajo": str(raiz),
        "nube": nube,
        "streamlit_seguro": streamlit_ok,
        "usuarios_configurados": usuarios_configurados,
        "hallazgos": hallazgos,
        "resumen": resumen,
    }


# ---------------------------------------------------------------------------
# 3. Anonimización PII y retención (Ley 81 de Panamá)
# ---------------------------------------------------------------------------


def _reemplazar_cuenta_si_no_es_fecha(match: re.Match[str]) -> str:
    token = match.group(0)
    if _RE_FECHA_ISO.fullmatch(token):
        return token
    return "[CUENTA]"


def anonimizar_texto_pii(texto: str, terminos_sensibles: list[str] | None = None) -> str:
    """Enmascara PII panameña y términos confidenciales explícitos en texto libre."""
    if texto is None:
        return ""
    resultado = str(texto)

    # 1. Correos primero para evitar sustituciones parciales dentro de direcciones.
    resultado = _RE_EMAIL.sub("[EMAIL]", resultado)

    # 2. Términos sensibles explícitos (del más largo al más corto).
    if terminos_sensibles:
        terminos = sorted(
            {str(t).strip() for t in terminos_sensibles if t is not None and str(t).strip()},
            key=len,
            reverse=True,
        )
        for termino in terminos:
            pref = r"(?<!\w)" if termino[0].isalnum() else ""
            suf = r"(?!\w)" if termino[-1].isalnum() else ""
            patron = f"{pref}{re.escape(termino)}{suf}"
            resultado = re.sub(patron, "[CONFIDENCIAL]", resultado, flags=re.IGNORECASE)

    # 3. Teléfonos con prefijo internacional/área antes de cuentas con guiones.
    resultado = _RE_TELEFONO_INTL.sub("[TELEFONO]", resultado)

    # 4. Identificaciones fiscales y personales de Panamá (RUC y cédula).
    resultado = _RE_RUC_PA.sub("[ID-PA]", resultado)
    resultado = _RE_CEDULA_PA.sub("[ID-PA]", resultado)

    # 5. Cuentas bancarias largas (con guiones o >= 10 dígitos continuos), preservando fechas ISO.
    resultado = _RE_CUENTA_GUIONES.sub(_reemplazar_cuenta_si_no_es_fecha, resultado)
    resultado = _RE_CUENTA_DIGITOS.sub("[CUENTA]", resultado)

    # 6. Teléfonos locales / etiquetados restantes.
    resultado = _RE_TELEFONO_ETIQUETA.sub(r"\1[TELEFONO]", resultado)
    resultado = _RE_TELEFONO_LOCAL_PA.sub("[TELEFONO]", resultado)

    return resultado


def _sanitizar_texto_soporte(texto: str, terminos_sensibles: list[str]) -> str:
    limpio = _RE_RUTA_WIN_EXT.sub("[RUTA]", str(texto))
    limpio = _RE_RUTA_WIN.sub("[RUTA]", limpio)
    limpio = _RE_RUTA_POSIX_EXT.sub("[RUTA]", limpio)
    limpio = _RE_RUTA_POSIX.sub("[RUTA]", limpio)
    limpio = anonimizar_texto_pii(limpio, terminos_sensibles=terminos_sensibles)
    limpio = _RE_MONTO.sub("[MONTO]", limpio)
    return limpio


def _sanitizar_estructura_soporte(valor: Any, terminos_sensibles: list[str], clave: str = "") -> Any:
    clave_low = clave.lower()
    if clave_low in _CLAVES_HASH_TECNICO and isinstance(valor, str):
        return valor
    if clave_low in _CLAVES_NUMERICAS_SENSIBLES:
        return "[MONTO]"
    if clave_low in ("cliente", "usuario", "auditor", "autor", "nombre_completo"):
        return "[CONFIDENCIAL]"
    if isinstance(valor, str):
        return _sanitizar_texto_soporte(valor, terminos_sensibles)
    if isinstance(valor, list):
        return [_sanitizar_estructura_soporte(v, terminos_sensibles, clave=clave) for v in valor]
    if isinstance(valor, dict):
        return {
            str(k): _sanitizar_estructura_soporte(v, terminos_sensibles, clave=str(k))
            for k, v in valor.items()
        }
    return valor


def exportar_diagnostico_anonimizado(
    carpeta_corrida: str | Path,
    destino: str | Path | None = None,
) -> dict[str, Any]:
    """Genera un JSON técnico de soporte desde bitacora.jsonl sin PII, montos ni rutas del usuario."""
    carpeta = Path(carpeta_corrida)
    ruta_bit = carpeta / "bitacora.jsonl"
    if not ruta_bit.exists() or not ruta_bit.is_file():
        raise ErrorSeguridad(f"No se encontró bitacora.jsonl en la carpeta de corrida: {carpeta}")

    bit = Bitacora(ruta_bit)
    registros = bit.leer()
    integra = bit.verificar()

    terminos_set: set[str] = set()
    paquete = ""
    version_motor = ""
    version_paquete = ""
    diag_evento: dict[str, Any] = {}
    conteos_eventos = Counter()
    importaciones: list[dict[str, Any]] = []
    pruebas: list[dict[str, Any]] = []
    observaciones_soporte: list[dict[str, Any]] = []

    for reg in registros:
        evento = str(reg.get("evento", ""))
        conteos_eventos[evento] += 1
        usr_os = reg.get("usuario")
        if isinstance(usr_os, str) and len(usr_os.strip()) >= 3:
            terminos_set.add(usr_os.strip())

        datos = reg.get("datos") if isinstance(reg.get("datos"), dict) else {}
        for clave_pii in ("cliente", "auditor"):
            val = datos.get(clave_pii)
            if isinstance(val, str) and val.strip():
                terminos_set.add(val.strip())

        if evento == "inicio":
            paquete = str(datos.get("paquete") or paquete)
            version_motor = str(datos.get("version_motor") or version_motor)
            version_paquete = str(datos.get("version_paquete") or version_paquete)
        elif evento == "diagnostico":
            diag_evento = datos

    terminos_sensibles = sorted(terminos_set, key=len, reverse=True)

    for reg in registros:
        evento = str(reg.get("evento", ""))
        datos = reg.get("datos") if isinstance(reg.get("datos"), dict) else {}
        if evento in ("importacion", "importacion_fe", "importacion_extracto"):
            importaciones.append({
                "tabla": _sanitizar_texto_soporte(str(datos.get("tabla", "")), terminos_sensibles),
                "codificacion": str(datos.get("codificacion", "")),
                "filas": int(datos.get("filas", 0) or 0),
                "filas_excluidas": int(datos.get("filas_excluidas", 0) or 0),
                "sha256": str(datos.get("sha256", "")),
                "transformaciones": [
                    _sanitizar_texto_soporte(str(t), terminos_sensibles)
                    for t in (datos.get("transformaciones") or [])
                ],
                "detalle_excluidas": [
                    _sanitizar_texto_soporte(str(d), terminos_sensibles)
                    for d in (datos.get("detalle_excluidas") or [])
                ],
            })
        elif evento == "prueba":
            pruebas.append({
                "id": str(datos.get("prueba", "")),
                "version_paquete": datos.get("version_paquete"),
                "filas_resultado": int(datos.get("filas_resultado", 0) or 0),
                "sql_sha256": str(datos.get("sql_sha256", "")),
            })
        elif evento not in ("inicio", "diagnostico"):
            datos_san = _sanitizar_estructura_soporte(datos, terminos_sensibles)
            observaciones_soporte.append({
                "evento": evento,
                "fecha_hora_utc": str(reg.get("fecha_hora_utc", "")),
                "datos": datos_san,
            })

    hallazgos_san = []
    for h in diag_evento.get("hallazgos") or []:
        if not isinstance(h, dict):
            continue
        hallazgos_san.append({
            "codigo": str(h.get("codigo", "")),
            "nombre": _sanitizar_texto_soporte(str(h.get("nombre", "")), terminos_sensibles),
            "tabla": _sanitizar_texto_soporte(str(h.get("tabla", "")), terminos_sensibles),
            "estado": str(h.get("estado", "")),
            "detalle": _sanitizar_texto_soporte(str(h.get("detalle", "")), terminos_sensibles),
            "accion_sugerida": _sanitizar_texto_soporte(str(h.get("accion_sugerida", "")), terminos_sensibles),
        })

    reporte: dict[str, Any] = {
        "version_esquema": 1,
        "fecha_exportacion_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "paquete": _sanitizar_texto_soporte(paquete, terminos_sensibles),
        "version_motor": version_motor,
        "version_paquete": version_paquete,
        "integridad_bitacora_sha256": bool(integra),
        "total_eventos": len(registros),
        "conteos_eventos": dict(sorted(conteos_eventos.items())),
        "diagnostico": {
            "estado_general": str(diag_evento.get("estado_general", "NO_DISPONIBLE")),
            "resumen": _sanitizar_texto_soporte(str(diag_evento.get("resumen", "")), terminos_sensibles),
            "conteos": diag_evento.get("conteos") or {},
            "hallazgos": hallazgos_san,
        },
        "importaciones": importaciones,
        "pruebas": pruebas,
        "eventos_adicionales": observaciones_soporte,
    }

    if destino is not None:
        ruta_destino = Path(destino)
        ruta_destino.parent.mkdir(parents=True, exist_ok=True)
        ruta_destino.write_text(json.dumps(reporte, indent=2, ensure_ascii=False), encoding="utf-8")

    return reporte


def _fecha_corrida_carpeta(carpeta: Path) -> datetime:
    m_comp = _RE_FECHA_CARPETA_COMPLETA.match(carpeta.name)
    if m_comp:
        try:
            return datetime.strptime(f"{m_comp.group(1)}-{m_comp.group(2)}", "%Y%m%d-%H%M%S").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            pass
    m_dia = _RE_FECHA_CARPETA_DIA.match(carpeta.name)
    if m_dia:
        try:
            return datetime.strptime(m_dia.group(1), "%Y%m%d").replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.fromtimestamp(carpeta.stat().st_mtime, tz=timezone.utc)


def purgar_corridas_expiradas(
    carpeta_salidas: str | Path,
    dias_retencion: int = 1825,
    simular: bool = True,
) -> list[Path]:
    """Detecta (y opcionalmente elimina) corridas en salidas/ cuya antigüedad supere dias_retencion."""
    if dias_retencion < 0:
        raise ErrorSeguridad("dias_retencion no puede ser negativo.")

    raiz = Path(carpeta_salidas)
    if not raiz.exists():
        return []
    if not raiz.is_dir():
        raise ErrorSeguridad(f"La ruta de salidas no es un directorio: {raiz}")

    ahora = datetime.now(timezone.utc)
    expiradas: list[Path] = []
    for sub in sorted(raiz.iterdir()):
        if not sub.is_dir():
            continue
        fecha_sub = _fecha_corrida_carpeta(sub)
        antiguedad_dias = (ahora - fecha_sub).total_seconds() / 86_400.0
        if antiguedad_dias > dias_retencion:
            expiradas.append(sub)
            if not simular:
                shutil.rmtree(sub)
    return expiradas
