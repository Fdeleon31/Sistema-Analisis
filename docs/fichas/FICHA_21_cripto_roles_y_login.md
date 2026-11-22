# Ficha 21 · Criptografía Local, Control de Acceso RBAC, Segregación NIA 220/230 y Pantalla de Inicio de Sesión (Oleada 2)

**Fecha:** noviembre 2026  
**Módulos:** `motor/cripto.py`, `motor/usuarios.py`, `motor/revision.py`, `app/login_qt.py`  
**Pruebas asociadas:** `tests/test_seguridad_cripto_roles.py`, `tests/test_login_pantalla.py`, `tests/test_fase3_roles.py`  
**Referencias públicas:**
- **RFC 8032** (*Edwards-Curve Digital Signature Algorithm (EdDSA)* — curva Ed25519, §5.1 y vectores de prueba §7.1).
- **NIST SP 800-57** (*Recommendation for Key Management*, Parte 1: ciclo de vida, generación aleatoria y almacenamiento protegido de claves).
- **NIST SP 800-38D** (*Recommendation for Block Cipher Modes of Operation: Galois/Counter Mode (GCM)*) y **RFC 7914** (*The scrypt Password-Based Key Derivation Function*).
- **OWASP ASVS v4.0.3** (V2 Autenticación, V4 Control de Acceso, V6 Criptografía almacenada) y **OWASP CWE Top 25** (`CWE-287`, `CWE-307`, `CWE-326`, `CWE-327`, `CWE-798`).
- **ISO/IEC 27001:2022** (Anexo A.8.3 — Restricción de acceso a la información; Anexo A.8.24 — Uso de criptografía) e **ISO/IEC 27037** (*Guidelines for identification, collection, acquisition and preservation of digital evidence*).
- **Microsoft Learn · Win32 Cryptography API: Next Generation (CNG)** (`bcrypt.dll`: `BCryptOpenAlgorithmProvider`, `BCryptEncrypt`, `BCryptDecrypt`, `BCRYPT_AUTHENTICATED_CIPHER_MODE_INFO`) y **Windows Data Protection API (DPAPI)** (`crypt32.dll`: `CryptProtectData`, `CryptUnprotectData`, `CRYPTPROTECT_UI_FORBIDDEN`).
- **Python 3.12 Standard Library** (`hashlib.scrypt`, `hashlib.sha512`, `hashlib.sha256`, `hmac.compare_digest`, `secrets`, `ctypes`).
- **NIGC 1 / ISQM 1**, **NIA 220** (*Gestión de la calidad de una auditoría de estados financieros*), **NIA 230** (*Documentación de auditoría* — párrs. 8, 9, 14–16 y guía A21 sobre el límite de 60 días de compilación final del archivo) y **NIA 500** (*Evidencia de auditoría*).
- **Fichas 17 y 18** (`docs/fichas/FICHA_17_identidad_y_constancia.md`, `docs/fichas/FICHA_18_interfaz_clasica_win32.md`): identidad ejecutiva **`FOLIO AUDITOR`** y sistema visual clásico Win32 (`#D4D0C8`, `#000080 -> #1084D0`, biseles 3D e íconos vectoriales 3D en memoria).

**Principio rector:** *Identidad criptográfica verificable, no repudio y segregación efectiva de deberes sin dependencias externas ni servicios en la nube.* La integridad de la bitácora SHA-256 se complementa con firma digital asimétrica **Ed25519** sobre el conjunto completo de papeles de trabajo (`sello.json`), garantizando que un tercero independiente detecte cualquier alteración, incluso si alguien intentara recalcular manualmente toda la cadena `bitacora.jsonl`.

---

## 1. Primitivas criptográficas locales (`motor/cripto.py`)

El módulo `motor/cripto.py` opera íntegramente con la biblioteca estándar de Python 3.12 y las APIs nativas del sistema operativo Windows mediante `ctypes`, reutilizando `ErrorSeguridad` de `motor/seguridad.py` y `Bitacora` de `motor/bitacora.py`.

### 1.1 Firma digital Ed25519 en Python puro (RFC 8032)

