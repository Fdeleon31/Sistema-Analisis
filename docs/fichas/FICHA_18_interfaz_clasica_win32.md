# Ficha 18 · Sistema visual de estación contable clásica Win32 y hoja de cálculo biselada

**Fecha:** noviembre 2026  
**Módulos:** `app/componentes_qt.py`, `app/escritorio.py`, `app/estilos.css`, `app/inicio.py`, `app/comun.py`  
**Referencias públicas:**
- Convenciones de interfaces de escritorio **IBM SAA Common User Access (CUA)** (*Advanced Interface Design Guide*, 1989; *Guide to User Interface Design*, 1991): separación estricta entre cromo estructural de control y lienzo de datos, consistencia espacial de barras y retroalimentación determinista de foco y estado.
- **Microsoft Corporation**, *The Windows Interface Guidelines for Software Design* (Microsoft Press, 1995) y documentación pública de la API Win32 en **Microsoft Learn** (`winuser.h` / `user32.dll`): función `GetSysColor` (`COLOR_3DFACE` / `COLOR_BTNFACE` `#D4D0C8`, `COLOR_3DHILIGHT` `#FFFFFF`, `COLOR_3DSHADOW` `#808080`, `COLOR_3DDKSHADOW` `#404040`, `COLOR_ACTIVECAPTION` `#000080`, `COLOR_GRADIENTACTIVECAPTION` `#1084D0`, `COLOR_CAPTIONTEXT` `#FFFFFF`, `COLOR_HIGHLIGHT` `#000080`) y primitiva de bordes tridimensionales `DrawEdge` (`EDGE_RAISED` y `EDGE_SUNKEN`).
- **Convenciones públicas de interfaz de hoja de cálculo de dos dimensiones** (literatura de interacción humano-computadora y sistemas tabulares contables): matriz ortogonal de celdas sobre fondo de papel `#FFFFFF` con líneas de división `#C0C0C0`, cabeceras biseladas de columnas y filas en `#D4D0C8`, *Cuadro de nombres* (`Name Box`) y *Barra de fórmulas* (`fx`) alojados en pozos hundidos sobre la rejilla, solapas de libro contable y barra de estado inferior segmentada en paneles hundidos.
- **NIA 230** (*Documentación de auditoría* — párrs. 8, 9 y 14–16 y guías A2–A5): suficiencia documental, legibilidad inequívoca y comprensión independiente por un auditor experimentado, junto con la identificación permanente de cliente, período auditado, responsable y marca temporal de ejecución/revisión (en continuidad con la **Ficha 17**).

**Principio rector:** *Legibilidad contable sin ambigüedades, geometría táctil biselada y continuidad íntegra de identidad e iconografía 3D.* La estación de trabajo adopta la estética clásica Win32 y de hoja de cálculo biselada para maximizar el contraste de cifras y papeles de trabajo, conservando íntegramente la identidad ejecutiva `Folio Auditor`, la banda de constancia en tiempo real (Ficha 17) y los íconos vectoriales 3D (`QPainter` y `SVG`) en memoria sin internet.

---

## 1. Objetivo y alcance de sala limpia

Establecer las reglas visuales y estructurales completas para renderizar la mesa de auditoría **`Folio Auditor`** —tanto en la aplicación nativa de escritorio (**PySide6** en `app/componentes_qt.py` y `app/escritorio.py`) como en la interfaz web local (**Streamlit** en `app/estilos.css` y `app/inicio.py`)— bajo un sistema visual de **estación contable clásica Win32 / hoja de cálculo biselada**.

El diseño se define en sala limpia únicamente a partir de estándares y convenciones públicas (CUA, guías Win32 `GetSysColor`/`DrawEdge`, arquitectura de hoja de cálculo bidimensional y NIA 230), sin inspeccionar ni reproducir recursos propietarios de terceros.

