# Flujo de git (solo consola)

## Una sola vez: enlazar la carpeta con GitHub

1. En GitHub crea un repositorio **privado** llamado `cuadra`, sin README ni .gitignore
   (la carpeta ya los trae).
2. En PowerShell:

```powershell
cd $HOME\OneDrive\Desktop\cuadra
git init -b main
git add .
git commit -m "Fase 0: estructura, motor y paquete de excepciones básicas"
git remote add origin https://github.com/TU_USUARIO/cuadra.git
git push -u origin main
```

Si tienes la CLI de GitHub instalada, los pasos 1 y 2 se reducen a:

```powershell
gh repo create cuadra --private --source . --remote origin --push
```

## Día a día

```powershell
git status
git add .
git commit -m "Ficha 04: muestreo MUS, primera versión"
git push
```

Haz commits pequeños y frecuentes: el historial con fechas es parte de la evidencia
de desarrollo independiente. Hacer push seguido también te sirve de respaldo.

## Al cerrar una fase

1. Verifica que todo pasa: `python -m pytest`
2. Actualiza `docs/FASES.md` y `CHANGELOG.md`.
3. Commit, etiqueta y push:

```powershell
git add .
git commit -m "Cierre de Fase 0"
git tag -a fase-0 -m "Fase 0: sala limpia y prototipo"
git push
git push origin fase-0
```

Para ver las fases cerradas: `git tag`. Para volver a ver el código de una fase:
`git checkout fase-0` (y `git checkout main` para regresar).

## Antes de cada push

- `git status` no muestra archivos de `datos/clientes/` ni `.env`.
- Ningún archivo trae datos reales de clientes.