Implementación determinista sobre la curva de Edwards torcida $-x^2 + y^2 = 1 + d x^2 y^2$ sobre $\mathbb{F}_p$ ($p = 2^{255}-19$) y orden del subgrupo primo $L = 2^{252} + 27742317777372353535851937790883648493$, utilizando coordenadas proyectivas extendidas $(X:Y:Z:T)$ con $x = X/Z$, $y = Y/Z$, $xy = T/Z$, función hash `hashlib.sha512` e inverso modular nativo `pow(..., -1, P)`:

| Función | Firma esperada | Comportamiento normativo (RFC 8032) |
| :--- | :--- | :--- |
| `generar_par_ed25519` | `() -> tuple[bytes, bytes]` | Genera una semilla aleatoria criptográfica de 32 bytes (`secrets.token_bytes(32)`) y deriva la clave pública de 32 bytes `(semilla_32b, pub_32b)`. |
| `clave_publica_ed25519` | `(semilla: bytes) -> bytes` | Valida longitud exacta de 32 bytes; aplica SHA-512, *clamping* de los 32 bytes inferiores según RFC 8032 §5.1.5 y multiplicación escalar `[a]B` codificada en 32 bytes *little-endian*. |
| `firmar_ed25519` | `(semilla: bytes, mensaje: bytes) -> bytes` | Calcula `r`, `R = [r]B`, `k = H(enc(R) || enc(A) || M) mod L` y `S = (r + k*a) mod L` (RFC 8032 §5.1.6), devolviendo firma determinista de 64 bytes. |
| `verificar_ed25519` | `(pub: bytes, mensaje: bytes, firma: bytes) -> bool` | Valida longitudes (32 y 64 bytes), decodificación canónica de puntos `A` y `R`, condición `0 <= S < L` y verificación cofactoreada `[8]SB == [8]R + [8]kA`. Ante clave/firma malformada o punto fuera de curva devuelve `False` y nunca lanza excepción. |
| `huella_clave_publica` | `(pub: bytes) -> str` | Devuelve el resumen hexadecimal SHA-256 en minúsculas (64 caracteres) de la clave pública de 32 bytes. |

### 1.2 Derivación de claves y almacenamiento de contraseñas (`scrypt`)

- **`derivar_clave_scrypt(contrasena: str, sal: bytes, largo: int = 32, n: int = 16384, r: int = 8, p: int = 1) -> bytes`:** deriva material simétrico usando `hashlib.scrypt` sobre la contraseña codificada en UTF-8.
- **`hashear_contrasena(contrasena: str) -> dict`:** genera una sal criptográfica aleatoria por usuario y retorna un diccionario estructurado con los parámetros explícitos (`algoritmo`, `n`, `r`, `p`, `sal_b64`, `hash_b64`).
- **`verificar_contrasena(contrasena: str, registro: dict) -> bool`:** recalcula el derivado con los parámetros almacenados y compara en tiempo constante mediante `hmac.compare_digest` para mitigar ataques por canal lateral de temporización.

### 1.3 Cifrado autenticado AES-256-GCM vía Windows CNG (`bcrypt.dll`)

- Se utiliza `ctypes.windll.bcrypt` con proveedor `BCRYPT_AES_ALGORITHM` en modo encadenado `BCRYPT_CHAIN_MODE_GCM`.
- La estructura `BCRYPT_AUTHENTICATED_CIPHER_MODE_INFO` respeta la alineación binaria de Windows 64 bits (`dwInfoVersion = 1`, `cbSize = ctypes.sizeof(...)`), gestiona *nonce* aleatorio de 12 bytes (`secrets.token_bytes(12)`), etiqueta de autenticación (*tag*) de 16 bytes, datos asociados autenticados (`aad`) y el caso límite `texto_plano = b""`.
- **`cifrar_aes_gcm(clave_32b: bytes, texto_plano: bytes, aad: bytes = b"") -> dict`:** exige clave de 32 bytes y retorna `{"algoritmo": "AES-256-GCM", "nonce_b64": ..., "tag_b64": ..., "cifrado_b64": ...}`.
- **`descifrar_aes_gcm(clave_32b: bytes, paquete: dict, aad: bytes = b"") -> bytes`:** verifica autenticidad completa antes de entregar el texto plano; cualquier modificación de un bit en el texto cifrado, *nonce*, etiqueta, clave o `aad` dispara `ErrorSeguridad`.

