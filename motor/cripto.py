"""Primitivas criptográficas locales (Ficha 21 · Oleada 2).

Implementación en sala limpia sin dependencias externas:
- Ed25519 (RFC 8032) en Python puro con coordenadas extendidas.
- Derivación de claves y verificación de contraseñas con `hashlib.scrypt` y `hmac.compare_digest`.
- Cifrado autenticado AES-256-GCM vía Windows CNG (`bcrypt.dll` con `ctypes`).
- Protección de secretos locales con Windows DPAPI (`crypt32.dll` con `ctypes`).
- Sellado criptográfico cruzado de corridas (`sello.json`) sobre `bitacora.jsonl`,
  `cedula.xlsx` y `revisiones.json`.
"""
from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes as wt
import hashlib
import hmac
import json
import os
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .bitacora import HASH_INICIAL, Bitacora
from .seguridad import ErrorSeguridad

# ---------------------------------------------------------------------------
# Constantes de Ed25519 (RFC 8032 §5.1)
# ---------------------------------------------------------------------------

_P = 2**255 - 19
_L = 2**252 + 27742317777372353535851937790883648493
_D = (-121665 * pow(121666, -1, _P)) % _P
_D2 = (2 * _D) % _P
_SQRT_M1 = pow(2, (_P - 1) // 4, _P)

_BY = (4 * pow(5, -1, _P)) % _P
_BX = 15112221349535400772501151409588531511454012693041857206046113283949847762202
_B_PUNTO = (_BX, _BY, 1, (_BX * _BY) % _P)
_IDENTIDAD = (0, 1, 1, 0)

# ---------------------------------------------------------------------------
# Constantes de Windows CNG y DPAPI
# ---------------------------------------------------------------------------

_STATUS_SUCCESS = 0
_BCRYPT_AES_ALGORITHM = "AES"
_BCRYPT_CHAINING_MODE = "ChainingMode"
_BCRYPT_CHAIN_MODE_GCM = "ChainingModeGCM"
_BCRYPT_OBJECT_LENGTH = "ObjectLength"
_BCRYPT_AUTH_INFO_VERSION = 1
_AES_GCM_NONCE_BYTES = 12
_AES_GCM_TAG_BYTES = 16
_CRYPTPROTECT_UI_FORBIDDEN = 0x1
_AAD_CLAVE_PRIVADA = b"folio-ed25519-v1"
_ARCHIVOS_MANIFIESTO = ("bitacora.jsonl", "cedula.xlsx", "revisiones.json")  # mínimo histórico (sellos versión 1)
_ARCHIVOS_FUERA_DE_SELLO = ("sello.json",)
VERSION_SELLO = 2  # v2: el manifiesto cubre todos los archivos de la carpeta y se rechazan archivos agregados


def _validar_bytes(valor: Any, nombre: str, largo: int | None = None) -> bytes:
    if not isinstance(valor, (bytes, bytearray)):
        raise ErrorSeguridad(f"El parámetro '{nombre}' debe entregarse en bytes.")
    datos = bytes(valor)
    if largo is not None and len(datos) != largo:
        raise ErrorSeguridad(f"El parámetro '{nombre}' debe medir exactamente {largo} bytes.")
    return datos


# ---------------------------------------------------------------------------
# Ed25519 (RFC 8032) en coordenadas extendidas (X, Y, Z, T)
# ---------------------------------------------------------------------------


def _sumar_puntos(p1: tuple[int, int, int, int], p2: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """Suma unificada en coordenadas extendidas para la curva de Edwards a = -1."""
    x1, y1, z1, t1 = p1
    x2, y2, z2, t2 = p2
    a = ((y1 - x1) * (y2 - x2)) % _P
    b = ((y1 + x1) * (y2 + x2)) % _P
    c = (t1 * _D2 * t2) % _P
    d = (z1 * 2 * z2) % _P
    e = (b - a) % _P
    f = (d - c) % _P
    g = (d + c) % _P
    h = (b + a) % _P
    return (
        (e * f) % _P,
        (g * h) % _P,
        (f * g) % _P,
        (e * h) % _P,
    )


def _multiplicar_escalar(escalar: int, punto: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    acum = _IDENTIDAD
    base = punto
    k = escalar
    while k > 0:
        if k & 1:
            acum = _sumar_puntos(acum, base)
        base = _sumar_puntos(base, base)
        k >>= 1
    return acum


def _puntos_iguales(p1: tuple[int, int, int, int], p2: tuple[int, int, int, int]) -> bool:
    x1, y1, z1, _ = p1
    x2, y2, z2, _ = p2
    return ((x1 * z2 - x2 * z1) % _P == 0) and ((y1 * z2 - y2 * z1) % _P == 0)


def _codificar_punto(punto: tuple[int, int, int, int]) -> bytes:
    x, y, z, _ = punto
    z_inv = pow(z, -1, _P)
    ax = (x * z_inv) % _P
    ay = (y * z_inv) % _P
    valor = ay | ((ax & 1) << 255)
    return valor.to_bytes(32, "little")


def _decodificar_punto(datos: bytes) -> tuple[int, int, int, int] | None:
    if len(datos) != 32:
        return None
    empaquetado = int.from_bytes(datos, "little")
    y = empaquetado & ((1 << 255) - 1)
    signo = empaquetado >> 255
    if y >= _P:
        return None

    y2 = (y * y) % _P
    u = (y2 - 1) % _P
    v = (_D * y2 + 1) % _P
    v3 = (v * v * v) % _P
    v7 = (v3 * v3 * v) % _P
    x = (u * v3 * pow((u * v7) % _P, (_P - 5) // 8, _P)) % _P

    vx2 = (v * x * x) % _P
    if vx2 != u:
        if vx2 == (-u) % _P:
            x = (x * _SQRT_M1) % _P
        else:
            return None

    if x == 0 and signo == 1:
        return None
    if (x & 1) != signo:
        x = (_P - x) % _P

    if ((-x * x + y2 - 1 - _D * x * x * y2) % _P) != 0:
        return None
    return (x, y, 1, (x * y) % _P)


def _expandir_semilla(semilla: bytes) -> tuple[int, bytes]:
    sem = _validar_bytes(semilla, "semilla", largo=32)
    resumen = hashlib.sha512(sem).digest()
    escalar_bytes = bytearray(resumen[:32])
    escalar_bytes[0] &= 248
    escalar_bytes[31] &= 127
    escalar_bytes[31] |= 64
    escalar = int.from_bytes(escalar_bytes, "little")
    return escalar, resumen[32:]


def generar_par_ed25519() -> tuple[bytes, bytes]:
    """Genera un par de claves Ed25519 (semilla privada de 32 bytes, clave pública de 32 bytes)."""
    semilla = secrets.token_bytes(32)
    return semilla, clave_publica_ed25519(semilla)


def clave_publica_ed25519(semilla: bytes) -> bytes:
    """Deriva la clave pública Ed25519 (32 bytes) a partir de la semilla privada (32 bytes)."""
    escalar, _ = _expandir_semilla(semilla)
    return _codificar_punto(_multiplicar_escalar(escalar, _B_PUNTO))


def firmar_ed25519(semilla: bytes, mensaje: bytes) -> bytes:
    """Genera firma determinista Ed25519 de 64 bytes conforme a RFC 8032."""
    msg = _validar_bytes(mensaje, "mensaje")
    escalar, prefijo = _expandir_semilla(semilla)
    pub = _codificar_punto(_multiplicar_escalar(escalar, _B_PUNTO))
    r = int.from_bytes(hashlib.sha512(prefijo + msg).digest(), "little") % _L
    r_bytes = _codificar_punto(_multiplicar_escalar(r, _B_PUNTO))
    k = int.from_bytes(hashlib.sha512(r_bytes + pub + msg).digest(), "little") % _L
    s = (r + k * escalar) % _L
    return r_bytes + s.to_bytes(32, "little")


def verificar_ed25519(pub: bytes, mensaje: bytes, firma: bytes) -> bool:
    """Verifica una firma Ed25519; retorna False ante claves, firmas o puntos inválidos."""
    if not isinstance(pub, (bytes, bytearray)) or not isinstance(mensaje, (bytes, bytearray)) or not isinstance(
        firma, (bytes, bytearray)
    ):
        return False
    pub_b = bytes(pub)
    msg_b = bytes(mensaje)
    sig_b = bytes(firma)
    if len(pub_b) != 32 or len(sig_b) != 64:
        return False

    punto_a = _decodificar_punto(pub_b)
    if punto_a is None or _puntos_iguales(_multiplicar_escalar(8, punto_a), _IDENTIDAD):
        return False

    r_bytes = sig_b[:32]
    s = int.from_bytes(sig_b[32:], "little")
    if s >= _L:
        return False

    punto_r = _decodificar_punto(r_bytes)
    if punto_r is None:
        return False

    k = int.from_bytes(hashlib.sha512(r_bytes + pub_b + msg_b).digest(), "little") % _L
    izquierda = _multiplicar_escalar(s, _B_PUNTO)
    derecha = _sumar_puntos(punto_r, _multiplicar_escalar(k, punto_a))
    return _puntos_iguales(izquierda, derecha)


def huella_clave_publica(pub: bytes) -> str:
    """Calcula la huella hexadecimal SHA-256 (64 caracteres) de una clave pública Ed25519."""
    pub_b = _validar_bytes(pub, "pub", largo=32)
    return hashlib.sha256(pub_b).hexdigest()


# ---------------------------------------------------------------------------
# Derivación y verificación de contraseñas (`hashlib.scrypt`)
# ---------------------------------------------------------------------------


# scrypt: OWASP recomienda N=2^17, r=8, p=1. Los registros con N menor (versiones <= 0.9.0 usaban 2^14)
# se aceptan y se migran al siguiente inicio de sesión correcto.
SCRYPT_N = 2**17
SCRYPT_N_MINIMO = 2**14
SCRYPT_N_MAXIMO = 2**20


def derivar_clave_scrypt(
    contrasena: str,
    sal: bytes,
    largo: int = 32,
    n: int = 16384,
    r: int = 8,
    p: int = 1,
) -> bytes:
    """Deriva una clave simétrica desde una contraseña usando `hashlib.scrypt`."""
    if not isinstance(contrasena, str):
        raise ErrorSeguridad("La contraseña debe ser una cadena de texto.")
    sal_b = _validar_bytes(sal, "sal")
    if not sal_b:
        raise ErrorSeguridad("La sal criptográfica no puede estar vacía.")
    if largo <= 0 or n < 2 or (n & (n - 1)) != 0 or r <= 0 or p <= 0:
        raise ErrorSeguridad("Parámetros scrypt inválidos.")
    # Límites a parámetros leídos de archivos (usuarios.json): ni tan bajos que debiliten, ni tan altos que congelen.
    if n < SCRYPT_N_MINIMO or n > SCRYPT_N_MAXIMO or r > 32 or p > 16:
        raise ErrorSeguridad(f"Parámetros scrypt fuera de rango permitido (n={n}, r={r}, p={p}).")
    maxmem = max(64 * 1024 * 1024, 256 * n * r)
    try:
        return hashlib.scrypt(
            contrasena.encode("utf-8"),
            salt=sal_b,
            n=n,
            r=r,
            p=p,
            maxmem=maxmem,
            dklen=largo,
        )
    except ValueError as exc:
        raise ErrorSeguridad(f"Error derivando clave con scrypt: {exc}") from exc


def hashear_contrasena(contrasena: str) -> dict[str, Any]:
    """Genera un registro de contraseña con sal aleatoria y parámetros `scrypt`."""
    if not isinstance(contrasena, str) or not contrasena:
        raise ErrorSeguridad("La contraseña no puede estar vacía.")
    sal = secrets.token_bytes(16)
    n, r, p = SCRYPT_N, 8, 1
    digest = derivar_clave_scrypt(contrasena, sal, largo=32, n=n, r=r, p=p)
    return {
        "algoritmo": "scrypt",
        "n": n,
        "r": r,
        "p": p,
        "sal_b64": base64.b64encode(sal).decode("ascii"),
        "hash_b64": base64.b64encode(digest).decode("ascii"),
    }


def requiere_migracion_scrypt(registro: dict[str, Any] | None) -> bool:
    """True si el registro (contraseña o clave privada) usa un costo scrypt menor al vigente."""
    try:
        return int((registro or {}).get("n", 0)) < SCRYPT_N
    except (TypeError, ValueError):
        return True


def verificar_contrasena(contrasena: str, registro: dict[str, Any]) -> bool:
    """Verifica una contraseña contra su registro `scrypt` en tiempo constante."""
    if not isinstance(contrasena, str) or not isinstance(registro, dict):
        return False
    if registro.get("algoritmo") != "scrypt":
        return False
    try:
        sal = base64.b64decode(str(registro["sal_b64"]), validate=True)
        hash_esp = base64.b64decode(str(registro["hash_b64"]), validate=True)
        n = int(registro["n"])
        r = int(registro["r"])
        p = int(registro["p"])
        calculado = derivar_clave_scrypt(contrasena, sal, largo=len(hash_esp), n=n, r=r, p=p)
    except Exception:
        return False
    return hmac.compare_digest(calculado, hash_esp)


# ---------------------------------------------------------------------------
# AES-256-GCM nativo Windows CNG (`bcrypt.dll`)
# ---------------------------------------------------------------------------


class _BCRYPT_AUTHENTICATED_CIPHER_MODE_INFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.ULONG),
        ("dwInfoVersion", wt.ULONG),
        ("pbNonce", ctypes.c_void_p),
        ("cbNonce", wt.ULONG),
        ("pbAuthData", ctypes.c_void_p),
        ("cbAuthData", wt.ULONG),
        ("pbTag", ctypes.c_void_p),
        ("cbTag", wt.ULONG),
        ("pbMacContext", ctypes.c_void_p),
        ("cbMacContext", wt.ULONG),
        ("cbAAD", wt.ULONG),
        ("cbData", ctypes.c_ulonglong),
        ("dwFlags", wt.ULONG),
    ]


_BCRYPT_CACHE: Any = None


def _obtener_bcrypt():
    global _BCRYPT_CACHE
    if _BCRYPT_CACHE is not None:
        return _BCRYPT_CACHE
    if sys.platform != "win32":
        raise ErrorSeguridad("AES-256-GCM vía Windows CNG requiere sistema operativo Windows.")
    dll = ctypes.WinDLL("bcrypt")
    handle_ptr = ctypes.POINTER(ctypes.c_void_p)
    ulong_ptr = ctypes.POINTER(wt.ULONG)

    dll.BCryptOpenAlgorithmProvider.argtypes = [handle_ptr, wt.LPCWSTR, wt.LPCWSTR, wt.ULONG]
    dll.BCryptOpenAlgorithmProvider.restype = wt.LONG
    dll.BCryptCloseAlgorithmProvider.argtypes = [ctypes.c_void_p, wt.ULONG]
    dll.BCryptCloseAlgorithmProvider.restype = wt.LONG
    dll.BCryptSetProperty.argtypes = [ctypes.c_void_p, wt.LPCWSTR, ctypes.c_void_p, wt.ULONG, wt.ULONG]
    dll.BCryptSetProperty.restype = wt.LONG
    dll.BCryptGetProperty.argtypes = [ctypes.c_void_p, wt.LPCWSTR, ctypes.c_void_p, wt.ULONG, ulong_ptr, wt.ULONG]
    dll.BCryptGetProperty.restype = wt.LONG
    dll.BCryptGenerateSymmetricKey.argtypes = [
        ctypes.c_void_p,
        handle_ptr,
        ctypes.c_void_p,
        wt.ULONG,
        ctypes.c_void_p,
        wt.ULONG,
        wt.ULONG,
    ]
    dll.BCryptGenerateSymmetricKey.restype = wt.LONG
    dll.BCryptDestroyKey.argtypes = [ctypes.c_void_p]
    dll.BCryptDestroyKey.restype = wt.LONG
    dll.BCryptEncrypt.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        wt.ULONG,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wt.ULONG,
        ctypes.c_void_p,
        wt.ULONG,
        ulong_ptr,
        wt.ULONG,
    ]
    dll.BCryptEncrypt.restype = wt.LONG
    dll.BCryptDecrypt.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        wt.ULONG,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wt.ULONG,
        ctypes.c_void_p,
        wt.ULONG,
        ulong_ptr,
        wt.ULONG,
    ]
    dll.BCryptDecrypt.restype = wt.LONG

    _BCRYPT_CACHE = dll
    return dll


def _preparar_info_gcm(
    nonce_buf: ctypes.Array[ctypes.c_ubyte],
    aad_buf: ctypes.Array[ctypes.c_ubyte] | None,
    aad_len: int,
    tag_buf: ctypes.Array[ctypes.c_ubyte],
) -> _BCRYPT_AUTHENTICATED_CIPHER_MODE_INFO:
    info = _BCRYPT_AUTHENTICATED_CIPHER_MODE_INFO()
    info.cbSize = ctypes.sizeof(_BCRYPT_AUTHENTICATED_CIPHER_MODE_INFO)
    info.dwInfoVersion = _BCRYPT_AUTH_INFO_VERSION
    info.pbNonce = ctypes.addressof(nonce_buf)
    info.cbNonce = _AES_GCM_NONCE_BYTES
    if aad_buf is not None and aad_len > 0:
        info.pbAuthData = ctypes.addressof(aad_buf)
        info.cbAuthData = aad_len
    else:
        info.pbAuthData = None
        info.cbAuthData = 0
    info.pbTag = ctypes.addressof(tag_buf)
    info.cbTag = _AES_GCM_TAG_BYTES
    info.pbMacContext = None
    info.cbMacContext = 0
    info.cbAAD = 0
    info.cbData = 0
    info.dwFlags = 0
    return info


def _gcm_portable(clave_32b: bytes, datos: bytes, nonce: bytes, tag: bytes, aad: bytes, cifrar: bool) -> tuple[bytes, bytes]:
    """AES-256-GCM con la librería auditada `cryptography` (respaldo fuera de Windows; mismo formato que CNG)."""
    try:
        from cryptography.exceptions import InvalidTag
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as exc:
        raise ErrorSeguridad(
            "AES-256-GCM vía Windows CNG requiere sistema operativo Windows "
            "(fuera de Windows instala el paquete 'cryptography')."
        ) from exc
    gcm = AESGCM(clave_32b)
    if cifrar:
        salida = gcm.encrypt(nonce, datos, aad or None)
        return salida[:-_AES_GCM_TAG_BYTES], salida[-_AES_GCM_TAG_BYTES:]
    try:
        return gcm.decrypt(nonce, datos + tag, aad or None), tag
    except InvalidTag as exc:
        raise ErrorSeguridad("Autenticación AES-256-GCM fallida: datos, clave, nonce o AAD alterados.") from exc


def _ejecutar_cng_gcm(clave_32b: bytes, datos: bytes, nonce: bytes, tag: bytes, aad: bytes, cifrar: bool) -> tuple[bytes, bytes]:
    if os.name != "nt":
        return _gcm_portable(clave_32b, datos, nonce, tag, aad, cifrar)
    bcrypt = _obtener_bcrypt()
    h_alg = ctypes.c_void_p()
    h_key = ctypes.c_void_p()
    try:
        st = bcrypt.BCryptOpenAlgorithmProvider(ctypes.byref(h_alg), _BCRYPT_AES_ALGORITHM, None, 0)
        if st != _STATUS_SUCCESS:
            raise ErrorSeguridad(f"No se pudo abrir proveedor AES CNG (estado=0x{st & 0xFFFFFFFF:08X}).")

        modo_buf = ctypes.create_unicode_buffer(_BCRYPT_CHAIN_MODE_GCM)
        st = bcrypt.BCryptSetProperty(
            h_alg,
            _BCRYPT_CHAINING_MODE,
            ctypes.byref(modo_buf),
            ctypes.sizeof(modo_buf),
            0,
        )
        if st != _STATUS_SUCCESS:
            raise ErrorSeguridad(f"No se pudo configurar modo GCM en CNG (estado=0x{st & 0xFFFFFFFF:08X}).")

        obj_len = wt.ULONG()
        res_len = wt.ULONG()
        st = bcrypt.BCryptGetProperty(
            h_alg,
            _BCRYPT_OBJECT_LENGTH,
            ctypes.byref(obj_len),
            ctypes.sizeof(obj_len),
            ctypes.byref(res_len),
            0,
        )
        if st != _STATUS_SUCCESS or obj_len.value == 0:
            raise ErrorSeguridad("No se pudo consultar ObjectLength de AES CNG.")

        key_obj = (ctypes.c_ubyte * obj_len.value)()
        key_buf = (ctypes.c_ubyte * 32).from_buffer_copy(clave_32b)
        st = bcrypt.BCryptGenerateSymmetricKey(
            h_alg,
            ctypes.byref(h_key),
            ctypes.byref(key_obj),
            obj_len.value,
            ctypes.byref(key_buf),
            32,
            0,
        )
        if st != _STATUS_SUCCESS:
            raise ErrorSeguridad(f"Error generando llave simétrica CNG (estado=0x{st & 0xFFFFFFFF:08X}).")

        nonce_buf = (ctypes.c_ubyte * _AES_GCM_NONCE_BYTES).from_buffer_copy(nonce)
        tag_buf = (ctypes.c_ubyte * _AES_GCM_TAG_BYTES).from_buffer_copy(tag)
        aad_buf = (ctypes.c_ubyte * len(aad)).from_buffer_copy(aad) if aad else None
        info = _preparar_info_gcm(nonce_buf, aad_buf, len(aad), tag_buf)

        if datos:
            in_buf = (ctypes.c_ubyte * len(datos)).from_buffer_copy(datos)
            out_buf = (ctypes.c_ubyte * len(datos))()
        else:
            in_buf = (ctypes.c_ubyte * 1)()
            out_buf = (ctypes.c_ubyte * 1)()

        out_len = wt.ULONG()
        fn = bcrypt.BCryptEncrypt if cifrar else bcrypt.BCryptDecrypt
        st = fn(
            h_key,
            ctypes.addressof(in_buf),
            len(datos),
            ctypes.byref(info),
            None,
            0,
            ctypes.addressof(out_buf),
            len(datos),
            ctypes.byref(out_len),
            0,
        )
        if st != _STATUS_SUCCESS:
            raise ErrorSeguridad(
                f"Fallo en {'cifrado' if cifrar else 'descifrado/autenticación'} AES-256-GCM "
                f"(estado=0x{st & 0xFFFFFFFF:08X})."
            )
        salida = bytes(out_buf[: out_len.value]) if out_len.value > 0 else b""
        return salida, bytes(tag_buf)
    finally:
        if h_key.value:
            bcrypt.BCryptDestroyKey(h_key)
        if h_alg.value:
            bcrypt.BCryptCloseAlgorithmProvider(h_alg, 0)


def cifrar_aes_gcm(clave_32b: bytes, texto_plano: bytes, aad: bytes = b"") -> dict[str, str]:
    """Cifra datos usando AES-256-GCM nativo de Windows CNG con nonce aleatorio de 12 bytes."""
    clave = _validar_bytes(clave_32b, "clave_32b", largo=32)
    datos = _validar_bytes(texto_plano, "texto_plano")
    aad_b = _validar_bytes(aad, "aad")
    nonce = secrets.token_bytes(_AES_GCM_NONCE_BYTES)
    cifrado, tag = _ejecutar_cng_gcm(clave, datos, nonce, b"\x00" * _AES_GCM_TAG_BYTES, aad_b, cifrar=True)
    return {
        "algoritmo": "AES-256-GCM",
        "nonce_b64": base64.b64encode(nonce).decode("ascii"),
        "tag_b64": base64.b64encode(tag).decode("ascii"),
        "cifrado_b64": base64.b64encode(cifrado).decode("ascii"),
    }


def descifrar_aes_gcm(clave_32b: bytes, paquete: dict[str, Any], aad: bytes = b"") -> bytes:
    """Descifra y verifica un paquete AES-256-GCM; lanza ErrorSeguridad ante cualquier alteración."""
    clave = _validar_bytes(clave_32b, "clave_32b", largo=32)
    aad_b = _validar_bytes(aad, "aad")
    if not isinstance(paquete, dict) or paquete.get("algoritmo") != "AES-256-GCM":
        raise ErrorSeguridad("Paquete AES-256-GCM inválido o algoritmo no compatible.")
    try:
        nonce = base64.b64decode(str(paquete["nonce_b64"]), validate=True)
        tag = base64.b64decode(str(paquete["tag_b64"]), validate=True)
        cifrado = base64.b64decode(str(paquete["cifrado_b64"]), validate=True)
    except Exception as exc:
        raise ErrorSeguridad(f"Codificación Base64 inválida en paquete AES-256-GCM: {exc}") from exc

    if len(nonce) != _AES_GCM_NONCE_BYTES or len(tag) != _AES_GCM_TAG_BYTES:
        raise ErrorSeguridad("Longitud de nonce o tag inválida en paquete AES-256-GCM.")

    texto_plano, _ = _ejecutar_cng_gcm(clave, cifrado, nonce, tag, aad_b, cifrar=False)
    return texto_plano


# ---------------------------------------------------------------------------
# DPAPI Windows (`crypt32.dll`) y cifrado de claves privadas
# ---------------------------------------------------------------------------


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wt.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


_DPAPI_CACHE: tuple[Any, Any] | None = None


def _obtener_dpapi():
    global _DPAPI_CACHE
    if _DPAPI_CACHE is not None:
        return _DPAPI_CACHE
    if sys.platform != "win32":
        raise ErrorSeguridad("DPAPI solo está disponible en Windows.")
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_DATA_BLOB),
        wt.LPCWSTR,
        ctypes.POINTER(_DATA_BLOB),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wt.DWORD,
        ctypes.POINTER(_DATA_BLOB),
    ]
    crypt32.CryptProtectData.restype = wt.BOOL

    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DATA_BLOB),
        ctypes.POINTER(wt.LPWSTR),
        ctypes.POINTER(_DATA_BLOB),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wt.DWORD,
        ctypes.POINTER(_DATA_BLOB),
    ]
    crypt32.CryptUnprotectData.restype = wt.BOOL

    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p

    _DPAPI_CACHE = (crypt32, kernel32)
    return _DPAPI_CACHE


