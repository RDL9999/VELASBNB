#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Análisis por lotes de partidos con el modelo Dixon-Coles.

Analiza varios partidos a la vez y genera un resumen comparativo y un
reporte JSON completo. Es la herramienta que hace del kit algo más que
una demo web: ideal para analistas que quieren evaluar una jornada
completa de su liga.

Uso
---
    python3 analisis_lote.py jornada.json
    python3 analisis_lote.py jornada.json --output resumen.json
    python3 analisis_lote.py jornada.json --sin-montecarlo

Formato de "jornada.json" (lista de partidos):

    {
      "mu": 0.65, "gamma": 1.30, "rho": -0.15,
      "n_simulaciones": 50000, "semilla": 20260726, "max_goles": 10,
      "partidos": [
        {"local": "Pachuca", "visitante": "Querétaro",
         "alpha_local": 1.85, "delta_local": 0.70,
         "alpha_visitante": 0.70, "delta_visitante": 1.15},
        ...
      ]
    }

Los campos que no aparezcan en un partido se heredan del nivel superior.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List, Optional, Sequence

from simulador_futbol_mejorado import (
    ParametrosPartido,
    simular_partido,
)

CLAVES_RESUMEN = ("local", "empate", "visitante",
                  "doble_1X", "doble_X2", "doble_12",
                  "ambos_marcan",
                  "over_2_5", "under_2_5")


def _numero(datos: Dict[str, Any], clave: str, por_defecto: Any, tipo) -> Any:
    """Lee un campo numérico heredando el valor por defecto del nivel superior."""
    valor = datos.get(clave, por_defecto)
    if valor is None:
        raise ValueError(f"El campo '{clave}' no puede ser null.")
    try:
        return tipo(valor)
    except (TypeError, ValueError):
        raise ValueError(f"El campo '{clave}' debe ser un número (recibido: {valor!r}).")


def cargar_jornada(ruta: str) -> Dict[str, Any]:
    """Carga y valida la estructura del archivo de jornada."""
    with open(ruta, "r", encoding="utf-8") as fh:
        datos = json.load(fh)

    if not isinstance(datos, dict):
        raise ValueError("El archivo JSON debe contener un objeto de jornada.")

    partidos = datos.get("partidos")
    if not isinstance(partidos, list) or len(partidos) == 0:
        raise ValueError("Debe existir una lista no vacía 'partidos'.")

    return datos


def construir_params(datos: Dict[str, Any], partido: Dict[str, Any]) -> ParametrosPartido:
    """Construye los parámetros de un partido heredando la configuración global."""
    if not isinstance(partido, dict):
        raise ValueError("Cada partido debe ser un objeto con 'local' y 'visitante'.")
    local = partido.get("local")
    visitante = partido.get("visitante")
    if not local or not visitante:
        raise ValueError("Cada partido debe tener 'local' y 'visitante'.")

    return ParametrosPartido(
        equipo_local=str(local),
        equipo_visitante=str(visitante),
        alpha_local=_numero(partido, "alpha_local", _numero(datos, "alpha_local", 1.0, float), float),
        delta_local=_numero(partido, "delta_local", _numero(datos, "delta_local", 1.0, float), float),
        alpha_visitante=_numero(partido, "alpha_visitante", _numero(datos, "alpha_visitante", 1.0, float), float),
        delta_visitante=_numero(partido, "delta_visitante", _numero(datos, "delta_visitante", 1.0, float), float),
        mu=_numero(partido, "mu", _numero(datos, "mu", 0.65, float), float),
        gamma=_numero(partido, "gamma", _numero(datos, "gamma", 1.20, float), float),
        rho=_numero(partido, "rho", _numero(datos, "rho", -0.15, float), float),
        max_goles=int(_numero(partido, "max_goles", _numero(datos, "max_goles", 10, float), float)),
        n_simulaciones=int(_numero(partido, "n_simulaciones",
                                   _numero(datos, "n_simulaciones", 50000, float), float)),
        semilla=int(_numero(partido, "semilla", _numero(datos, "semilla", 20260726, float), float)),
        notas=dict(partido.get("notas") or {}),
    )


def imprimir_resumen(resultados: List[Dict[str, Any]]) -> None:
    """Imprime una tabla comparativa de la jornada."""
    linea = "=" * 96
    print(linea)
    print("  ANÁLISIS DE JORNADA — Kit Dixon-Coles (estimación probabilística)")
    print(linea)
    cabecera = (f"  {'Partido':<34}{'1':>6}{'X':>6}{'2':>6}{'1X':>6}{'12':>6}"
                f"{'X2':>6}{'BTTS':>6}{'O2.5':>6}{'U2.5':>6}")
    print(cabecera)
    print(linea)
    for r in resultados:
        p = r["partido"]
        prob = r["matriz_exacta"]["probabilidades"]
        nombre = f"{p['equipo_local']} vs {p['equipo_visitante']}"
        print(f"  {nombre:<34}"
              f"{prob['local']*100:>6.1f}{prob['empate']*100:>6.1f}{prob['visitante']*100:>6.1f}"
              f"{prob['doble_1X']*100:>6.1f}{prob['doble_12']*100:>6.1f}{prob['doble_X2']*100:>6.1f}"
              f"{prob['ambos_marcan']*100:>6.1f}{prob['over_2_5']*100:>6.1f}{prob['under_2_5']*100:>6.1f}")
    print(linea)
    print("  1X2: local / empate / visitante · 1X, 12, X2: doble oportunidad")
    print("  BTTS: ambos marcan · O2.5/U2.5: over/under 2.5 goles")
    print(linea)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="analisis_lote",
        description="Análisis por lotes de partidos con el modelo Dixon-Coles.",
    )
    parser.add_argument("jornada", help="Archivo JSON con la lista de partidos.")
    parser.add_argument("--output", default=None,
                        help="Ruta para guardar el reporte JSON completo de la jornada.")
    parser.add_argument("--sin-montecarlo", action="store_true",
                        help="Desactiva Monte Carlo (solo matriz exacta, más rápido).")
    args = parser.parse_args(argv)

    try:
        datos = cargar_jornada(args.jornada)
        globales = datos.get("globales") or {}
        con_mc = not args.sin_montecarlo

        resultados: List[Dict[str, Any]] = []
        errores: List[str] = []
        for i, partido in enumerate(datos["partidos"], 1):
            try:
                params = construir_params(datos, partido)
                reporte = simular_partido(params, con_monte_carlo=con_mc)
                resultados.append(reporte)
            except ValueError as exc:
                errores.append(f"Partido {i}: {exc}")

        if resultados:
            imprimir_resumen(resultados)

        if errores:
            print("Partidos con error (omitió análisis):")
            for e in errores:
                print(f"  - {e}")

        if args.output:
            resumen = {
                "globales": globales,
                "con_monte_carlo": con_mc,
                "partidos": resultados,
                "errores": errores,
                "advertencia": "Estimación probabilística, no predicción garantizada "
                               "ni recomendación de apuestas.",
            }
            with open(args.output, "w", encoding="utf-8") as fh:
                json.dump(resumen, fh, ensure_ascii=False, indent=2)
            print(f"Reporte de jornada guardado en: {args.output}")

        return 0 if not errores or resultados else 1
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