### 1.4 Protección de secretos locales con DPAPI (`crypt32.dll`) y resguardo de clave privada

- **`proteger_dpapi(datos: bytes, entropia: bytes = b"FolioAuditorDPAPI") -> bytes`** y **`desproteger_dpapi(cifrado: bytes, entropia: bytes = b"FolioAuditorDPAPI") -> bytes`:** encapsulan `CryptProtectData` y `CryptUnprotectData` de `crypt32.dll` con bandera `CRYPTPROTECT_UI_FORBIDDEN = 0x1`, entropía adicional de aplicación, manejo explícito de buffers vacíos y liberación segura con `LocalFree` (`kernel32.dll`). Cualquier error Win32 se traduce en `ErrorSeguridad`.
- **`cifrar_clave_privada(semilla: bytes, contrasena: str) -> dict`** y **`descifrar_clave_privada(paquete: dict, contrasena: str) -> bytes`:** protegen la semilla Ed25519 del usuario derivando una llave simétrica de 32 bytes mediante `scrypt` y cifrando con `AES-256-GCM` vinculando el contexto `aad = b"folio-ed25519-v1"`.

### 1.5 Sellado criptográfico cruzado de corrida (`sello.json`)

1. **`construir_manifiesto_corrida(carpeta: str | Path) -> dict`:** calcula los resúmenes SHA-256 de `bitacora.jsonl`, `cedula.xlsx` y `revisiones.json` (cuando existan en la carpeta de la corrida), e incluye `ultimo_hash_bitacora` y `bitacora_integra` obtenido de `Bitacora(...).verificar()`.
2. **`sellar_corrida(carpeta: str | Path, usuario: str, rol: str, semilla_privada: bytes, clave_publica: bytes, bitacora: Bitacora | None = None) -> Path`:**
   - Registra **primero** el evento `"sello_criptografico_emitido"` en `bitacora` (si se pasa) para que la bitácora final quede cerrada antes del cálculo de hashes.
   - Calcula **después** el manifiesto final con `construir_manifiesto_corrida(carpeta)`.
   - Serializa el manifiesto de forma canónica (`json.dumps(manifiesto, sort_keys=True, ensure_ascii=False).encode("utf-8")`) y firma ese bloque con `firmar_ed25519`.
   - Escribe `sello.json` con `clave_publica_b64`, `huella_clave`, `usuario`, `rol`, `fecha_utc`, `manifiesto` y `firma_ed25519_b64`.
3. **`verificar_sello_corrida(carpeta: str | Path, clave_publica_esperada: bytes | None = None) -> dict`:**
   - Comprueba la existencia de `sello.json` y el formato válido de su contenido.
   - Verifica la firma Ed25519 contra el manifiesto canónico almacenado.
   - Si se suministra `clave_publica_esperada`, valida coincidencia exacta con la clave firmante.
   - Recalcula en disco los hashes SHA-256 actuales de `bitacora.jsonl`, `cedula.xlsx` y `revisiones.json`, y ejecuta `Bitacora.verificar()`.
   - Retorna `{"valido": bool, "motivo": str, "detalle": dict, "huella_clave": str, "usuario": str, "rol": str}`. Si alguien recalcula la cadena completa de `bitacora.jsonl` o modifica 1 byte en `cedula.xlsx` o `revisiones.json`, el sello falla de inmediato (`valido == False`).

---

## 2. Gobierno de identidades, RBAC y fuerza bruta (`motor/usuarios.py`)

El almacén local de identidades reside bajo `seguridad/` en `raiz_trabajo()` (`usuarios.json` y `bitacora_accesos.jsonl`, esta última gestionada con `Bitacora` para garantizar encadenamiento SHA-256 de todos los eventos de autenticación y administración).

### 2.1 Perfiles, constantes y sesión autenticada

