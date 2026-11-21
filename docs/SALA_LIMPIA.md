# Reglas de sala limpia

Cuadra se desarrolla de forma independiente. Las especificaciones viven en el
cuaderno de sala limpia (documento aparte, con fecha por ficha).

1. Cada función parte de una ficha escrita con palabras propias desde fuentes públicas.
2. No se copia nada de la ayuda, pantallas, scripts ni archivos de otros productos.
3. No se descompila ni se inspecciona el formato interno de ningún software comercial.
4. Se programa desde la ficha, nunca mirando otro producto al mismo tiempo.
5. Cada ficha tiene casos de prueba con resultado esperado calculado a mano.
6. Solo datos sintéticos. Nada de datos de clientes ni archivos de empleadores.
7. Desarrollo en tiempo, equipo y cuentas personales.
8. El historial de git es parte de la evidencia: commits frecuentes y con mensajes claros.

## Fuentes públicas usadas

- Nigrini, M. J. (2012). *Benford's Law: Applications for Forensic Accounting,
  Auditing, and Fraud Detection*. Wiley. Tabla 7.1 (umbrales MAD) y estadístico Z.
- Documentación de DuckDB: lectura de CSV, funciones de ventana, `generate_series`.
- Documentación de Python: `hashlib` (SHA-256).
- Calendario de feriados de Panamá: Código de Trabajo, art. 46; calendario oficial 2026 publicado en prensa
  (La Estrella de Panamá, 11/12/2025; Telemetro, 2026). Ver `paquetes/excepciones-basicas/calendario/feriados_pa.csv`.
- NIA 240 (revisada), apéndice sobre selección de asientos y otros ajustes (texto publicado por el MIA, 2025).
- PCAOB AU 316.61: características de asientos inapropiados (sin descripción, sin número de cuenta, montos redondos).
- AICPA Audit Sampling Guide, apéndice C: factores de confianza de MUS para cero errores (3.00 con 95 %, 2.31 con 90 %).
- Factura electrónica de Panamá: ficha técnica publicada por la DGI (portal de factura electrónica);
  nombres de campos en ejemplos públicos de XML (Siteck); tipos de documento en Microsoft Learn (localización de Panamá).