### Restricciones de conservación obligatoria
1. **Conservación íntegra de íconos 3D (`SVG` / `QPainter`):** todos los íconos vectoriales 3D renderizados en memoria (`icono_cuadra` en `app/componentes_qt.py`, `LOGO_SVG` en `app/inicio.py` y los íconos `data:image/svg+xml` de la cinta en `app/estilos.css`) permanecen intactos en forma, volumen, sombreado y paleta.
2. **Conservación de identidad ejecutiva `Folio Auditor` (Ficha 17):** se mantiene `NOMBRE_MARCA = "FOLIO AUDITOR"`, `LEMA_MARCA = "Mesa de Auditoría Determinista · Analítica NIA"` y la ausencia total del término interno `"cuadra"` en títulos, cintas, etiquetas y barras visibles al auditor.
3. **Conservación de constancia en tiempo real (Ficha 17):** permanecen activos el cuadro de constancia temporal (`local` + `UTC` en vivo cada segundo mediante `_timer_reloj` en Qt y `@st.fragment(run_every="1s")` en Streamlit), el período auditado (`periodo_inicio al fecha_cierre`) y su sincronización inmediata desde los campos del encargo (`edt_cliente`, `de_inicio`, `de_cierre`).
4. **Independencia del motor determinista:** ningún cambio de esta ficha modifica el cálculo en DuckDB (`motor/`), la ingesta/conectores (`conectores/`) ni la bitácora SHA-256.

---

## 2. Sustento normativo y ergonómico (NIA 230, CUA y hoja 2D)

De acuerdo con la **NIA 230** y los principios clásicos de diseño de estaciones de trabajo de escritorio:

1. **Legibilidad y comprensión independiente (NIA 230, párr. 8; guías A2–A5):**
   - El uso de una superficie neutra mate (`#D4D0C8`) para marcos, barras y controles separa físicamente la instrumentación del área de evidencia contable (`#FFFFFF`), eliminando ruido visual, sombras difusas modernas y bordes ambiguos alrededor de montos, saldos y cuentas.
   - Las líneas ortogonales de rejilla `#C0C0C0` permiten seguir visualmente filas extensas de asientos diarios, conciliaciones bancarias o facturas DGI sin perder la correspondencia entre columna y monto.
2. **Asequibilidad (*affordance*) entre control y dato editable (IBM CUA / Win32):**
   - Todo elemento accionable o estructural (botones de cinta, botones de comando, cabeceras de tabla, pestañas inactivas, etiqueta `fx`) emerge del plano con **bisel 3D elevado**.
   - Todo campo de datos, fórmula o lectura activa (`FormulaBar`, `NameBox`, `QLineEdit`, `QComboBox`, `QTableView`, caja de constancia, paneles de `QStatusBar`) se incrusta en el plano con **bisel 3D hundido (pozo)**, comunicando sin texto adicional dónde reside la información analizada o editable.
3. **Identificación permanente del encargo y momento de realización (NIA 230, párr. 9):**
   - La barra de título clásica con gradiente `#000080 -> #1084D0` ofrece contraste máximo (`#FFFFFF` sobre azul profundo) para identificar el cliente auditado, la aplicación `Folio Auditor` y el bloque de constancia en tiempo real (`YYYY-MM-DD HH:MM:SS (TZ)` + `UTC` + período auditado).

---

## 3. Tokens cromáticos y gramática de biseles 3D

### 3.1 Paleta maestra Win32 / estación contable

