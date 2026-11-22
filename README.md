# Folio Auditor · Mesa de Auditoría Determinista

Herramienta de analítica y documentación determinista de auditoría para firmas latinoamericanas (100 % local, sin conexión a internet).
**Estado: Fase 3 (`0.8.0`): flujo NIA 220/230 (`Preparador → Revisor → Socio`), portafolio de encargos, semáforo previo de integridad contable, constancia ejecutiva en tiempo real (cliente, período auditado y hora local/UTC), cédulas Excel ejecutivas y binario portátil `.exe` para Windows.**

> Repositorio privado. Nunca subas datos de clientes: solo datos sintéticos.

## Qué hace hoy

Importa un mayor general (CSV o Excel), guarda su huella SHA-256, corre el paquete
`excepciones-basicas` y entrega una cédula en Excel con bitácora de evidencia.

| Ficha | Prueba | Qué detecta |
| --- | --- | --- |
| 00 | Importación y bitácora | Huella del archivo, totales de control, registro encadenado de cada paso |
| 01 | Ley de Benford (1 y 2 dígitos) | Distribución anómala de montos; MAD y Z según Nigrini (2012) |
| 02 | Duplicados exactos | Líneas repetidas en fecha, cuenta, monto y descripción |
| 02 | Mismo-mismo-distinto | Un mismo asiento registrado con fechas distintas |
| 03 | Gaps en asientos | Números de asiento faltantes |
| 03 | Gaps en fechas | Días hábiles sin registros, excluyendo feriados de Panamá |

## Paquetes

| Paquete | Archivos | Qué entrega |
| --- | --- | --- |
| `excepciones-basicas` | mayor | Benford, duplicados, gaps en asientos y fechas |
| `asientos-nia240` | mayor y balanza (opcional), más el archivo del encargo | Mayor contra balanza, estratificación, rubros, asientos con criterios de riesgo, puntaje de riesgo explicable (Ficha 11), selección sugerida y muestra impredecible |
| `ventas-fe` | ZIP o carpeta de XML de factura electrónica y mayor (opcional) | Consistencia de totales, CUFE repetido, huecos de numeración, fuera de periodo, ambiente de pruebas y conciliación mensual de ventas |
| `bancos-conciliacion` | Estado de cuenta bancario en PDF (o CSV/Excel) y mayor (opcional) | Extracción local sin internet, continuidad aritmética de saldos, duplicados, movimientos fuera de periodo y conciliación 1 a 1 contra la cuenta de bancos (partidas en tránsito y cargos no registrados) |

Los diez criterios por asiento: fin de semana o feriado, posterior al cierre, cerca del cierre, monto redondo,
justo bajo el umbral de aprobación, descripción vacía o genérica, usuario poco frecuente, cuenta poco usada,
descuadrado y sobre la materialidad de ejecución.

## Instalación (Windows, consola)

Requiere Python 3.11 o superior.

```powershell
cd "$HOME\OneDrive\Desktop\Sistema Analisis"
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Si PowerShell bloquea la activación, corre una vez
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` o usa `.venv\Scripts\activate.bat` desde CMD.

## Uso sin consola (programa nativo de escritorio, 100 % sin internet)

Doble clic en **`iniciar.bat`** (o ejecuta `python cuadra.py escritorio`). Una vez instalado el entorno `.venv`, abre directamente la **aplicación nativa de escritorio para Windows (PySide6 / Qt 6)** con Cinta de Opciones estilo Excel:

- Corre **100 % sin conexión a internet** (iconografía 3D local, bitácora SHA-256 y motor DuckDB en el equipo).
- Lee archivos pesados directamente desde disco sin copiarlos ni subirlos por red.
- Incluye portafolio de encargos guardados (`.yaml`), historial de corridas y flujo de revisión/firma por roles (`Preparador -> Revisor -> Socio`).
- Para generar un ejecutable portátil `.exe` en Windows (sin requerir Python en otros equipos), ejecuta **`empaquetar_exe.bat`** (salida en `dist\LibroAuditoria\LibroAuditoria.exe`).
- Si prefieres la interfaz local en navegador (Streamlit), ejecuta `iniciar.bat web`.

## Uso por consola

```powershell
# Demo con un mayor sintético que trae anomalías sembradas
python cuadra.py ejemplo

# Tu propio archivo (sintético), renombrando columnas si hace falta
python cuadra.py correr --archivo datos\mi_mayor.xlsx --mapeo "No. Asiento=asiento,Importe=monto"

# CSV con coma decimal
python cuadra.py correr --archivo datos\mayor.csv --decimal ","

# Excel con Debe y Haber, en la hoja "Diario"
python cuadra.py correr --archivo datos\diario.xlsx --hoja Diario --debito-credito "Debe,Haber"

# Fechas día/mes/año y 3 filas de título antes del encabezado
python cuadra.py correr --archivo datos\diario.csv --formato-fecha "%d/%m/%Y" --saltar-filas 3
```

El importador nunca corrige en silencio: lo que excluye (totales, líneas en blanco)
y lo que transforma (montos en texto, formatos de fecha) queda en la hoja
"Control de archivos" de la cédula y en la bitácora. Si algo es ambiguo, se detiene y pregunta.

Columnas estándar del mayor: `asiento, linea, fecha, cuenta, descripcion, monto, usuario`.
Los resultados quedan en `salidas\<fecha-hora>\` (cédula y bitácora); esa carpeta no se sube a git.

### Asientos de diario (NIA 240)

```powershell
# Demo con diario y balanza sintéticos
python cuadra.py ejemplo-asientos

