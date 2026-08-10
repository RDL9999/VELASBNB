#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Calibrador de ratings para el modelo Dixon-Coles.

A partir de las estadísticas históricas de un equipo (goles a favor,
goles en contra y partidos jugados), calcula los ratings alpha (ataque)
y delta (defensa) que alimentan el simulador:

    alpha = (goles_a_favor / partidos) / mu
    delta = (goles_en_contra / partidos) / mu

Con la salida de este script puedes rellenar los campos alpha_* y
delta_* de tu configuración JSON (también de analisis_lote.py).

Uso
---
    python3 calibrar_equipo.py --goles-a-favor 32 --goles-en-contra 18 --partidos 20
    python3 calibrar_equipo.py --goles-a-favor 32 --goles-en-contra 18 --partidos 20 --mu 1.25

Nota: mu es el promedio de goles POR EQUIPO por partido de tu liga.
Por ejemplo, si tu liga promedia 2.5 goles por partido (total), mu ≈ 1.25.
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional, Sequence

from simulador_futbol_mejorado import estimar_ratings


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="calibrar_equipo",
        description="Calcula ratings alpha/delta desde estadísticas del equipo.",
    )
    parser.add_argument("--goles-a-favor", type=float, required=True,
                        help="Goles anotados por el equipo en el periodo.")
    parser.add_argument("--goles-en-contra", type=float, required=True,
                        help="Goles recibidos por el equipo en el periodo.")
    parser.add_argument("--partidos", type=int, required=True,
                        help="Número de partidos del periodo.")
    parser.add_argument("--mu", type=float, default=0.65,
                        help="Promedio de goles por equipo por partido de tu liga.")
    args = parser.parse_args(argv)

    try:
        alpha, delta = estimar_ratings(
            goles_a_favor=args.goles_a_favor,
            goles_en_contra=args.goles_en_contra,
            partidos=args.partidos,
            mu=args.mu,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("=" * 60)
    print("  CALIBRACIÓN DE RATINGS (Kit Dixon-Coles)")
    print("=" * 60)
    print(f"  Goles a favor : {args.goles_a_favor:g}  ({args.partidos} partidos)")
    print(f"  Goles en contra: {args.goles_en_contra:g}")
    print(f"  mu de la liga  : {args.mu:g}")
    print(f"  alpha (ataque) : {alpha:.4f}")
    print(f"  delta (defensa): {delta:.4f}")
    print("=" * 60)
    print("  Úsalo en tu JSON así:")
    print(f'    "alpha_local": {alpha:.2f}, "delta_local": {delta:.2f}')
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