| Rol visual | Constante Win32 (`GetSysColor`) | Hexadecimal | Uso en `Folio Auditor` |
| --- | --- | --- | --- |
| Superficie neutra de estación | `COLOR_3DFACE` / `COLOR_BTNFACE` | `#D4D0C8` | Fondo principal de ventana/estación, cinta de opciones, tarjetas/paneles de control, cabeceras de rejilla, pestañas inactivas y barra de estado |
| Luz de bisel y papel de datos | `COLOR_3DHILIGHT` / `COLOR_WINDOW` | `#FFFFFF` | Aristas superior e izquierda de bisel elevado; aristas inferior y derecha de bisel hundido; fondo de celdas de rejilla, barra de fórmulas y campos de entrada |
| Luz media / relieve interior | `COLOR_3DLIGHT` | `#E8E6E0` | Trazo interno claro en botones compuestos, pestañas y cabeceras |
| Sombra media de bisel | `COLOR_3DSHADOW` / `COLOR_BTNSHADOW` | `#808080` | Aristas superior e izquierda de pozos hundidos; sombra interna inferior/derecha de bisel elevado; línea oscura de separadores grabados |
| Sombra profunda de bisel | `COLOR_3DDKSHADOW` | `#404040` | Arista exterior inferior y derecha de controles y marcos elevados; borde exterior profundo en pozos dobles |
| Barra de título (inicio) | `COLOR_ACTIVECAPTION` | `#000080` | Extremo izquierdo del gradiente clásico de barra de título y acento de selección/foco clásico |
| Barra de título (fin) | `COLOR_GRADIENTACTIVECAPTION` | `#1084D0` | Extremo derecho del gradiente horizontal clásico de barra de título |
| Texto de barra de título | `COLOR_CAPTIONTEXT` | `#FFFFFF` | Texto principal del título del libro/cliente y acciones sobre la barra azul |
| Rejilla de hoja de cálculo | — (estándar libro 2D) | `#C0C0C0` | Líneas horizontales y verticales entre celdas de `QTableView` y tablas de datos web |
| Tinta contable principal | `COLOR_WINDOWTEXT` | `#000000` / `#111827` | Texto de celdas, fórmulas, etiquetas y cabeceras para máximo contraste sobre `#FFFFFF` y `#D4D0C8` |
| Acento Excel / verificación | — (semántico auditoría) | `#107C41` / `#15803D` | Botones de exportación a Excel, filete activo en pestañas y estado `BITÁCORA ÍNTEGRA` |
| Semáforos de riesgo NIA | — (semántico auditoría) | `#B91C1C` / `#B45309` / `#1D4ED8` | Barras laterales de `TarjetaKPI`, niveles `alto` (`#FEE2E2`), `medio` (`#FEF3C7`), `bajo` (`#DBEAFE`) y `DelegadoBarraPuntaje` |

### 3.2 Geometría de biseles 3D (fuente de luz superior izquierda a 45°)

Toda la geometría estructural adopta esquinas rectas (`border-radius: 0px`) coherentes con `DrawEdge` de Win32:

1. **Bisel 3D elevado (`EDGE_RAISED`):** simula un elemento que sobresale hacia el auditor.
   - **Borde superior e izquierdo:** `#FFFFFF` (luz directa).
   - **Borde inferior y derecho:** `#404040` en trazo exterior (y `#808080` en trazo interior cuando se aplica doble bisel en botones o cabeceras).
   - **Estado presionado o activo (`:pressed`, `:checked`, botón seleccionado de cinta):** invierte las caras iluminadas y sombreadas (`#808080`/`#404040` arriba-izquierda y `#FFFFFF` abajo-derecha) y desplaza visualmente el contenido `1px` hacia abajo-derecha, marcando el estado activo sin perder contraste.
2. **Bisel 3D hundido / pozo (`EDGE_SUNKEN`):** simula un hueco tallado en la superficie `#D4D0C8`.
   - **Borde superior e izquierdo:** `#808080` (y `#404040` interior en pozos profundos).
   - **Borde inferior y derecho:** `#FFFFFF` (y `#D4D0C8` interior).
   - **Fondo interior:** `#FFFFFF` en zonas editables o de lectura tabular (`FormulaBar`, `FormulaText`, `QLineEdit`, `QComboBox`, `QSpinBox`, `QDateEdit`, `QPlainTextEdit`, `QTableView`), o `#D4D0C8` / azul profundo contrastado en paneles de solo lectura (`QStatusBar`, `#ConstanciaBox`).
3. **Separador grabado (*Etched Divider*):** línea vertical u horizontal compuesta por dos trazos contiguos de `1px`: `#808080` seguido de `#FFFFFF`, utilizada entre grupos de la cinta de herramientas (`.RibbonSep`) y debajo de `.SectionHdr`.