# Un encargo: copia encargos\ejemplo-2025.yaml, ajusta materialidad y cierre, y corre
python cuadra.py correr --paquete asientos-nia240 --encargo encargos\mi-encargo.yaml `
  --archivo mayor=datos\diario.xlsx --archivo balanza=datos\balanza.csv --hoja Diario --debito-credito "Debe,Haber"
```

### Factura electrónica de la DGI y Bancos PDF

```powershell
python cuadra.py ejemplo-fe
python cuadra.py ejemplo-bancos
python cuadra.py copiloto --pregunta "Asientos descuadrados" --aprobar
python cuadra.py correr --paquete ventas-fe --encargo encargos\mi-encargo.yaml `
  --archivo facturas=datos\facturas_2025.zip --archivo mayor=datos\diario.xlsx
python cuadra.py correr --paquete bancos-conciliacion --encargo encargos\mi-encargo.yaml `
  --archivo extracto=datos\estado_cuenta.pdf --archivo mayor=datos\diario.xlsx
```

### Sistemas contables de Panamá y fuentes SQL/datos

Cuadra adapta su importador y perfiles de mapeo a los 10 sistemas contables/ERP más usados en Panamá
(`sap-ecc-s4`, `sap-b1`, `softland-exactus`, `sage50-peachtree`, `quickbooks`, `odoo`, `dynamics`,
`netsuite`, `alegra-interfuerza`, `monica-saint`) e ingesta `.csv`, `.tsv`, `.txt` (SAP ALV `|`,
UTF-16/UTF-8/cp1252), `.xlsx`, `.parquet`, `.json`/`.jsonl`, `.sqlite`, `.duckdb`, volcados `.sql`
y conexiones SQL de solo lectura (`SELECT`/`WITH`).

```powershell
# Ver catálogo de perfiles ERP y formatos soportados
python cuadra.py conectores
python cuadra.py conectores --erp sap-b1

# Importar un reporte ALV de SAP o un archivo SQLite/Parquet con autodetección
python cuadra.py correr --archivo datos\fbl3n_alv.txt --erp auto
python cuadra.py correr --archivo datos\diario.sqlite --tabla-origen mayor --erp auto
python cuadra.py correr --archivo datos\odoo_apuntes.parquet --erp odoo --generar-linea
```

### Muestreo

```powershell
# MUS: tamaño, intervalo y selección (inicio aleatorio con semilla, o --inicio explícito)
python cuadra.py muestra --archivo datos\cxc.xlsx --id cliente --valor saldo --tolerable 45000 --confianza 95

# Evaluar la muestra con los errores encontrados (límite superior de error)
python cuadra.py evaluar --errores datos\errores.csv --intervalo 15000 --tolerable 45000

# Aleatorio simple repetible
python cuadra.py muestra --archivo datos\cxc.xlsx --id cliente --metodo aleatorio --n 25 --semilla 2025
```

## Pruebas

```powershell
python -m pytest
```

Cada prueba compara el motor contra resultados calculados a mano en
`paquetes/excepciones-basicas/casos/esperados.json`. Ninguna función se da por
lograda si sus casos no pasan.

## Ciberseguridad, Login y Verificación

- **Control de acceso dual (Escritorio y Web):** asistente inicial y pantalla de inicio de sesión diferenciada para **Administrador** (gestión de cuentas, políticas NIA 220/230 y bitácora de accesos) y **Preparador / Auditor** (`Preparador`, `Revisor`, `Socio`). Para pruebas locales sin prompt puedes usar `python cuadra.py escritorio --sin-login`.
- **Verificación criptográfica y bóveda en reposo:**

```powershell
# Verificar firma Ed25519 (sello.json), hashes de cédula/revisiones y cadena SHA-256
python cuadra.py verificar salidas\20261122-100000

# Postura de entorno (nube/OneDrive, web 127.0.0.1), escaneo SAST y SBOM CycloneDX
python cuadra.py seguridad --entorno --escanear --sbom docs\seguridad\sbom.cdx.json

# Cifrar y descifrar una corrida en bóveda AES-256-GCM (Windows DPAPI o FOLIO_BOVEDA_PASS)
python cuadra.py seguridad --cifrar salidas\20261122-100000 --dpapi
python cuadra.py seguridad --descifrar salidas\20261122-100000

# Puerta completa DevSecOps (escaneo + todas las suites de seguridad + SBOM + lockfile)
.\verificar_seguridad.ps1
```

## Estructura

```
cuadra/
  cuadra.py           línea de comandos
  motor/              importación, ejecución, estadística, bitácora, exportación
  paquetes/
    excepciones-basicas/
      manifiesto.yaml   archivos que pide, pruebas, NIA, parámetros
      pruebas/          una prueba por archivo .sql
      casos/            datos pequeños con resultado esperado
  conectores/         (Fase 2) plantillas por ERP, XML de factura electrónica, PDF
  ia/                 (Fase 2) copiloto, mapeo y redacción
  app/                (Fase 1) interfaz
  docs/               fases, sala limpia y flujo de git
  tests/
```

Para agregar un paquete nuevo basta con crear su carpeta en `paquetes/` con un
`manifiesto.yaml`, sus `.sql` y sus casos; el motor no cambia.

## Documentación

- [docs/FASES.md](docs/FASES.md): fases, puertas y estado.
- [docs/ESTUDIO_MERCADO_PANAMA.md](docs/ESTUDIO_MERCADO_PANAMA.md): análisis de sistemas contables en Panamá y adaptaciones.
- [docs/SALA_LIMPIA.md](docs/SALA_LIMPIA.md): reglas de desarrollo independiente.
- [docs/GIT.md](docs/GIT.md): flujo de trabajo con git por consola.
- [CHANGELOG.md](CHANGELOG.md): cambios por versión.

Copyright © 2026 Felipe. Todos los derechos reservados.
