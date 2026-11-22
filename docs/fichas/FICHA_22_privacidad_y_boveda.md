# Ficha 22 · Privacidad en Reposo, Bóveda Cifrada y Guardarraíles de Cumplimiento (Oleada 3)

**Fecha:** noviembre 2026  
**Módulo:** `motor/privacidad.py` (en integración con `motor/cripto.py`, `motor/seguridad.py`, `motor/bitacora.py`)  
**Pruebas asociadas:** `tests/test_seguridad_privacidad.py`  
**Referencias públicas:**
- **Ley 81 de 26 de marzo de 2019** (*Sobre Protección de Datos Personales*, República de Panamá) y **Decreto Ejecutivo N.º 285 de 28 de mayo de 2021** (Reglamento de la Ley 81, supervisada por ANTAI).
- **Legislación regional equivalente:** **Ley Estatutaria 1581 de 2012** y Decreto 1377 de 2013 (Colombia), **Ley Federal de Protección de Datos Personales en Posesión de los Particulares (LFPDPPP)** (México) y **Ley N.º 8968** (Costa Rica).
- **ISO/IEC 27701:2019** (*Security techniques — Extension to ISO/IEC 27001 and ISO/IEC 27002 for privacy information management*) e **ISO/IEC 27001:2022** (Anexo A.8.10 — Eliminación de información; A.8.11 — Enmascaramiento de datos; A.8.24 — Uso de criptografía).
- **NIST SP 800-57** (*Recommendation for Key Management*), **NIST SP 800-88 Rev. 1** (*Guidelines for Media Sanitization* — sobrescritura lógica antes de liberación en archivos) y **CIS Controls v8** (Control 3 — Protección de Datos).
- **OWASP ASVS v4.0.3** (V8 *Data Protection Verification Requirements*).
- **Microsoft Learn · Windows Security:** comando estándar `icacls.exe` y listas de control de acceso (ACLs) NTFS.
- **NIA 230** (*Documentación de auditoría*) y **NIGC 1** (*Gestión de la calidad*).

**Principio rector:** *Privacidad desde el diseño y por defecto para expedientes de auditoría locales.* Los archivos contables y papeles de trabajo no deben quedar expuestos en texto claro sobre carpetas sincronizadas en nubes de terceros, ni revelar datos identificables de clientes al emitir diagnósticos de soporte técnico, ni permanecer indefinidamente más allá del período legal de retención.

---

## 1. Bóveda cifrada en reposo `.folioenc` (`motor/privacidad.py`)

Permite resguardar archivos individuales o carpetas completas de una corrida (`salidas/<corrida>/` o `encargos/`) reutilizando las primitivas `cifrar_aes_gcm`, `descifrar_aes_gcm`, `derivar_clave_scrypt`, `proteger_dpapi` y `desproteger_dpapi` de `motor/cripto.py`, junto con `ErrorSeguridad` de `motor/seguridad.py`.

### 1.1 Modalidades y formato del contenedor `.folioenc`

Cada archivo cifrado produce un contenedor JSON estructurado con extensión `.folioenc`:

| Campo | Descripción |
| :--- | :--- |
| `version` | Versión del esquema de bóveda (ej. `1`). |
| `algoritmo` | `"AES-256-GCM"` (cifrado autenticado vía Windows CNG `bcrypt.dll`). |
| `modo` | `"scrypt"` (clave derivada de contraseña portátil entre equipos) o `"dpapi"` (clave simétrica protegida mediante Windows DPAPI vinculada al usuario local). |
| `nombre_origen` | Nombre base del archivo original, utilizado como dato autenticado adicional (**AAD** = `nombre_origen.encode("utf-8")`) para detectar sustitución o manipulación de metadatos. |
| `sal_b64` / `clave_dpapi_b64` | Sal aleatoria de 16 bytes (cuando `modo == "scrypt"`) o clave aleatoria de 32 bytes protegida con DPAPI (cuando `modo == "dpapi"`). |
| `nonce_b64`, `tag_b64`, `cifrado_b64` | Vector de inicialización de 12 bytes, etiqueta de autenticación de 16 bytes y texto cifrado en Base64. |

### 1.2 Interfaz de bóveda