---

## 4. Especificación por zona de la interfaz

### 4.1 Barra de título clásica (`#AppBar` / `.cuadra-appbar`)
- **Fondo:** gradiente horizontal lineal de izquierda a derecha **`#000080 -> #1084D0`** (`qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #000080, stop:1 #1084D0)` en Qt; `linear-gradient(90deg, #000080 0%, #1084D0 100%)` en CSS).
- **Marco:** filete superior `#4A80C4` / `#FFFFFF` sutil y filete inferior de separación `#404040` / `#000040`.
- **Elementos contenidos:**
  - Izquierda: emblema 3D (`icono_cuadra("logo", 34)` / `LOGO_SVG`), etiqueta de marca `FOLIO AUDITOR · Mesa de Auditoría Determinista · Analítica NIA` (`#BrandBadge` en dorado legible `#FDE68A` / `#FCD34D`), título con cliente activo (`#WorkbookTitle`: `Cliente: <nombre>` en `#FFFFFF` negrita) y subtítulo contextual (`#WorkbookSubtitle`).
  - Centro-derecha: pozo de constancia en tiempo real (`#ConstanciaBox` / `.cuadra-constancia-box`) con bisel hundido de alto contraste (`#000050` / `#081E4A` con borde superior/izquierdo `#000033` e inferior/derecho `#60A5FA` o marco clásico `#808080`/`#FFFFFF`) alojando `lbl_constancia_reloj` en fuente monoespaciada `Consolas` (`YYYY-MM-DD  HH:MM:SS (TZ) · HH:MM:SS UTC`) y `lbl_constancia_periodo` (`PERÍODO AUDITADO: YYYY-MM-DD al YYYY-MM-DD`).
  - Derecha: botones rápidos biselados (`#BtnQuick` en `#D4D0C8` con texto `#000000` y bisel `#FFFFFF`/`#404040`; `#BtnQuickExcel` con acento `#107C41` y bisel claro/oscuro) y píldoras de estado (`SIN INTERNET`, `BITÁCORA ÍNTEGRA · SHA-256`, `BITÁCORA ALTERADA`, `BITÁCORA SIN EJECUCIÓN`).

### 4.2 Cinta de opciones biselada y solapas superiores (`#RibbonTabs`, `#RibbonBody` / `.st-key-cuadra_ribbon_box`)
- **Franja de pestañas (`#RibbonTabs` / `.cuadra-ribbon-tabs`):**
  - Base en `#D4D0C8` con línea base `#808080` / `#404040`.
  - Pestaña inactiva (`.RibbonTab`): `#D4D0C8` con borde suave `#808080` y texto `#1E293B` / `#000000`.
  - Pestaña activa (`.RibbonTab[active="true"]`, `.cuadra-ribbon-tab-active`): bisel elevado `#FFFFFF` arriba-izquierda y `#404040` derecha, fondo `#D4D0C8` o `#ECEAE4` conectado sin línea inferior al cuerpo `#RibbonBody`, con franja superior identificadora de `2px` en `#000080` o `#107C41`.