def _crear_blob(datos: bytes) -> tuple[_DATA_BLOB, ctypes.Array[ctypes.c_ubyte]]:
    if datos:
        buf = (ctypes.c_ubyte * len(datos)).from_buffer_copy(datos)
    else:
        buf = (ctypes.c_ubyte * 1)()
    return _DATA_BLOB(len(datos), buf), buf


def proteger_dpapi(datos: bytes, entropia: bytes = b"FolioAuditorDPAPI") -> bytes:
    """Protege bytes locales vinculándolos al usuario actual de Windows mediante DPAPI."""
    datos_b = _validar_bytes(datos, "datos")
    ent_b = _validar_bytes(entropia, "entropia")
    crypt32, kernel32 = _obtener_dpapi()

    blob_in, _buf_in = _crear_blob(datos_b)
    blob_ent, _buf_ent = _crear_blob(ent_b) if ent_b else (None, None)
    blob_out = _DATA_BLOB()
    try:
        ok = crypt32.CryptProtectData(
            ctypes.byref(blob_in),
            None,
            ctypes.byref(blob_ent) if blob_ent is not None else None,
            None,
            None,
            _CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(blob_out),
        )
        if not ok:
            err = ctypes.get_last_error()
            raise ErrorSeguridad(f"Error protegiendo datos con Windows DPAPI (código={err}).")
        if not blob_out.pbData or blob_out.cbData == 0:
            raise ErrorSeguridad("Windows DPAPI devolvió un buffer vacío.")
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        if blob_out.pbData:
            kernel32.LocalFree(ctypes.cast(blob_out.pbData, ctypes.c_void_p))


