# Ficha 17 · Identidad ejecutiva `Folio Auditor`, constancia en tiempo real y encabezados de cédula

**Fecha:** noviembre 2026  
**Módulos:** `app/comun.py`, `app/escritorio.py`, `app/componentes_qt.py`, `app/inicio.py`, `app/estilos.css`, `motor/exportador.py`, `motor/formato_excel.py`  
**Referencias públicas:** NIA 230 (*Documentación de auditoría* — párrs. 8, 9 y 14–16 y guías A2–A5 sobre suficiencia documental, identificación de la entidad y período auditado, y constancia de fecha/hora de ejecución y revisión), NIA 220 (*Gestión de la calidad de una auditoría de estados financieros*), estándar ISO 8601 (formato de fechas y marcas temporales local/UTC) y especificación OOXML / `openpyxl` (`oddHeader`, `oddFooter` y códigos `&D`, `&T`, `&P`, `&N`).  
**Principio rector:** *Evidencia inequívoca de contexto y oportunidad en cada papel de trabajo.* Ninguna pantalla de trabajo ni cédula Excel exportada o impresa debe carecer de la identificación del cliente activo, el período auditado (`periodo_inicio` al `fecha_cierre`) y la marca temporal real (local y UTC) de ejecución o emisión.

---

## 1. Objetivo

Unificar la identidad ejecutiva **`Folio Auditor`** (*Mesa de Auditoría Determinista · Analítica NIA*) en la aplicación nativa de escritorio (PySide6), en la interfaz web secundaria (Streamlit) y en los libros Excel exportados (`cedula.xlsx`), conservando la iconografía vectorial 3D estilo Excel y suprimiendo referencias internas de desarrollo (`cuadra`) en todos los títulos visibles al auditor. Simultáneamente, incorporar una banda superior de constancia de presentación y auditoría en tiempo real y encabezados/pies de impresión auditables en cada hoja de la cédula Excel.

---

## 2. Sustento normativo (NIA 230 y NIA 220)

De conformidad con la **NIA 230** (*Documentación de auditoría*):
- **Suficiencia y comprensión independiente (párr. 8, guías A2–A5):** la documentación debe permitir que un auditor experimentado, sin conexión previa con el encargo, comprenda la naturaleza, oportunidad y alcance de los procedimientos ejecutados y sus resultados.
- **Identificación del asunto analizado y oportunidad (párr. 9):** los papeles de trabajo deben dejar constancia clara de las características identificatorias del encargo (entidad/cliente y período financiero auditado) y de la fecha en que se completó o revisó el trabajo.
- **Compilación y control de cambios posteriores (párrs. 14–16):** registrar marcas temporales inequívocas (hora local del equipo de trabajo y referencia universal UTC según ISO 8601) evita ambigüedades entre husos horarios al auditar firmas y exportaciones de cédulas.

En conjunto con la **NIA 220** (supervisión y revisión por roles) y la bitácora encadenada SHA-256, esta ficha asegura que tanto la vista interactiva como la versión impresa o archivada en Excel reflejen en todo instante el contexto exacto del encargo.

---

## 3. Utilidades compartidas sin dependencias de UI (`app/comun.py`)

### 3.1 Identidad de marca
- `NOMBRE_MARCA = "FOLIO AUDITOR"`
- `LEMA_MARCA = "Mesa de Auditoría Determinista · Analítica NIA"`

### 3.2 Cálculo y formato del período auditado
1. **`calcular_periodo_inicio(fecha_cierre) -> date`:**
   - Normaliza `date`, `datetime` o cadena ISO (`YYYY-MM-DD`).
   - Si `fecha_cierre` es válida y su mes es `12` (cierre de año calendario), devuelve `date(fc.year, 1, 1)`.
   - Si `fecha_cierre` es válida con mes distinto de `12` y `fc.year > 1`, devuelve el primer día de un ejercicio de 12 meses terminado en `fecha_cierre`: `date(fc.year - 1, fc.month + 1, 1)`.
   - Si `fecha_cierre` es nula, vacía, inválida o `fc.year <= 1`, devuelve el respaldo determinista `date(2025, 1, 1)`.