- **Cuerpo de cinta (`#RibbonBody` / `.st-key-cuadra_ribbon_box`):**
  - Fondo `#D4D0C8` con borde superior iluminado (`#FFFFFF`) y borde inferior en sombra (`#808080` / `#404040`).
  - Botones de herramienta (`.RibbonBtn`, `.RibbonActionRun`, `.RibbonActionExcel` y columnas `1..9` en Streamlit):
    - Conservan el diseño vertical (**ícono 3D arriba de 32–34 px + etiqueta legible debajo**) y **todos los íconos 3D SVG/`QPainter`**.
    - En reposo: fondo `#D4D0C8` con bisel elevado sutil (`#FFFFFF` arriba-izquierda, `#808080`/`#404040` abajo-derecha) o marco clásico de barra de herramientas.
    - En *hover*: bisel elevado marcado (`border-top/left: #FFFFFF`, `border-bottom/right: #404040`) con realce suave (`#E4E0D8` o `#FFFBEB`).
    - En estado activo (`:checked` / `primary`): **bisel hundido** (`border-top/left: #808080`, `border-bottom/right: #FFFFFF`), fondo tramado/claro `#ECEAE4` o `#FFFFFF` y franja inferior `#107C41` o `#000080` que identifica el módulo activo de forma inequívoca.
    - Los botones de acción principal (`Correr pruebas` con `.RibbonActionRun` y `Exportar Excel` con `.RibbonActionExcel`) mantienen bisel 3D elevado pronunciado y contraste de acción (`#000080`/`#1B3A5C` y `#107C41`), adoptando `#D4D0C8` con texto `#808080` grabado cuando están deshabilitados.
  - Divisores entre grupos (`.RibbonSep`): separador grabado vertical `#808080` + `#FFFFFF`.
  - Etiquetas de grupo (`.RibbonGroupLbl` / `.cuadra-ribbon-group-lbl`): texto compacto en `#404040` centrado al pie de cada bloque.

### 4.3 Barra de fórmula en pozos hundidos (`#FormulaBar` / `.cuadra-formulabar`)
La barra de fórmula replica la anatomía de una hoja de cálculo clásica de dos dimensiones sobre fondo `#D4D0C8`:
1. **Cuadro de nombres (`#NameBox` / `.cuadra-namebox`):**
   - Pozo hundido (`background-color: #FFFFFF`, `border-top/left: #808080`, `border-bottom/right: #FFFFFF`), ancho mínimo `108–118 px`, fuente `Consolas` / `Courier New` en negrita `#000080` o `#000000` centrada (`NIA-240`, `BENFORD-01`, `DGI-SFEP`, `BANCO-01`, `MUS-530`, `ERP-SQL`, `IA-SQL`, `BITACORA`, `PORTAFOLIO`).
2. **Botón / signo `fx` (`#FxIcon` / `.cuadra-fx`):**
   - Placa biselada elevada `#D4D0C8` (`border-top/left: #FFFFFF`, `border-bottom/right: #808080`/`#404040`) con tipografía `Georgia` itálica negrita en `#000080` / `#404040`.
3. **Pozo de fórmula contextual (`#FormulaText` / `.cuadra-formula-text`):**
   - Pozo hundido extendido (`flex: 1`, `background-color: #FFFFFF`, `border-top/left: #808080`, `border-bottom/right: #FFFFFF`), fuente `Consolas` legible (`#000000`), mostrando la fórmula determinista viva generada por `formula_contextual(...)` con el cliente y período auditado actualizados al instante.
4. **Etiquetas de norma (`.NiaTag` / `.cuadra-nia-tag`):**
   - Pequeñas placas biseladas `#D4D0C8` (`border-top/left: #FFFFFF`, `border-bottom/right: #808080`) con texto en negrita `#000080` para las normas aplicables al módulo activo.

### 4.4 Área de trabajo, controles de entrada y tarjetas KPI
- **Fondo general (`.stApp`, `QMainWindow`, `QDialog`):** `#D4D0C8`, esquinas rectas (`border-radius: 0px`).
- **Paneles y tarjetas (`.PanelCard`, `stExpander`):** superficie `#D4D0C8` o `#F4F2EE` con bisel elevado (`#FFFFFF` / `#404040`), o pozo blanco `#FFFFFF` dentro de marco biselado, y encabezados `.SectionHdr` / `.cuadra-section-hdr` en mayúsculas con separador grabado `#808080` + `#FFFFFF`.
- **Controles de formulario (`QLineEdit`, `QComboBox`, `QSpinBox`, `QDoubleSpinBox`, `QDateEdit`, `QPlainTextEdit`, inputs Streamlit):**
  - Pozos hundidos blancos (`background-color: #FFFFFF`, `border-top/left: #808080`, `border-bottom/right: #FFFFFF`, sombra interior sutil `#404040`), foco marcado en `#000080`.