- **Constantes:**
  - `PERFIL_ADMIN = "Administrador"`
  - `PERFIL_PREPARADOR = "Preparador"`
  - `PERFIL_REVISOR = "Revisor"`
  - `PERFIL_SOCIO = "Socio"`
  - `PERFILES_VALIDOS = ("Administrador", "Preparador", "Revisor", "Socio")`
  - `PERFILES_AUDITORIA = ("Preparador", "Revisor", "Socio")`
  - `MAX_INTENTOS_FALLIDOS = 5`
  - `BLOQUEO_MINUTOS = 15`
- **Dataclass `SesionAutenticada`:** encapsula `usuario`, `nombre_completo`, `perfil`, `rol_auditoria`, `clave_publica_b64`, `huella_clave`, `fecha_login_utc` y `_semilla_privada: bytes | None = field(default=None, repr=False)` (excluida de representaciones textuales). Expone las propiedades `es_admin`, `etiqueta_ui`, `clave_publica_bytes` y `semilla_privada_bytes`.

### 2.2 Política de contraseñas y protección contra fuerza bruta

- **`validar_politica_contrasena(contrasena: str) -> None`:** exige longitud mínima de **10 caracteres**, al menos **1 letra mayúscula**, al menos **1 letra minúscula** y al menos **1 dígito numérico**; ante incumplimiento lanza `ErrorSeguridad`.
- **Bloqueo temporal (`autenticar`):** tras acumular `intentos_fallidos >= max_intentos` (5 por defecto), la cuenta queda bloqueada durante `bloqueo_minutos` (15 minutos por defecto). Todo intento exitoso, fallido por credenciales o rechazado por bloqueo/modo incompatible deja constancia en `bitacora_accesos.jsonl`.

### 2.3 Operaciones de `GestorUsuarios`

1. **`inicializar_firma(admin_usuario, admin_nombre, admin_contrasena, preparador=None, segregacion_estricta=True) -> dict`:** crea el almacén inicial con el **Administrador** obligatorio, un **Preparador** opcional cuando se pasa el diccionario correspondiente, y las políticas iniciales (`segregacion_estricta: True`, `ventana_archivo_dias: 60`, `max_intentos: 5`, `bloqueo_minutos: 15`, `alerta_nube: True`).
2. **`crear_usuario(actor, usuario, nombre_completo, contrasena, perfil, rol_auditoria_extra=None) -> dict`:** operación exclusiva de `Administrador` (`actor.es_admin`); genera un par Ed25519 propio para el usuario y cifra su semilla privada con su contraseña.
3. **`autenticar(usuario, contrasena, modo_acceso=None) -> SesionAutenticada`:** soporta acceso dual diferenciando explícitamente:
   - `modo_acceso == "Administrador"`: exige `perfil == "Administrador"`.
   - `modo_acceso in ("Preparador", "Auditor")`: exige `perfil in PERFILES_AUDITORIA` (`Preparador`, `Revisor`, `Socio`).
   - `modo_acceso is None`: permite cualquier perfil activo.
   Al autenticar exitosamente, descifra `_semilla_privada` únicamente en memoria de la sesión.
4. **Ciclo de vida de cuentas y llaves:**
   - `cambiar_contrasena(usuario, contrasena_actual, contrasena_nueva)`: valida política nueva y **re-cifra** la semilla Ed25519 preservando la misma clave pública del auditor (continuidad de identidad en firmas históricas).
   - `restablecer_contrasena_admin(actor, usuario_objetivo, nueva_contrasena)`: exclusiva de `Administrador`; desbloquea la cuenta, genera un nuevo par Ed25519 (rotación documentada) y registra el evento en `bitacora_accesos.jsonl`.
   - `cambiar_estado_usuario(actor, usuario_objetivo, activo)`: exclusiva de `Administrador`; impide desactivar al último `Administrador` activo del sistema.
   - `actualizar_politicas(actor, **cambios)`: exclusiva de `Administrador`.
   - `listar_usuarios()`: expone metadatos públicos y `huella_clave`, **nunca** hashes de contraseña ni semillas privadas.
   - `leer_bitacora_accesos() -> tuple[list[dict], bool]`: retorna eventos e integridad SHA-256.
   - `puede_firmar_rol(sesion, rol) -> bool`: valida si la sesión posee `perfil == rol` o `rol_auditoria == rol`; un `Administrador` puro sin `rol_auditoria` asignado no puede firmar papeles de auditoría.