def desproteger_dpapi(cifrado: bytes, entropia: bytes = b"FolioAuditorDPAPI") -> bytes:
    """Descifra bytes protegidos previamente con `proteger_dpapi`."""
    cif_b = _validar_bytes(cifrado, "cifrado")
    if not cif_b:
        raise ErrorSeguridad("El contenido DPAPI cifrado no puede estar vacío.")
    ent_b = _validar_bytes(entropia, "entropia")
    crypt32, kernel32 = _obtener_dpapi()

    blob_in, _buf_in = _crear_blob(cif_b)
    blob_ent, _buf_ent = _crear_blob(ent_b) if ent_b else (None, None)
    blob_out = _DATA_BLOB()
    try:
        ok = crypt32.CryptUnprotectData(
            ctypes.byref(blob_in),
            None,
            ctypes.byref(blob_ent) if blob_ent is not None else None,
            None,
            None,
            _CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(blob_out),
        )
        if not ok:
            err = ctypes.get_last_error()
            raise ErrorSeguridad(f"Error desprotegiendo datos con Windows DPAPI (código={err}).")
        if blob_out.cbData == 0:
            return b""
        if not blob_out.pbData:
            raise ErrorSeguridad("Windows DPAPI devolvió puntero nulo.")
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        if blob_out.pbData:
            kernel32.LocalFree(ctypes.cast(blob_out.pbData, ctypes.c_void_p))