2. **`formatear_periodo_auditado(periodo_inicio, fecha_cierre) -> str`:**
   - Normaliza `fecha_cierre` (respaldo `date(2025, 12, 31)`) y `periodo_inicio` (si falta o es inválida, la calcula mediante `calcular_periodo_inicio(fc)`).
   - Devuelve `"YYYY-MM-DD al YYYY-MM-DD"` (por ejemplo, `"2025-01-01 al 2025-12-31"`).

### 3.3 Constancia de fecha y hora en tiempo real
- **`constancia_tiempo_real() -> tuple[str, str]`:**
  - Obtiene la fecha y hora real local con zona horaria (`datetime.now().astimezone()`) y su conversión exacta a UTC (`timezone.utc`).
  - Determina la etiqueta corta de zona horaria local (`tzname()` si tiene longitud ≤ 6 y sin espacios, o desplazamiento UTC como `-05`, `+05:30` o `UTC`).
  - Devuelve la tupla `(local_str, utc_str)`:
    - `local_str`: `"YYYY-MM-DD  HH:MM:SS (TZ)"`
    - `utc_str`: `"YYYY-MM-DD HH:MM:SS UTC"`

### 3.4 Fórmula contextual en barra superior
- **`formula_contextual(hid, cliente, fecha_cierre, materialidad, estado_bit, periodo_inicio=None) -> tuple[str, str]`:**
  - Calcula `periodo_txt = formatear_periodo_auditado(periodo_inicio, fecha_cierre)` e incluye `Cliente` y `Periodo` en las fórmulas de contexto de la herramienta activa (por ejemplo, `=AUDITAR.DIARIO(...)` en `asientos-nia240` y `=GESTIONAR.FIRMA(...)` en `encargos`).

---

## 4. Banda superior de constancia y experiencia visual en tiempo real

### 4.1 Identidad ejecutiva y conservación de íconos 3D
- Los títulos visibles (título de ventana, encabezado principal, subtítulos y cintas) utilizan la identidad **`Folio Auditor`** sin exponer el nombre interno `cuadra`.
- Se conservan íntegramente los íconos vectoriales 3D estilo Excel en memoria (`icono_cuadra` en `app/componentes_qt.py` y el emblema `LOGO_SVG` en `app/inicio.py`).

### 4.2 Aplicación de escritorio PySide6 (`app/escritorio.py`, `app/componentes_qt.py`)
1. **Banda superior (`#AppBar`):**
   - `lbl_workbook_title`: muestra la identidad `Folio Auditor` junto al cliente activo (`encargo_datos["cliente"]`).
   - `lbl_constancia_periodo`: muestra el período auditado (`inicio` al `cierre`) obtenido de `formatear_periodo_auditado`.
   - `lbl_constancia_reloj`: muestra la fecha y hora en tiempo real en formato local y UTC mediante `constancia_tiempo_real()`.
2. **Controles del encargo sincronizados (`VistaPaqueteWidget`):**
   - Incluye `edt_cliente` (`QLineEdit`), `de_inicio` (`QDateEdit`) y `de_cierre` (`QDateEdit`).
   - Cualquier cambio en `edt_cliente`, `de_inicio` o `de_cierre` dispara de inmediato la sincronización del encargo y actualiza en vivo `lbl_workbook_title`, `lbl_constancia_periodo` y la barra de fórmula contextual sin esperar a ejecutar pruebas.
3. **Temporizador en vivo (`_timer_reloj`):**
   - `QTimer` configurado en `VentanaCuadra` (intervalo de 1 segundo) que permanece activo durante la sesión para actualizar `lbl_constancia_reloj` y se detiene ordenadamente dentro de `closeEvent` al cerrar la ventana.

