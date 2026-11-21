# Cuadra

Herramienta de analítica de auditoría con IA para firmas latinoamericanas.
Proyecto personal, en desarrollo por fases. **Estado: Fase 1 (0.4.0): MVP de asientos de diario con muestreo e interfaz para el auditor.**

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
| `asientos-nia240` | mayor y balanza (opcional), más el archivo del encargo | Mayor contra balanza, estratificación, rubros, asientos con criterios de riesgo, selección sugerida y muestra impredecible |

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

## Uso sin consola (recomendado para auditores)

Doble clic en **`iniciar.bat`**. La primera vez prepara todo (tarda unos minutos); después abre
Cuadra en el navegador. Ahí llenas los datos del encargo, subes el diario y la balanza, confirmas
las columnas que Cuadra sugiere y descargas la cédula. Los archivos se procesan solo en tu computador.

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
- [docs/SALA_LIMPIA.md](docs/SALA_LIMPIA.md): reglas de desarrollo independiente.
- [docs/GIT.md](docs/GIT.md): flujo de trabajo con git por consola.
- [CHANGELOG.md](CHANGELOG.md): cambios por versión.

Copyright © 2026 Felipe. Todos los derechos reservados.