def cifrar_clave_privada(semilla: bytes, contrasena: str) -> dict[str, Any]:
    """Cifra una semilla Ed25519 (32 bytes) con scrypt + AES-256-GCM vinculado a AAD."""
    sem_b = _validar_bytes(semilla, "semilla", largo=32)
    if not isinstance(contrasena, str) or not contrasena:
        raise ErrorSeguridad("La contraseña para proteger la clave privada no puede estar vacía.")
    sal = secrets.token_bytes(16)
    n, r, p = SCRYPT_N, 8, 1
    clave = derivar_clave_scrypt(contrasena, sal, largo=32, n=n, r=r, p=p)
    paquete_gcm = cifrar_aes_gcm(clave, sem_b, aad=_AAD_CLAVE_PRIVADA)
    return {
        "kdf": "scrypt",
        "n": n,
        "r": r,
        "p": p,
        "sal_b64": base64.b64encode(sal).decode("ascii"),
        **paquete_gcm,
    }


def descifrar_clave_privada(paquete: dict[str, Any], contrasena: str) -> bytes:
    """Descifra la semilla privada Ed25519 validando contraseña y etiqueta AES-GCM."""
    if not isinstance(paquete, dict) or paquete.get("kdf") != "scrypt":
        raise ErrorSeguridad("Formato de clave privada cifrada inválido.")
    if not isinstance(contrasena, str) or not contrasena:
        raise ErrorSeguridad("Contraseña inválida para descifrar la clave privada.")
    try:
        sal = base64.b64decode(str(paquete["sal_b64"]), validate=True)
        n = int(paquete["n"])
        r = int(paquete["r"])
        p = int(paquete["p"])
    except Exception as exc:
        raise ErrorSeguridad(f"Metadatos KDF inválidos en clave privada: {exc}") from exc

    clave = derivar_clave_scrypt(contrasena, sal, largo=32, n=n, r=r, p=p)
    semilla = descifrar_aes_gcm(clave, paquete, aad=_AAD_CLAVE_PRIVADA)
    if len(semilla) != 32:
        raise ErrorSeguridad("La semilla privada descifrada no tiene 32 bytes.")
    return semilla


