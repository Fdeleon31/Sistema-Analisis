# Fases y puertas

Cada fase cierra con una puerta medible. Al cerrar una fase: actualiza este
archivo y `CHANGELOG.md`, crea la etiqueta `fase-N` y haz push (ver `GIT.md`).

## Fase 0 · semanas 1 a 4 · Sala limpia y validación (en curso)

- [x] Estructura del repositorio y flujo de git
- [x] Fichas 00 a 03 escritas en el cuaderno de sala limpia
- [x] Prototipo con DuckDB: Benford, duplicados y gaps, con casos que pasan
- [x] Ciclo de estrés: 8 de 8 variantes de exportación y 9 de 9 casos borde (34 pruebas)
- [ ] Pruebas pasan en tu computador (python -m pytest)
- [ ] Layouts de 3 exportaciones reales (solo encabezados y formatos, sin datos de clientes)
- [x] Feriados 2025 verificados (solo feriados nacionales; los días no hábiles bancarios como el lunes de Carnaval quedan fuera)
- [ ] Contrato revisado (cláusulas de propiedad intelectual, confidencialidad, conflicto de interés)
- [ ] Dos semanas de registro de tiempos y dolores con IDEA
- [ ] Cinco entrevistas con auditores de otras firmas

**Puerta:** contrato revisado y 3 dolores confirmados en entrevistas.

## Fase 1 · meses 2 a 4 · MVP de asientos de diario (técnica lista)

- [x] Paquete asientos-nia240: integridad, estratificación, rubros, 10 criterios, selección y muestra impredecible
- [x] Archivo de encargo con materialidad y fecha de cierre
- [x] Muestreo MUS y aleatorio simple
- [x] Cédula con hoja del encargo y columna de conclusión
- [x] Puerta técnica: 3 datasets con resultados idénticos a los esperados (tests/test_fase1.py)
- [ ] Probar con la estructura de 3 exportaciones reales (encabezados y formato, sin datos de clientes)
- [x] Evaluación de muestras MUS con límite superior de error (Ficha 05b)
- [ ] Interfaz para el auditor (decidir: app local sencilla o complemento de Excel)

**Puerta:** resultados idénticos a los esperados en 3 datasets de prueba. Cumplida en el entorno de desarrollo;
falta confirmarla en tu computador con `python -m pytest`.

## Fase 2 · meses 5 a 8 · Piloto pagado

PDF y XML de factura electrónica de la DGI, copiloto en lenguaje natural,
puntaje de riesgo, piloto en un encargo real con horas medidas.

**Puerta:** una firma pagando y horas ahorradas documentadas.

## Fase 3 · meses 9 a 15 · Escala regional

Multiusuario, revisión y roles, ruta hacia una certificación de seguridad,
conectores a ERP comunes en la región, venta a redes de firmas.