- **`cifrar_archivo_boveda(ruta_origen, ruta_destino=None, contrasena=None, usar_dpapi=False, borrar_origen=False) -> Path`:**
  - Valida exclusividad estricta: debe suministrarse `contrasena` no vacía **o** `usar_dpapi=True`, nunca ambos ni ninguno (de lo contrario lanza `ErrorSeguridad`).
  - Lee los bytes de `ruta_origen` y los cifra vinculando `aad = ruta_origen.name.encode("utf-8")`.
  - Escribe el contenedor `.folioenc` en `ruta_destino` (por defecto `<ruta_origen>.folioenc`).
  - Si `borrar_origen=True`, sobrescribe el contenido del archivo original con bytes nulos (`b"\x00"`) y vacía buffers en disco antes de ejecutar `unlink()` como medida de higienización lógica.
- **`descifrar_archivo_boveda(ruta_cifrada, ruta_destino=None, contrasena=None) -> Path`:**
  - Lee y valida el contenedor `.folioenc`, recupera la clave simétrica de 32 bytes según `modo` (`scrypt` exige `contrasena`; `dpapi` invoca `desproteger_dpapi`), verifica `aad` con `nombre_origen` y descifra con `descifrar_aes_gcm`.
  - Si la contraseña, clave DPAPI, etiqueta GCM, datos cifrados o `nombre_origen` fueron alterados, lanza `ErrorSeguridad` sin escribir salida corrupta.
- **`cifrar_carpeta_corrida(...) -> list[Path]`** y **`descifrar_carpeta_corrida(...) -> list[Path]`:**
  - Procesan todos los archivos regulares de una carpeta de corrida (omitiendo `*.folioenc` al cifrar y procesando únicamente `*.folioenc` al descifrar).

---

## 2. Guardarraíles del entorno de trabajo Windows

### 2.1 Detección de carpetas sincronizadas en la nube

- **`detectar_carpeta_sincronizada(ruta: str | Path) -> dict`:**
  - Resuelve e inspecciona los componentes de la ruta (insensible a mayúsculas/minúsculas) frente a clientes de sincronización conocidos: `OneDrive`, `OneDrive - ...`, `Dropbox`, `Google Drive`, `My Drive`, `Mi unidad`, `iCloudDrive` y `Box`.
  - Devuelve:
    ```python
    {
        "en_nube": bool,
        "proveedor": str | None,
        "ruta": str,
        "recomendacion": str,
    }
    ```
  - Su finalidad es alertar al auditor y al equipo de TI antes de almacenar papeles de trabajo en texto claro bajo carpetas que replican automáticamente hacia servidores externos sin aprobación o cifrado previo `.folioenc`.

### 2.2 Permisos restrictivos NTFS (`icacls`)

- **`aplicar_acl_solo_usuario_actual(ruta: str | Path) -> dict`:**
  - En **Windows**, invoca directamente `icacls` mediante `subprocess.run(..., shell=False, capture_output=True, text=True)` (sin shell para evitar inyección de comandos), removiendo herencia permisiva (`/inheritance:r`) y otorgando control (`/grant:r`) exclusivamente al usuario actual (`%USERDOMAIN%\%USERNAME%` o `getpass.getuser()`).
  - En sistemas **POSIX**, aplica `chmod 0o700` sobre directorios y `chmod 0o600` sobre archivos.
  - Devuelve `{"aplicado": bool, "detalle": str}`.

### 2.3 Evaluación integral de postura local

- **`evaluar_postura_entorno(ruta_trabajo: str | Path) -> dict`:**
  - Verifica de forma consolidada:
    1. Si la carpeta de trabajo está expuesta a sincronización en nube (`detectar_carpeta_sincronizada`).
    2. Si `.streamlit/config.toml` (cuando exista en el árbol de trabajo) fija `address = "127.0.0.1"`, `enableXsrfProtection = true`, `enableCORS = false` y `gatherUsageStats = false`.
    3. Si existe configuración de control de acceso local (`seguridad/usuarios.json`).
  - Retorna un diccionario con `estado` (`"OK"` o `"ADVERTENCIA"`) y la lista detallada de hallazgos accionables.

---

## 3. Anonimización de PII regional, diagnóstico de soporte y retención

### 3.1 Anonimización determinista de PII (`anonimizar_texto_pii`)