# ---------------------------------------------------------------------------
# Sellado criptográfico cruzado de corridas (`sello.json`)
# ---------------------------------------------------------------------------


def _sha256_archivo(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open("rb") as f:
        while True:
            bloque = f.read(65536)
            if not bloque:
                break
            h.update(bloque)
    return h.hexdigest()


def _estado_bitacora_actual(ruta_bitacora: Path) -> tuple[str, bool]:
    if not ruta_bitacora.exists():
        return HASH_INICIAL, True
    try:
        bit = Bitacora(ruta_bitacora)
        registros = bit.leer()
        integra = bit.verificar()
        ultimo = registros[-1]["hash"] if registros else HASH_INICIAL
        return str(ultimo), bool(integra)
    except Exception:
        return "", False


def _json_canonico(datos: dict[str, Any]) -> bytes:
    return json.dumps(datos, sort_keys=True, ensure_ascii=False).encode("utf-8")


def _archivos_corrida(carp: Path) -> list[str]:
    """Todos los archivos de la carpeta de corrida (rutas relativas con '/'), salvo el propio sello."""
    nombres: list[str] = []
    if not carp.exists():
        return nombres
    for ruta in sorted(carp.rglob("*")):
        if not ruta.is_file() or ruta.is_symlink():
            continue
        rel = ruta.relative_to(carp).as_posix()
        if rel in _ARCHIVOS_FUERA_DE_SELLO or rel.endswith(".tmp"):
            continue
        nombres.append(rel)
    return nombres


def construir_manifiesto_corrida(carpeta: str | Path) -> dict[str, Any]:
    """Construye el manifiesto de integridad SHA-256 de TODOS los archivos de una corrida (salvo sello.json)."""
    carp = Path(carpeta)
    archivos: dict[str, dict[str, Any]] = {}
    for nombre in _archivos_corrida(carp):
        ruta = carp / nombre
        archivos[nombre] = {
            "sha256": _sha256_archivo(ruta),
            "bytes": ruta.stat().st_size,
        }
    ultimo_hash, bitacora_integra = _estado_bitacora_actual(carp / "bitacora.jsonl")
    return {
        "archivos": archivos,
        "ultimo_hash_bitacora": ultimo_hash,
        "bitacora_integra": bitacora_integra,
    }


def sellar_corrida(
    carpeta: str | Path,
    usuario: str,
    rol: str,
    semilla_privada: bytes,
    clave_publica: bytes,
    bitacora: Bitacora | None = None,
) -> Path:
    """Registra el sellado en bitácora y genera `sello.json` firmado con Ed25519."""
    carp = Path(carpeta)
    carp.mkdir(parents=True, exist_ok=True)
    sem_b = _validar_bytes(semilla_privada, "semilla_privada", largo=32)
    pub_b = _validar_bytes(clave_publica, "clave_publica", largo=32)
    if clave_publica_ed25519(sem_b) != pub_b:
        raise ErrorSeguridad("La semilla privada no corresponde a la clave pública indicada.")

    huella = huella_clave_publica(pub_b)
    if bitacora is not None:
        bitacora.registrar(
            "sello_criptografico_emitido",
            usuario=usuario,
            rol=rol,
            huella_clave=huella,
        )

    manifiesto = construir_manifiesto_corrida(carp)
    if not manifiesto.get("bitacora_integra", False):
        raise ErrorSeguridad("No se puede sellar la corrida: la cadena SHA-256 de bitacora.jsonl está alterada.")

    firma = firmar_ed25519(sem_b, _json_canonico(manifiesto))
    sello = {
        "version": VERSION_SELLO,
        "algoritmo": "Ed25519",
        "usuario": usuario,
        "rol": rol,
        "fecha_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "clave_publica_b64": base64.b64encode(pub_b).decode("ascii"),
        "huella_clave": huella,
        "manifiesto": manifiesto,
        "firma_ed25519_b64": base64.b64encode(firma).decode("ascii"),
    }
    ruta_sello = carp / "sello.json"
    ruta_sello.write_text(json.dumps(sello, indent=2, ensure_ascii=False), encoding="utf-8")
    return ruta_sello


def verificar_sello_corrida(
    carpeta: str | Path,
    clave_publica_esperada: bytes | None = None,
    claves_registradas: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Verifica firma Ed25519 de `sello.json`, hashes en disco de cada archivo y cadena de bitácora.

    La firma por sí sola solo prueba que alguien con *alguna* clave selló la carpeta. Para saber
    QUIÉN la selló hay que anclar la clave: `clave_publica_esperada` (una clave concreta) o
    `claves_registradas` ({huella: {"usuario": ..., ...}}, p. ej. de `GestorUsuarios.registro_claves()`).
    El resultado trae `firmante_verificado`: True (clave anclada), False (clave desconocida o de otro
    usuario: el sello se rechaza) o None (no se entregó ancla: firma íntegra pero firmante sin verificar).
    """
    carp = Path(carpeta)
    ruta_sello = carp / "sello.json"
    base_res = {
        "valido": False,
        "motivo": "",
        "detalle": {},
        "huella_clave": "",
        "usuario": "",
        "rol": "",
    }
    if not carp.exists() or not ruta_sello.exists():
        base_res["motivo"] = "No existe sello.json en la carpeta de la corrida."
        return base_res

    try:
        sello = json.loads(ruta_sello.read_text(encoding="utf-8"))
        if not isinstance(sello, dict):
            raise ValueError("Estructura JSON inválida.")
    except Exception as exc:
        base_res["motivo"] = f"No se pudo leer sello.json: {exc}"
        return base_res

    usuario = str(sello.get("usuario", ""))
    rol = str(sello.get("rol", ""))
    huella_declarada = str(sello.get("huella_clave", ""))
    manifiesto = sello.get("manifiesto")

    detalle: dict[str, Any] = {
        "firma_valida": False,
        "clave_coincide": clave_publica_esperada is None,
        "bitacora_integra": False,
        "archivos": {},
    }
    res = {
        "valido": False,
        "motivo": "",
        "detalle": detalle,
        "huella_clave": huella_declarada,
        "usuario": usuario,
        "rol": rol,
        "fecha_utc": str(sello.get("fecha_utc", "")),
        "firmante_verificado": None,
        "version_sello": sello.get("version", 1),
    }

    try:
        pub_b = base64.b64decode(str(sello["clave_publica_b64"]), validate=True)
        firma_b = base64.b64decode(str(sello["firma_ed25519_b64"]), validate=True)
    except Exception:
        res["motivo"] = "Clave pública o firma Ed25519 malformada en sello.json."
        return res

    if len(pub_b) != 32 or len(firma_b) != 64 or not isinstance(manifiesto, dict):
        res["motivo"] = "Longitud de clave/firma o manifiesto inválido en sello.json."
        return res

    huella_real = huella_clave_publica(pub_b)
    if huella_declarada and huella_declarada != huella_real:
        res["motivo"] = "La huella de clave declarada no coincide con la clave pública."
        return res
    res["huella_clave"] = huella_real

    if clave_publica_esperada is not None:
        try:
            esp_b = _validar_bytes(clave_publica_esperada, "clave_publica_esperada", largo=32)
        except ErrorSeguridad as exc:
            res["motivo"] = str(exc)
            return res
        if not hmac.compare_digest(pub_b, esp_b):
            detalle["clave_coincide"] = False
            res["motivo"] = "La clave pública del sello no coincide con la clave esperada."
            return res
        detalle["clave_coincide"] = True
        res["firmante_verificado"] = True

    if claves_registradas is not None:
        registro = claves_registradas.get(huella_real)
        if registro is None:
            res["firmante_verificado"] = False
            res["motivo"] = (
                f"La clave que firmó el sello (huella {huella_real[:16]}…) no está registrada en la firma: "
                "el sello pudo ser emitido por alguien distinto del usuario declarado."
            )
            return res
        usuario_reg = str(registro.get("usuario", ""))
        if usuario_reg and usuario_reg.strip().lower() != usuario.strip().lower():
            res["firmante_verificado"] = False
            res["motivo"] = (
                f"El sello declara al usuario '{usuario}' pero la clave registrada pertenece a '{usuario_reg}'."
            )
            return res
        res["firmante_verificado"] = True

    firma_ok = verificar_ed25519(pub_b, _json_canonico(manifiesto), firma_b)
    detalle["firma_valida"] = firma_ok
    if not firma_ok:
        res["motivo"] = "La firma criptográfica Ed25519 de sello.json es inválida."
        return res

    ultimo_hash_actual, bit_integra = _estado_bitacora_actual(carp / "bitacora.jsonl")
    detalle["bitacora_integra"] = bit_integra
    if not bit_integra:
        res["motivo"] = "La cadena SHA-256 de bitacora.jsonl está alterada."
        return res

    if ultimo_hash_actual != str(manifiesto.get("ultimo_hash_bitacora", "")):
        res["motivo"] = "El último hash de bitacora.jsonl no coincide con el manifiesto sellado."
        return res

    archivos_sellados = manifiesto.get("archivos")
    if not isinstance(archivos_sellados, dict):
        res["motivo"] = "El manifiesto de archivos en sello.json es inválido."
        return res

    carp_resuelta = carp.resolve()
    for nombre, meta in archivos_sellados.items():
        ruta = carp / nombre
        if carp_resuelta not in ruta.resolve().parents:
            res["motivo"] = f"El manifiesto contiene una ruta fuera de la carpeta de la corrida: {nombre!r}."
            return res
        if not ruta.exists() or not ruta.is_file():
            detalle["archivos"][nombre] = "ausente"
            res["motivo"] = f"El archivo sellado '{nombre}' fue eliminado o movido."
            return res
        hash_esp = meta.get("sha256") if isinstance(meta, dict) else str(meta)
        hash_act = _sha256_archivo(ruta)
        if hash_act != hash_esp:
            detalle["archivos"][nombre] = "alterado"
            res["motivo"] = f"El archivo '{nombre}' fue modificado después del sellado."
            return res
        detalle["archivos"][nombre] = "integro"

    if int(sello.get("version", 1) or 1) >= 2:
        agregados = [n for n in _archivos_corrida(carp) if n not in archivos_sellados]
        if agregados:
            for n in agregados:
                detalle["archivos"][n] = "agregado"
            res["motivo"] = f"Se agregaron archivos después del sellado: {', '.join(agregados[:5])}."
            return res

    res["valido"] = True
    res["motivo"] = "Sello criptográfico Ed25519 y hashes SHA-256 verificados correctamente."
    if res["firmante_verificado"] is None:
        res["motivo"] += (
            " Atención: el firmante NO está verificado (no se comparó la clave con un registro de claves),"
            " así que cualquiera pudo haber re-sellado la carpeta."
        )
    return res