---

## 3. Segregación NIA 220/NIGC 1 y cierre a 60 días (`motor/revision.py`)

Manteniendo 100 % retrocompatibilidad con las llamadas existentes sin sesión:

- **`firmar_papel_trabajo(..., exigir_segregacion: bool = False, sesion: Any = None, ventana_archivo_dias: int = 60)`:**
  - Si `sesion` está presente, valida `puede_firmar_rol(sesion, rol)`; si el perfil no corresponde al rol solicitado, lanza `ErrorSeguridad`.
  - Si `exigir_segregacion` es `True`, impide que una misma persona física o identidad de usuario (comparando `usuario` de sesión cuando existe, o nombre normalizado en minúsculas y sin espacios sobrantes) firme más de un rol distinto entre `Preparador`, `Revisor` y `Socio` (NIGC 1 / NIA 220).
  - Si `sesion` incluye `semilla_privada_bytes`, firma el contenido canónico de la firma y registra `usuario`, `huella_clave` y `firma_ed25519_b64` dentro de `estado["firmas"][rol]` en `revisiones.json`.
  - Al firmar el rol **`Socio`**, guarda `fecha_cierre_utc` y `ventana_archivo_dias` (60 por defecto), bloquea el papel de trabajo e invoca `sellar_corrida(...)` (cuando hay semilla privada) para emitir `sello.json`.
- **`reabrir_papel_trabajo(..., sesion: Any = None)`:**
  - Si se proporciona `sesion`, exige `sesion.perfil == "Socio"` o `sesion.rol_auditoria == "Socio"`.
  - Si existe `sello.json` en la carpeta de la corrida, registra su resumen SHA-256 previo en `bitacora.jsonl` y lo elimina para invalidar el sello anterior hasta un nuevo cierre formal de Socio.
- **`estado_archivo_nia230(carpeta: str | Path, ventana_dias: int = 60) -> dict`:**
  - Calcula el estado respecto al plazo máximo recomendado de compilación del archivo final de auditoría (**60 días** tras la fecha del informe/cierre según NIA 230, párr. 14 y guía A21), retornando `cerrado`, `fecha_cierre_utc`, `dias_transcurridos`, `dias_restantes`, `ventana_dias` y `archivado_definitivo`.

---

## 4. Interfaz de inicio de sesión y consola de administración (`app/login_qt.py`)

Diseñada en PySide6 bajo los lineamientos estrictos de las **Fichas 17 y 18**:
- Título e identidad visibles: **`FOLIO AUDITOR`** con el lema institucional y el emblema `icono_cuadra("logo", 44)` en barra superior azul Win32 (`#000080 -> #1084D0`).
- Superficie neutra `#D4D0C8` y biseles 3D clásicos (`ESTILO_CUADRA_QT`), sin cadenas `"cuadra"` ni versiones visibles en títulos, etiquetas o botones, y acotando estilos por `#Id { ... }` para no pisar `#BtnPrimary` ni aplicar `setButtonSymbols(NoButtons)` sobre `QDoubleSpinBox`.

Componentes especificados:
1. **`DialogoLoginFolio(gestor=None, permitir_evaluacion=True, parent=None)` (`QDialog`):**
   - **Vista de primer arranque (`not gestor.existe_configuracion()`):** alta obligatoria del **Administrador** (`edt_admin_usr`, `edt_admin_nom`, `edt_admin_pwd`, `edt_admin_pwd2`), alta opcional marcada por defecto del **Preparador** (`chk_crear_prep`, `edt_prep_usr`, `edt_prep_nom`, `edt_prep_pwd`, `edt_prep_pwd2`), casilla `chk_segregacion` (activa por defecto), mensajes en `lbl_error_init`, botón primario `btn_inicializar` (`#BtnPrimary`), botón opcional `btn_evaluacion` (cuando `permitir_evaluacion=True`) y método programático `intentar_inicializar() -> bool`.
   - **Vista operativa (`gestor.existe_configuracion()`):** selector dual exclusivo entre **`btn_modo_preparador`** (`"Preparador / Auditor"`) y **`btn_modo_admin`** (`"Administrador"`) con tarjeta explicativa `lbl_desc_modo` detallando facultades y límites de cada modo, campos `edt_usuario`, `edt_contrasena` (`EchoMode.Password`), `chk_mostrar_pwd`, `lbl_error`, `btn_ingresar` (`#BtnPrimary`), `btn_cancelar`, más los métodos públicos `seleccionar_modo(modo)`, `intentar_login() -> bool` y `sesion_autenticada()`.