- **Botones estándar (`QPushButton`, `.stButton > button`, `.stDownloadButton > button`):**
  - Superficie `#D4D0C8` con doble bisel elevado (`#FFFFFF` arriba-izquierda, `#404040` / `#808080` abajo-derecha), texto `#000000`; al hacer clic invierten a bisel hundido.
- **Tarjetas KPI (`TarjetaKPI` / `.cuadra-kpi`):**
  - Alojadas como cédulas de resumen con fondo `#FFFFFF`, bisel clásico (`#808080` / `#FFFFFF` o `#FFFFFF` / `#404040`) y franja izquierda de `4 px` por severidad (`alto` `#B91C1C`, `medio` `#B45309`, `bajo` `#1D4ED8`, `ok` `#107C41`, `neutro` `#000080`), manteniendo cifras tabulares de alto contraste (`#000000`).

### 4.5 Rejilla tipo libro `#C0C0C0` y pestañas de hojas (`QTableView`, `QTabWidget`, Streamlit DataFrame)
- **Marco de tabla (`QTableView`, `[data-testid="stDataFrame"]`):** pozo hundido exterior (`border-top/left: #808080`, `border-bottom/right: #FFFFFF`).
- **Celdas y líneas de libro:** fondo `#FFFFFF`, filas alternas discretas (`#F7F7F5` / `#F8FAFC`), **`gridline-color: #C0C0C0`** mostrando claramente la cuadrícula ortogonal horizontal y vertical tipo libro contable.
- **Encabezados de columna y fila (`QHeaderView::section`):**
  - Fondo `#D4D0C8`, texto `#000000` en negrita (`8.1 pt`), borde biselado elevado (`border-top/left: #FFFFFF`, `border-right/bottom: #808080` / `#404040`) simulando las cabeceras alfabéticas/numéricas de una hoja de cálculo de dos dimensiones.
- **Selección y delegados:**
  - Selección legible (`#000080` con texto `#FFFFFF` o `#DBEAFE` con borde `#000080` cuando convive con celdas de riesgo coloreadas).
  - Se conservan intactos `ModeloTablaPandas` (alineación derecha para `COLUMNAS_MONETARIAS`, fechas ISO, formato `#,##0.00`) y `DelegadoBarraPuntaje` (barras de progreso sobre fondo limpio en columna `puntaje`).
- **Solapas de hojas (`QTabWidget::pane`, `QTabBar::tab`):**
  - Panel blanco `#FFFFFF` con borde biselado (`#FFFFFF` / `#404040`); solapas inactivas en `#D4D0C8` biseladas; solapa activa en `#FFFFFF` (o `#ECEAE4`) con borde superior `#107C41` o `#000080` y texto en negrita.

### 4.6 Barra de estado inferior (`QStatusBar`)
- Fondo clásico `#D4D0C8` con separador superior grabado (`#808080` + `#FFFFFF`).
- Cada segmento informativo (`lbl_sb_izq` y `lbl_sb_der`) se presenta dentro de un **pozo hundido independiente** (`border-top/left: #808080`, `border-bottom/right: #FFFFFF`, texto `#000000` en `8 pt`), mostrando en tiempo de sesión el modo offline y los contadores de filas, pruebas, hallazgos y verificación `SHA-256`.

---

## 5. Conservación de íconos 3D (`QPainter` y `SVG`) y constancia en tiempo real

