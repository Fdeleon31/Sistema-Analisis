# Ficha 15 · Flujo de revisión por roles, firmas, portafolio de encargos y empaquetado portátil

**Fecha:** noviembre 2026  
**Módulos:** `motor/rutas.py`, `motor/revision.py`, `motor/portafolio.py`, `motor/exportador.py`, `cuadra.spec`, `empaquetar_exe.bat`  
**Referencias públicas:** NIA 220 (*Gestión de la calidad de una auditoría de estados financieros*), NIA 230 (*Documentación de auditoría* — identificación de quién ejecutó y quién revisó el trabajo y en qué fecha).  
**Principio rector:** *Trazabilidad completa de revisión humana.* Toda conclusión de auditoría, cambio de estado de un hallazgo, firma de rol (`Preparador`, `Revisor`, `Socio`) o reapertura de un papel de trabajo queda registrada en la bitácora encadenada SHA-256 (`bitacora.jsonl`) y reflejada en la cédula de trabajo Excel.

---

## 1. Roles y flujo de calidad (NIA 220 / NIA 230)

1. **Roles soportados:** `Preparador`, `Revisor`, `Socio`.
2. **Estados por prueba ejecutada:**
   - `Pendiente`
   - `En revisión`
   - `Aclarado con evidencia`
   - `Hallazgo confirmado`
3. **Reglas de firma de papel de trabajo:**
   - El **Preparador** puede documentar conclusiones y firmar en cualquier momento tras la ejecución determinista.
   - El **Revisor** (Senior / Encargado / Gerente) revisa estados/conclusiones y estampa su firma de revisión.
   - El **Socio** solo puede cerrar con firma definitiva cuando existe firma previa de **Preparador** y no quedan pruebas ejecutadas en estado `Pendiente`.
   - Tras la firma de **Socio**, el papel de trabajo queda **bloqueado** contra modificaciones de conclusiones/estados salvo reapertura explícita con motivo registrado en la bitácora encadenada.
   - Cada revisión o firma se persiste en `revisiones.json` junto a `bitacora.jsonl`, registra un evento SHA-256 encadenado y regenera `cedula.xlsx` incorporando `"Estado"`, `"Conclusión del auditor"` y las firmas de rol en `"Revisiones y Firmas"`.

---

## 2. Portafolio de encargos y corridas históricas

- **Encargos (`encargos/*.yaml`):** plantillas reutilizables por cliente (`cliente`, `fecha_cierre`, `marco`, materialidades, umbrales y roles `preparo`, `reviso`, `aprobo`).
- **Historial de corridas (`salidas/<fecha-hora>/`):** inspecciona corridas pasadas, verifica la integridad criptográfica SHA-256 de `bitacora.jsonl`, muestra cantidad de hallazgos, estado de firmas y permite reabrir para revisión/firma sin alterar los cálculos originales.

---

## 3. Resolución portátil de rutas para ejecutable Windows (`.exe`)

`motor/rutas.py` separa estrictamente:
- `raiz_recursos()`: carpeta de recursos de solo lectura (`sys._MEIPASS` bajo PyInstaller, o raíz del repositorio en desarrollo) para `paquetes/`, `conectores/perfiles/` y `app/estilos.css`.
- `raiz_trabajo()`: carpeta persistente de escritura junto al ejecutable cuando está empaquetado (`Path(sys.executable).parent`), o raíz del repositorio en desarrollo, para `encargos/`, `salidas/` y `datos/ejemplo/`.