2. **`DialogoAdminSeguridad(gestor, sesion_admin, parent=None)` (`QDialog`):**
   - Rechaza en `__init__` cualquier sesión sin `es_admin` lanzando `ErrorSeguridad`.
   - Tres pestañas en `QTabWidget`:
     1. **Usuarios y Roles:** vista tabular (`QTableView` + `ModeloTablaPandas`) con usuario, nombre, perfil, estado y huella Ed25519; formulario de alta (`edt_nuevo_usr`, `edt_nuevo_nom`, `cmb_nuevo_perfil`, `edt_nuevo_pwd`, `btn_crear_usr`); acciones `btn_toggle_estado` y `btn_reset_pwd`.
     2. **Políticas de Seguridad:** `chk_pol_segregacion`, `spn_pol_ventana`, `spn_pol_intentos`, `chk_pol_nube` y `btn_guardar_politicas`.
     3. **Bitácora de Accesos:** indicador de integridad SHA-256 (`lbl_bit_accesos_estado`: `"ÍNTEGRA"` / `"ALTERADA"`) y tabla de eventos (`leer_bitacora_accesos()`).
3. **`DialogoCambiarContrasena(gestor, sesion, parent=None)` (`QDialog`):** valida contraseña actual, nueva y confirmación invocando `gestor.cambiar_contrasena(...)`.

---

## 5. Casos de prueba esperados

| Suite / Caso | Entrada / Condición | Resultado esperado |
| :--- | :--- | :--- |
| **RFC 8032 §7.1 TEST 1 y TEST 2** | Semillas oficiales de prueba RFC 8032 con mensaje vacío (`b""`) y mensaje `b"\x72"` | Clave pública de 32 bytes y firma de 64 bytes idénticas a los vectores oficiales; modificación de 1 bit devuelve `False` |
| **AES-256-GCM y DPAPI** | Cifrado/descifrado de texto normal y `b""`, con `aad`, alteración de 1 bit en tag/cifrado/AAD | Ida y vuelta exacta; cualquier alteración lanza `ErrorSeguridad`; `proteger_dpapi`/`desproteger_dpapi` operan en Windows sin diálogo |
| **Sellado cruzado `sello.json`** | Corrida sellada por `Socio`, alteración de 1 byte en `cedula.xlsx`, cambio en `revisiones.json` o **recálculo completo de la cadena SHA-256 de `bitacora.jsonl`** | `verificar_sello_corrida` devuelve `valido == True` inicialmente y `valido == False` ante cualquier manipulación |
| **Bloqueo y RBAC** | 5 intentos fallidos consecutivos; login de `Preparador` en modo `"Administrador"`; `cambiar_contrasena` | Bloqueo temporal de 15 min tras el 5.º fallo; rechazo por modo incompatible; conservación de `huella_clave` al cambiar contraseña |
| **Segregación y NIA 230** | Mismo usuario intentando firmar `Preparador` y `Revisor` con `exigir_segregacion=True`; reapertura por no-Socio; cálculo de ventana de 60 días | Rechazo de auto-revisión y de reapertura sin rol `Socio`; invalidación de `sello.json` al reabrir; cálculo exacto de `dias_restantes` |
| **UI Login (`QT_QPA_PLATFORM=offscreen`)** | Primer arranque en `DialogoLoginFolio`, inicio dual, apertura de `DialogoAdminSeguridad` por Admin vs Preparador, revisión de textos visibles | Inicialización y login exitosos; `ErrorSeguridad` para Preparador en panel Admin; cero ocurrencias de `"cuadra"` en textos visibles |