- **`anonimizar_texto_pii(texto: str, terminos_sensibles: list[str] | None = None) -> str`:**
  Aplica reemplazos deterministas sin alterar la estructura técnica de los mensajes:
  - **Términos sensibles explícitos** (razón social del cliente, marcas o nombres propios declarados) → `[CONFIDENCIAL]`.
  - **Correos electrónicos** → `[EMAIL]`.
  - **Cédulas personales de Panamá** (`8-123-4567`, `PE-12-3456`, `E-8-123456`, `N-...`) y **RUCs panameños** (p. ej. `155678901-2-2024`, con o sin sufijo `DV`) → `[ID-PA]`.
  - **Números de cuentas bancarias y referencias largas** (patrones `\b\d{2,4}(?:-\d{2,4}){2,4}\b` y secuencias continuas `>= 10` dígitos) → `[CUENTA]`.
  - **Teléfonos** locales e internacionales habituales → `[TELEFONO]`.

### 3.2 Exportación de diagnóstico técnico anonimizado

- **`exportar_diagnostico_anonimizado(carpeta_corrida: str | Path, destino: str | Path | None = None) -> dict`:**
  - Lee `bitacora.jsonl` de la corrida indicada y construye un resumen JSON destinado exclusivamente a soporte técnico o análisis de incidentes:
    - Omite nombres de clientes, valores monetarios individuales y rutas absolutas del equipo del usuario (`C:\Users\<usuario>\...`).
    - Filtra cadenas textuales mediante `anonimizar_texto_pii`.
    - Conserva únicamente metadatos técnicos auditables: conteos por tipo de evento, resultado de verificación de cadena SHA-256 (`Bitacora.verificar()`), paquete analítico y versión del motor.
  - Si se especifica `destino`, guarda el JSON resultante en disco.

### 3.3 Retención y purga controlada

- **`purgar_corridas_expiradas(carpeta_salidas: str | Path, dias_retencion: int = 1825, simular: bool = True) -> list[Path]`:**
  - Plazo por defecto de **1,825 días (5 años)** alineado con la conservación mínima de documentación contable y de auditoría.
  - Examina subcarpetas en `salidas/` tomando la fecha del prefijo `YYYYMMDD-*` (o, en su defecto, la marca temporal de modificación del directorio) y selecciona aquellas cuya antigüedad exceda `dias_retencion`.
  - Opera en modo **simulación segura por defecto (`simular=True`)** para permitir la revisión previa antes de la eliminación efectiva; cuando `simular=False`, elimina las carpetas expiradas mediante `shutil.rmtree` y devuelve la lista de rutas afectadas.

---

## 4. Casos esperados y prueba de cero conexiones salientes (`tests/test_seguridad_privacidad.py`)

| Caso de verificación | Escenario sintético | Resultado esperado |
| :--- | :--- | :--- |
| **Bóveda `scrypt` y `DPAPI`** | Cifrado y descifrado de archivo individual y carpeta de corrida con contraseña y con `usar_dpapi=True` | Contenido recuperado bit a bit idéntico; `borrar_origen=True` sobrescribe y elimina el archivo fuente |
| **Integridad GCM / AAD** | Alteración de 1 byte en `cifrado_b64` o modificación de `nombre_origen` dentro de `.folioenc` | `descifrar_archivo_boveda` rechaza la operación lanzando `ErrorSeguridad` |
| **Detección de nube** | Rutas `C:\Users\Demo\OneDrive - Firma\Trabajo`, `...\Dropbox\Cliente` y `C:\AuditoriaLocal\Proyecto` | `en_nube == True` para OneDrive/Dropbox; `en_nube == False` para ruta local aislada |
| **Anonimización PII y diagnóstico** | Texto y bitácora con cédula `8-123-4567`, RUC `155678901-2-2024`, correo, cuenta bancaria y cliente sintético | Todos los identificadores quedan enmascarados con `[ID-PA]`, `[EMAIL]`, `[CUENTA]`, `[CONFIDENCIAL]`; sin rutas de usuario ni montos individuales |
| **Purga por retención** | Carpeta `20180101-101010` frente a corrida reciente | `simular=True` lista la carpeta expirada sin borrarla; `simular=False` elimina únicamente la expirada |
| **Cero telemetría / cero sockets salientes** | `monkeypatch` bloqueando `socket.socket.connect` y `socket.create_connection` durante `ejecutar_encargo("asientos-nia240", ...)` | Ejecución completa exitosa con **0 intentos de conexión de red saliente** |