### 4.3 Interfaz Web Streamlit (`app/inicio.py`, `app/estilos.css`)
- Muestra la identidad `Folio Auditor` y el emblema 3D en la barra superior, junto con el cliente activo, el período auditado (`periodo_inicio` – `fecha_cierre`) y la marca temporal local/UTC de `constancia_tiempo_real()`, manteniendo arranque limpio sin errores.

---

## 5. Metadatos en hoja `"Encargo"` y encabezados de impresión en cédulas Excel

### 5.1 Hoja `"Encargo"` (`motor/exportador.py`)
Antes de escribir la tabla `"Parámetro" / "Valor"` en la hoja `"Encargo"`, `exportar_excel` asegura mediante `setdefault` las siguientes claves de constancia documental:
- `aplicacion`: `"Folio Auditor · Analítica Determinista"`
- `periodo_auditado`: `"{inicio} al {cierre}"` (tomando `periodo_inicio` del encargo o derivando el inicio fiscal estándar de 12 meses a partir de `fecha_cierre`).
- `fecha_hora_emision_local`: marca de emisión local `"YYYY-MM-DD HH:MM:SS"`.
- `fecha_hora_emision_utc`: marca de emisión UTC `"YYYY-MM-DD HH:MM:SS UTC"`.

### 5.2 Encabezados y pies de página de impresión (`motor/formato_excel.py`)
`exportar_excel` construye la cadena de encabezado:
```text
Folio Auditor | Cliente: <cliente> | Período: <periodo_auditado> | Emitido: <fecha_hora_emision_local>
```
y la entrega a `estilizar_libro(..., encabezado_impresion=...)`, que configura en **todas las hojas** del libro `openpyxl` (fuente `8 pt`):
- `oddHeader.left.text`: cadena anterior (hasta 140 caracteres), garantizando visibilidad del cliente y período auditado al imprimir o exportar a PDF.
- `oddHeader.right.text`: `"&D &T"` (fecha y hora de impresión del libro).
- `oddFooter.left.text`: `"Folio Auditor · Evidencia determinista SHA-256"`.
- `oddFooter.right.text`: `"Página &P de &N"`.

---

## 6. Casos esperados calculados a mano (`tests/test_identidad_constancia.py`)

| Caso | Entrada | Resultado esperado |
| --- | --- | --- |
| Inicio período año calendario | `fecha_cierre = date(2025, 12, 31)` | `date(2025, 1, 1)` |
| Inicio período ejercicio quebrado | `fecha_cierre = date(2025, 6, 30)` | `date(2024, 7, 1)` |
| Inicio período con entrada inválida | `fecha_cierre = "invalida"` / `None` | `date(2025, 1, 1)` |
| Formato período completo | `("2025-01-01", "2025-12-31")` | `"2025-01-01 al 2025-12-31"` |
| Formato período inferido | `(None, date(2025, 6, 30))` | `"2024-07-01 al 2025-06-30"` |
| Constancia en tiempo real | Llamada a `constancia_tiempo_real()` | Tupla `(local, utc)` con fecha/hora real actual, zona local entre paréntesis y sufijo `" UTC"` |
| Cédula Excel (`exportar_excel`) | `encargo = {"cliente": "Distribuidora Canal, S.A.", "periodo_inicio": "2025-01-01", "fecha_cierre": "2025-12-31"}` | Hoja `"Encargo"` contiene `aplicacion`, `periodo_auditado`, `fecha_hora_emision_local`, `fecha_hora_emision_utc`; `ws.oddHeader.left.text` contiene cliente y período |
| Escritorio `VentanaCuadra` | Edición en vivo de `edt_cliente`, `de_inicio`, `de_cierre` y cierre | Actualización inmediata de `lbl_workbook_title` y `lbl_constancia_periodo`; `lbl_constancia_reloj` con hora local/UTC; `_timer_reloj` activo hasta `close()` y sin `"cuadra"` en títulos visibles |
| Web `app/inicio.py` | `AppTest.from_file(...)` | Arranque sin excepciones (`not app.exception`) |