### 5.1 Inventario protegido de íconos 3D en memoria
1. **Desktop PySide6 (`icono_cuadra` en `app/componentes_qt.py`):**
   - `"logo"` (libro esmeralda + lomo dorado + placa zafiro)
   - `"asientos-nia240"` (hoja de diario + lupa 3D dorada/cristal)
   - `"excepciones-basicas"` (barras isométricas 3D + curva Benford carmesí)
   - `"ventas-fe"` (documento doblado + banda DGI + sello esmeralda)
   - `"bancos-conciliacion"` (extracto PDF + frontón bancario oro/zafiro)
   - `"copiloto"` (consola `SQL>` metálica + destello dorado)
   - `"muestreo-mus"` (matriz de bloques monetarios 3D)
   - `"conectores"` (cilindro metálico 3D de base de datos + conector dorado)
   - `"bitacora"` (libro Excel esmeralda + escudo `SHA-256`)
   - `"encargos"` (carpeta ejecutiva dorada/marina + medallón de firma)
   - `"correr"` (medallón circular esmeralda 3D con triángulo Play)
   - `"excel"` (libro Excel 3D con X blanca en relieve)
2. **Web Streamlit (`app/inicio.py` y `app/estilos.css`):**
   - Emblema `LOGO_SVG` en `.cuadra-appbar`.
   - Los 9 íconos `data:image/svg+xml` en `.st-key-cuadra_ribbon_box [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(1..9) .stButton > button::before`.

### 5.2 Continuidad de constancia en tiempo real (Ficha 17)
- `VentanaCuadra` conserva `_timer_reloj` (`QTimer` de 1 segundo) actualizando `lbl_constancia_reloj` mediante `constancia_tiempo_real()`, deteniéndose limpiamente en `closeEvent`.
- Al editar `edt_cliente`, `de_inicio` o `de_cierre` en `VistaPaqueteWidget`, se actualizan de inmediato `windowTitle()`, `lbl_workbook_title`, `lbl_workbook_sub`, `lbl_constancia_periodo` y la barra de fórmula hundida (`lbl_namebox` / `lbl_formula`).
- `app/inicio.py` conserva `_render_appbar_tiempo_real` con `@st.fragment(run_every="1s")` reflejando cliente, período auditado y marca temporal local/UTC.

---

## 6. Casos de prueba con resultado esperado calculado a mano

| Caso | Entrada / Inspección | Resultado esperado |
| --- | --- | --- |
| Paleta clásica Qt (`ESTILO_CUADRA_QT`) | Inspección de constantes cromáticas en `app/componentes_qt.py` | Incluye superficie `#D4D0C8`, barra de título `#000080` `->` `#1084D0`, aristas `#FFFFFF` / `#808080` / `#404040` y rejilla `#C0C0C0` en `QTableView` |
| Paleta clásica Web (`app/estilos.css`) | Inspección de reglas CSS | `.stApp` y cinta usan `#D4D0C8`; `.cuadra-appbar` usa gradiente `#000080` `->` `#1084D0`; `.cuadra-formulabar` usa pozos hundidos `#808080`/`#FFFFFF`; conserva los 9 `data:image/svg+xml` |
| Simetría de biseles 3D | Inspección de reglas QSS/CSS para botones elevados vs. pozos hundidos | Botón/cabecera elevado tiene luz `#FFFFFF` en `top`/`left` y sombra `#808080`/`#404040` en `bottom`/`right`; pozo hundido (`#FormulaBar`, `#NameBox`, `QLineEdit`, paneles `QStatusBar`) invierte exactamente `#808080` en `top`/`left` y `#FFFFFF` en `bottom`/`right` |
| Conservación de íconos 3D QPainter | Llamada `icono_cuadra(nombre, 34)` para los 12 identificadores | Todos devuelven `QIcon` no nulo (`not icon.isNull()`) con `QPixmap` válido y no monocromo |
| Continuidad de identidad y reloj en escritorio | Instanciación de `VentanaCuadra` y edición de `edt_cliente`, `de_inicio`, `de_cierre` | Sin cadena `"cuadra"` en títulos visibles; `lbl_workbook_title` y `lbl_constancia_periodo` se actualizan en vivo; `lbl_constancia_reloj` muestra hora local y `UTC`; `_timer_reloj` activo hasta `close()` |
| Arranque web y navegación sin errores | `AppTest.from_file("app/inicio.py").run()` | Arranque limpio (`not app.exception`), 9 herramientas de cinta presentes, `LOGO_SVG` y bloque de constancia en tiempo real renderizados |
