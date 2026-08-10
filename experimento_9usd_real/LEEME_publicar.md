# Publicar.sh — instrucciones de uso

1. Asegúrate de estar en la raíz del repositorio (VELASBNB).
2. Ejecuta:

```bash
bash experimento_9usd_real/publicar.sh
```

3. El script: inicializa git si falta, ejecuta las 28 pruebas del producto,
   hace commit + push a la rama `main` y activa GitHub Pages desde la CLI.
4. Al terminar imprime las URLs finales:
   - Landing: https://RDL9999.github.io/VELASBNB/landing/
   - Demo:    https://RDL9999.github.io/VELASBNB/simulador_futbol_mejorado.html

> Nota: la primera activación de Pages puede tardar 1–2 minutos en estar viva.
> Para comprobar el estado: `gh api repos/RDL9999/VELASBNB/pages --jq '.status'`
