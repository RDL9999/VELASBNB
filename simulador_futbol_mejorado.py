#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simulador de fútbol Dixon-Coles — versión mejorada.

Este módulo implementa un modelo estadístico para estimar la distribución
de marcadores de un partido de fútbol usando:

    lambda_local     = alpha_local  * delta_visitante * gamma * mu
    lambda_visitante = alpha_visitante * delta_local * mu

y la corrección bivariada de Dixon-Coles para los marcadores bajos.

IMPORTANTE
----------
Los resultados son estimaciones probabilísticas basadas en supuestos
estadísticos (Poisson independiente por equipo con corrección Dixon-Coles).
NO constituyen predicciones garantizadas ni recomendaciones de apuestas.
Los parámetros deben calibrarse con datos históricos reales.

Uso desde la terminal
---------------------
    python3 simulador_futbol_mejorado.py
    python3 simulador_futbol_mejorado.py --config ejemplo_partido.json
    python3 simulador_futbol_mejorado.py --config ejemplo_partido.json --output reporte.json
    python3 simulador_futbol_mejorado.py --sin-montecarlo
"""

from __future__ import annotations

import argparse
import json
import math
from bisect import bisect_left
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Constantes y valores por defecto
# ---------------------------------------------------------------------------

MU_POR_DEFECTO = 0.65          # Goles promedio por equipo por partido.
GAMMA_POR_DEFECTO = 1.20       # Factor de localía (debe calibrarse).
RHO_POR_DEFECTO = -0.15        # Correlación Dixon-Coles (debe calibrarse).
MAX_GOLES_POR_DEFECTO = 10     # Máximo de goles inicial de la matriz.
N_SIMULACIONES_POR_DEFECTO = 50_000
SEMILLA_POR_DEFECTO = 20260726
RHO_MINIMO = -0.30             # Límite de validación para rho.
RHO_MAXIMO = 0.30
TAIL_MAXIMO_ACEPTABLE = 0.01   # 1% de masa fuera de la matriz = relevante.
MAX_GOLES_ABSOLUTO = 30        # Tope para la expansión automática.
Z_WILSON = 1.96                # Valor z para el IC Wilson al 95%.

# Claves de todos los mercados calculados (comunes a matriz exacta y Monte Carlo).
CLAVES_PROBABILIDAD = (
    "local", "empate", "visitante",
    "ambos_marcan",
    "over_1_5", "under_1_5",
    "over_2_5", "under_2_5",
    "over_3_5", "under_3_5",
    "over_4_5", "under_4_5",
    "doble_1X", "doble_X2", "doble_12",
    "porteria_cero_local", "porteria_cero_visitante",
)

AVISO_ESTIMACION = (
    "Los resultados son una ESTIMACIÓN PROBABILÍSTICA basada en un modelo "
    "estadístico. No constituyen una predicción garantizada ni una "
    "recomendación de apuestas."
)


# ---------------------------------------------------------------------------
# Funciones básicas del modelo
# ---------------------------------------------------------------------------

def poisson_pmf(k: int, lam: float) -> float:
    """Función de masa de probabilidad de Poisson P(X = k) con media `lam`."""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def tau(x: int, y: int, lam_local: float, lam_visitante: float, rho: float) -> float:
    """
    Corrección Dixon-Coles para marcadores bajos.

    Ajusta las probabilidades de los marcadores 0-0, 0-1, 1-0 y 1-1
    para reflejar la correlación entre los goles de ambos equipos.
    Para el resto de marcadores devuelve 1 (sin ajuste).
    """
    if x == 0 and y == 0:
        return 1.0 - lam_local * lam_visitante * rho
    if x == 0 and y == 1:
        return 1.0 + lam_local * rho
    if x == 1 and y == 0:
        return 1.0 + lam_visitante * rho
    if x == 1 and y == 1:
        return 1.0 - rho
    return 1.0


def calcular_lambdas(params: "ParametrosPartido") -> Tuple[float, float]:
    """Calcula los goles esperados (lambdas) de cada equipo."""
    lam_local = params.alpha_local * params.delta_visitante * params.gamma * params.mu
    lam_visitante = params.alpha_visitante * params.delta_local * params.mu
    return lam_local, lam_visitante


def estimar_ratings(goles_a_favor: float, goles_en_contra: float,
                    partidos: int, mu: float) -> Tuple[float, float]:
    """
    Estima los ratings alpha y delta a partir de estadísticas históricas.

        alpha = (goles_a_favor / partidos) / mu
        delta = (goles_en_contra / partidos) / mu

    Devuelve una tupla (alpha, delta).
    """
    if partidos <= 0:
        raise ValueError("El número de partidos debe ser mayor que cero.")
    if mu <= 0:
        raise ValueError("mu debe ser mayor que cero.")
    alpha = (goles_a_favor / partidos) / mu
    delta = (goles_en_contra / partidos) / mu
    return alpha, delta


# ---------------------------------------------------------------------------
# Datos de entrada
# ---------------------------------------------------------------------------

@dataclass
class ParametrosPartido:
    """Parámetros de entrada del simulador para un partido."""

    equipo_local: str = "Local"
    equipo_visitante: str = "Visitante"
    alpha_local: float = 1.0
    delta_local: float = 1.0
    alpha_visitante: float = 1.0
    delta_visitante: float = 1.0
    mu: float = MU_POR_DEFECTO
    gamma: float = GAMMA_POR_DEFECTO
    rho: float = RHO_POR_DEFECTO
    max_goles: int = MAX_GOLES_POR_DEFECTO
    n_simulaciones: int = N_SIMULACIONES_POR_DEFECTO
    semilla: int = SEMILLA_POR_DEFECTO
    # Información contextual opcional (altitud, rachas, bajas, etc.).
    # Se muestra como referencia pero NUNCA modifica el cálculo.
    notas: Dict[str, Any] = field(default_factory=dict)


def validar_parametros(params: ParametrosPartido) -> None:
    """
    Valida los parámetros de entrada.

    Lanza ValueError con un mensaje claro si algún valor no es válido.
    """
    errores: List[str] = []

    if not params.equipo_local.strip():
        errores.append("El equipo local no puede estar vacío.")
    if not params.equipo_visitante.strip():
        errores.append("El equipo visitante no puede estar vacío.")

    for nombre, valor in (("alpha_local", params.alpha_local),
                          ("delta_local", params.delta_local),
                          ("alpha_visitante", params.alpha_visitante),
                          ("delta_visitante", params.delta_visitante),
                          ("mu", params.mu),
                          ("gamma", params.gamma)):
        if not isinstance(valor, (int, float)) or valor <= 0:
            errores.append(f"{nombre} debe ser un número mayor que cero (recibido: {valor}).")

    if not isinstance(params.rho, (int, float)):
        errores.append("rho debe ser un número.")
    elif not (RHO_MINIMO <= params.rho <= RHO_MAXIMO):
        errores.append(
            f"rho debe estar entre {RHO_MINIMO} y {RHO_MAXIMO} "
            f"(recibido: {params.rho})."
        )

    if not isinstance(params.n_simulaciones, int) or params.n_simulaciones <= 0:
        errores.append(
            f"n_simulaciones debe ser un entero positivo (recibido: {params.n_simulaciones})."
        )

    if not isinstance(params.max_goles, int) or params.max_goles <= 0:
        errores.append(
            f"max_goles debe ser un entero positivo (recibido: {params.max_goles})."
        )

    if not isinstance(params.semilla, int):
        errores.append(f"semilla debe ser un entero (recibido: {params.semilla}).")

    if errores:
        raise ValueError("Parámetros inválidos:\n - " + "\n - ".join(errores))


def validar_tau(lam_local: float, lam_visitante: float, rho: float) -> None:
    """
    Valida que la corrección Dixon-Coles produzca valores positivos.

    Si algún tau (de los marcadores bajos) es <= 0, el modelo no es válido
    y se detiene el cálculo con un mensaje claro.
    """
    checks: Dict[str, float] = {
        "tau(0,0)": tau(0, 0, lam_local, lam_visitante, rho),
        "tau(0,1)": tau(0, 1, lam_local, lam_visitante, rho),
        "tau(1,0)": tau(1, 0, lam_local, lam_visitante, rho),
        "tau(1,1)": tau(1, 1, lam_local, lam_visitante, rho),
    }
    invalidos = [f"{k}={v:.4f}" for k, v in checks.items() if v <= 0]
    if invalidos:
        raise ValueError(
            "La corrección Dixon-Coles no es válida con estos parámetros. "
            f"Valores tau no positivos: {', '.join(invalidos)}. "
            "Reduce la magnitud de los ratings (alpha/delta) o de |rho|."
        )


# ---------------------------------------------------------------------------
# Matriz teórica exacta
# ---------------------------------------------------------------------------

def construir_matriz(lam_local: float, lam_visitante: float, rho: float,
                     max_goles: int,
                     tail_maximo: float = TAIL_MAXIMO_ACEPTABLE) -> Tuple[List[List[float]], float, int]:
    """
    Construye la matriz de probabilidades de marcadores (0..max_goles) al cuadrado.

    - Si la masa de probabilidad fuera de la matriz es relevante (>= tail_maximo),
      se aumenta automáticamente el máximo de goles.
    - Normaliza la matriz para que sus elementos sumen 1.

    Devuelve (matriz_normalizada, cobertura, max_goles_usado).
    """
    while True:
        # Calcula la matriz sin normalizar.
        matriz_raw: List[List[float]] = []
        for x in range(max_goles + 1):
            fila = []
            for y in range(max_goles + 1):
                p = (poisson_pmf(x, lam_local) * poisson_pmf(y, lam_visitante)
                     * tau(x, y, lam_local, lam_visitante, rho))
                fila.append(p)
            matriz_raw.append(fila)

        total = sum(sum(fila) for fila in matriz_raw)
        cola = 1.0 - total  # masa aproximada fuera de la matriz (tau=1 en la cola).

        if cola >= tail_maximo and max_goles < MAX_GOLES_ABSOLUTO:
            max_goles += 5  # Expansión automática del máximo de goles.
            continue
        break

    # Normalización: la matriz es una distribución de probabilidad.
    matriz = [[p / total for p in fila] for fila in matriz_raw]
    cobertura = total
    return matriz, cobertura, max_goles


def mercados_para_marcador(x: int, y: int) -> set:
    """
    Devuelve el conjunto de claves de mercados que se cumplen con el
    marcador (x, y). Se usa tanto para la matriz exacta como para el Monte Carlo.
    """
    claves: set = set()
    if x > y:
        claves.add("local")
        claves.add("doble_1X")
        claves.add("doble_12")
    elif x == y:
        claves.add("empate")
        claves.add("doble_1X")
        claves.add("doble_X2")
    else:
        claves.add("visitante")
        claves.add("doble_X2")
        claves.add("doble_12")

    total = x + y
    if x > 0 and y > 0:
        claves.add("ambos_marcan")

    for linea, umbral in (("1_5", 1), ("2_5", 2), ("3_5", 3), ("4_5", 4)):
        if total > umbral:
            claves.add(f"over_{linea}")
        else:
            claves.add(f"under_{linea}")

    if x == 0:
        claves.add("porteria_cero_visitante")  # El visitante no encaja.
    if y == 0:
        claves.add("porteria_cero_local")      # El local no encaja.
    return claves


def analizar_matriz(matriz: List[List[float]], lam_local: float,
                    lam_visitante: float) -> Dict[str, float]:
    """
    Calcula todos los mercados a partir de la matriz normalizada.

    Incluye 1X2, ambos marcan, over/under 1.5-4.5, doble oportunidad,
    porterías a cero y goles esperados.
    """
    n = len(matriz)
    probs: Dict[str, float] = {clave: 0.0 for clave in CLAVES_PROBABILIDAD}
    xg_local = 0.0
    xg_visitante = 0.0

    for x in range(n):
        for y in range(n):
            p = matriz[x][y]
            for clave in mercados_para_marcador(x, y):
                probs[clave] += p
            xg_local += x * p
            xg_visitante += y * p

    # Mercados derivados ya incluidos en mercados_para_marcador
    # (doble_1X, doble_X2, doble_12).

    probs["xg_local"] = xg_local
    probs["xg_visitante"] = xg_visitante
    probs["xg_total"] = xg_local + xg_visitante
    return probs


def top_marcadores(matriz: List[List[float]], n_top: int = 10) -> List[Tuple[Tuple[int, int], float]]:
    """Devuelve los `n_top` marcadores más probables como ((x, y), probabilidad)."""
    n = len(matriz)
    lista = [((x, y), matriz[x][y]) for x in range(n) for y in range(n)]
    lista.sort(key=lambda item: item[1], reverse=True)
    return lista[:n_top]


# ---------------------------------------------------------------------------
# Monte Carlo con semilla reproducible
# ---------------------------------------------------------------------------

def _to_uint32(v: int) -> int:
    """Convierte un entero a un entero sin signo de 32 bits."""
    return v & 0xFFFFFFFF


def _to_int32(v: int) -> int:
    """Convierte un entero a un entero con signo de 32 bits (semántica JS)."""
    v = v & 0xFFFFFFFF
    return v - 0x100000000 if v >= 0x80000000 else v


def _xor32(a: int, b: int) -> int:
    """XOR con semántica de 32 bits con signo (operador ^ de JavaScript)."""
    return _to_int32((_to_int32(a) & 0xFFFFFFFF) ^ (_to_int32(b) & 0xFFFFFFFF))


def _or32(a: int, b: int) -> int:
    """OR con semántica de 32 bits con signo (operador | de JavaScript)."""
    return _to_int32((_to_int32(a) & 0xFFFFFFFF) | (_to_int32(b) & 0xFFFFFFFF))


def _imul32(a: int, b: int) -> int:
    """Multiplicación con semántica de 32 bits con signo (Math.imul de JS)."""
    return _to_int32(_to_int32(a) * _to_int32(b))


def generador_mulberry32(semilla: int):
    """
    Generador pseudoaleatorio Mulberry32 (idéntico al del HTML mejorado).

    Replica exactamente la aritmética de 32 bits de JavaScript
    (XOR/OR/Math.imul y desplazamientos `>>>`) para que Python y el HTML
    produzcan EXACTAMENTE las mismas secuencias y resultados con la misma
    semilla. Devuelve una función que produce uniformes en [0, 1).
    """
    a = _to_uint32(semilla)

    def rng() -> float:
        nonlocal a
        a = _to_uint32(a + 0x6D2B79F5)
        t = a
        # t = Math.imul(t ^ (t >>> 15), t | 1)
        t = _imul32(_xor32(t, _to_uint32(t) >> 15), _or32(t, 1))
        # t = (t + Math.imul(t ^ (t >>> 7), t | 61)) ^ t
        inner = _imul32(_xor32(t, _to_uint32(t) >> 7), _or32(t, 61))
        t = _xor32(t + inner, t)
        # t = (t ^ (t >>> 14)) >>> 0
        t = _to_uint32(_xor32(t, _to_uint32(t) >> 14))
        return t / 4294967296.0

    return rng


def monte_carlo(matriz: List[List[float]], n_simulaciones: int,
                semilla: int) -> Tuple[Dict[str, int], float, float]:
    """
    Simula `n_simulaciones` partidos muestreando desde la matriz exacta.

    Usa inversión de la función de distribución acumulada con el generador
    reproducible Mulberry32.

    Devuelve (conteos_por_mercado, suma_goles_local, suma_goles_visitante)
    para poder derivar también los xG simulados.
    """
    # Lista acumulada de celdas (x, y, probabilidad_acumulada).
    n = len(matriz)
    celdas: List[Tuple[int, int, float]] = []
    acum = 0.0
    for x in range(n):
        for y in range(n):
            acum += matriz[x][y]
            celdas.append((x, y, acum))

    acumulados = [c[2] for c in celdas]
    rng = generador_mulberry32(semilla)

    conteos: Dict[str, int] = {clave: 0 for clave in CLAVES_PROBABILIDAD}
    suma_local = 0.0
    suma_visitante = 0.0
    for _ in range(n_simulaciones):
        u = rng()
        idx = bisect_left(acumulados, u)
        idx = min(idx, len(celdas) - 1)
        x, y, _ = celdas[idx]
        suma_local += x
        suma_visitante += y
        for clave in mercados_para_marcador(x, y):
            conteos[clave] += 1
    return conteos, suma_local, suma_visitante


def intervalo_wilson(conteos: int, n_total: int, z: float = Z_WILSON) -> Dict[str, float]:
    """
    Intervalo de confianza de Wilson al 95% para una proporción.

    Devuelve un dict con 'proporcion', 'lim_inf', 'lim_sup' y 'semiamplitud'.
    """
    if n_total <= 0:
        raise ValueError("n_total debe ser mayor que cero.")
    phat = conteos / n_total
    z2 = z * z
    den = 1.0 + z2 / n_total
    centro = (phat + z2 / (2 * n_total)) / den
    margen = z * math.sqrt((phat * (1 - phat) + z2 / (4 * n_total)) / n_total) / den
    lim_inf = max(0.0, centro - margen)
    lim_sup = min(1.0, centro + margen)
    return {
        "proporcion": phat,
        "lim_inf": lim_inf,
        "lim_sup": lim_sup,
        "semiamplitud": (lim_sup - lim_inf) / 2,
    }


# ---------------------------------------------------------------------------
# Orquestación y reportes
# ---------------------------------------------------------------------------

def simular_partido(params: ParametrosPartido,
                    con_monte_carlo: bool = True) -> Dict[str, Any]:
    """
    Ejecuta la simulación completa de un partido.

    1) Valida parámetros y tau.
    2) Calcula lambdas.
    3) Construye la matriz exacta (con expansión automática si hace falta).
    4) Calcula los mercados desde la matriz.
    5) Opcionalmente ejecuta Monte Carlo con semilla reproducible y
       compara contra la matriz exacta.

    Devuelve un dict con el reporte completo.
    """
    validar_parametros(params)
    lam_local, lam_visitante = calcular_lambdas(params)
    validar_tau(lam_local, lam_visitante, params.rho)

    matriz, cobertura, max_goles_usado = construir_matriz(
        lam_local, lam_visitante, params.rho, params.max_goles
    )
    probs = analizar_matriz(matriz, lam_local, lam_visitante)
    tops = top_marcadores(matriz, n_top=10)

    reporte: Dict[str, Any] = {
        "partido": {
            "equipo_local": params.equipo_local,
            "equipo_visitante": params.equipo_visitante,
            "parametros": {
                "alpha_local": params.alpha_local,
                "delta_local": params.delta_local,
                "alpha_visitante": params.alpha_visitante,
                "delta_visitante": params.delta_visitante,
                "mu": params.mu,
                "gamma": params.gamma,
                "rho": params.rho,
                "max_goles_pedido": params.max_goles,
                "max_goles_usado": max_goles_usado,
                "n_simulaciones": params.n_simulaciones,
                "semilla": params.semilla,
            },
            "notas": params.notas,
        },
        "lambdas": {"local": lam_local, "visitante": lam_visitante},
        "matriz_exacta": {
            "cobertura": cobertura,
            "probabilidades": {k: v for k, v in probs.items()
                               if k not in ("xg_local", "xg_visitante", "xg_total")},
            "xg": {"local": probs["xg_local"],
                   "visitante": probs["xg_visitante"],
                   "total": probs["xg_total"]},
            "top_marcadores": [
                {"marcador": f"{x}-{y}", "probabilidad": p}
                for (x, y), p in tops
            ],
        },
        "monte_carlo": None,
        "advertencia": AVISO_ESTIMACION,
    }

    if con_monte_carlo:
        conteos, suma_local, suma_visitante = monte_carlo(
            matriz, params.n_simulaciones, params.semilla
        )
        n = params.n_simulaciones
        mc: Dict[str, Any] = {"n": n, "semilla": params.semilla}
        for clave in CLAVES_PROBABILIDAD:
            wi = intervalo_wilson(conteos[clave], n)
            mc[clave] = {
                "conteo": conteos[clave],
                "proporcion": wi["proporcion"],
                "wilson_lim_inf": wi["lim_inf"],
                "wilson_lim_sup": wi["lim_sup"],
                "wilson_semiamplitud": wi["semiamplitud"],
                "diferencia_matriz": wi["proporcion"] - probs[clave],
            }
        mc["xg"] = {
            "local": suma_local / n,
            "visitante": suma_visitante / n,
            "total": (suma_local + suma_visitante) / n,
        }
        reporte["monte_carlo"] = mc

    return reporte


def imprimir_reporte(reporte: Dict[str, Any]) -> None:
    """Imprime el reporte de forma legible en consola."""
    p = reporte["partido"]
    lams = reporte["lambdas"]
    m = reporte["matriz_exacta"]
    prob = m["probabilidades"]
    xg = m["xg"]

    linea = "=" * 78
    print(linea)
    print("  SIMULADOR DIXON-COLES — Estimación probabilística (no garantizada)")
    print(linea)
    print(f"  Partido: {p['equipo_local']}  vs  {p['equipo_visitante']}")
    par = p["parametros"]
    print(f"  Parámetros: alphaL={par['alpha_local']:.3f} deltaL={par['delta_local']:.3f}"
          f" | alphaV={par['alpha_visitante']:.3f} deltaV={par['delta_visitante']:.3f}")
    print(f"  mu={par['mu']:.3f}  gamma={par['gamma']:.3f}  rho={par['rho']:.3f}")
    print(f"  Lambda local: {lams['local']:.3f}   Lambda visitante: {lams['visitante']:.3f}")
    print(f"  Cobertura de la matriz: {m['cobertura']*100:.2f}%"
          f"  (máximo de goles usado: {par['max_goles_usado']})")

    if p.get("notas"):
        print(f"  Notas contextuales (NO usadas en el cálculo): {p['notas']}")

    print(linea)
    print("  MERCADO 1X2 (matriz exacta)")
    print(f"    1  Gana {p['equipo_local']:<18} {prob['local']*100:6.2f}%")
    print(f"    X  Empate{'':<21} {prob['empate']*100:6.2f}%")
    print(f"    2  Gana {p['equipo_visitante']:<15} {prob['visitante']*100:6.2f}%")
    print(f"    Doble 1X: {prob['doble_1X']*100:.2f}%  |  12: {prob['doble_12']*100:.2f}%  "
          f"|  X2: {prob['doble_X2']*100:.2f}%")

    print(linea)
    print("  MERCADOS DE GOLES (matriz exacta)")
    print(f"    Ambos marcan (Sí): {prob['ambos_marcan']*100:6.2f}%")
    for linea_linea, u in (("1.5", 1), ("2.5", 2), ("3.5", 3), ("4.5", 4)):
        over = prob[f"over_{u}_5"]
        under = prob[f"under_{u}_5"]
        print(f"    Over {linea_linea}: {over*100:6.2f}%   Under {linea_linea}: {under*100:6.2f}%")
    print(f"    Portería a cero {p['equipo_local']}: {prob['porteria_cero_local']*100:.2f}%  |  "
          f"Portería a cero {p['equipo_visitante']}: {prob['porteria_cero_visitante']*100:.2f}%")

    print(linea)
    print(f"  GOLES ESPERADOS: {p['equipo_local']} {xg['local']:.2f}  ·  "
          f"{p['equipo_visitante']} {xg['visitante']:.2f}  ·  Total {xg['total']:.2f}")

    print(linea)
    print("  TOP 10 MARCADORES MÁS PROBABLES")
    for i, item in enumerate(m["top_marcadores"], 1):
        print(f"    {i:>2}. {item['marcador']:>5}   {item['probabilidad']*100:6.2f}%")

    mc = reporte.get("monte_carlo")
    if mc is not None:
        print(linea)
        print(f"  MONTE CARLO (N={mc['n']}, semilla={mc['semilla']}) — comparación vs matriz exacta")
        for clave in CLAVES_PROBABILIDAD:
            d = mc[clave]
            dif = d["diferencia_matriz"] * 100
            print(f"    {clave:<22} MC={d['proporcion']*100:6.2f}%  "
                  f"IC95%=[{d['wilson_lim_inf']*100:6.2f}, {d['wilson_lim_sup']*100:6.2f}]  "
                  f"vs exacta={prob[clave]*100:6.2f}%  (Δ={dif:+.3f}pp)")
        mc_xg = mc["xg"]
        print(f"    xG simulados: local={mc_xg['local']:.3f}  visitante={mc_xg['visitante']:.3f}  "
              f"total={mc_xg['total']:.3f}")

    print(linea)
    print("  AVISO:", AVISO_ESTIMACION)
    print(linea)


def guardar_reporte_json(reporte: Dict[str, Any], ruta: str) -> None:
    """Guarda el reporte en un archivo JSON."""
    with open(ruta, "w", encoding="utf-8") as fh:
        json.dump(reporte, fh, ensure_ascii=False, indent=2)


def cargar_config(ruta: str) -> ParametrosPartido:
    """Carga una configuración JSON de partido.

    Valida que los campos numéricos sean números (y no `null`/texto inválido)
    y lanza ValueError con un mensaje claro en caso contrario.
    """
    def _num(datos: dict, clave: str, por_defecto: float, tipo) -> Any:
        valor = datos.get(clave, por_defecto)
        if valor is None:
            raise ValueError(f"El campo '{clave}' no puede ser null.")
        try:
            return tipo(valor)
        except (TypeError, ValueError):
            raise ValueError(
                f"El campo '{clave}' debe ser un número (recibido: {valor!r})."
            )

    with open(ruta, "r", encoding="utf-8") as fh:
        datos = json.load(fh)

    if not isinstance(datos, dict):
        raise ValueError("El archivo JSON debe contener un objeto de configuración.")

    notas = datos.get("notas", {})
    if notas is not None and not isinstance(notas, dict):
        raise ValueError("El campo 'notas' debe ser un objeto (dict).")

    return ParametrosPartido(
        equipo_local=str(datos.get("equipo_local") or "Local"),
        equipo_visitante=str(datos.get("equipo_visitante") or "Visitante"),
        alpha_local=_num(datos, "alpha_local", 1.0, float),
        delta_local=_num(datos, "delta_local", 1.0, float),
        alpha_visitante=_num(datos, "alpha_visitante", 1.0, float),
        delta_visitante=_num(datos, "delta_visitante", 1.0, float),
        mu=_num(datos, "mu", MU_POR_DEFECTO, float),
        gamma=_num(datos, "gamma", GAMMA_POR_DEFECTO, float),
        rho=_num(datos, "rho", RHO_POR_DEFECTO, float),
        max_goles=_num(datos, "max_goles", MAX_GOLES_POR_DEFECTO, int),
        n_simulaciones=_num(datos, "n_simulaciones",
                            N_SIMULACIONES_POR_DEFECTO, int),
        semilla=_num(datos, "semilla", SEMILLA_POR_DEFECTO, int),
        notas=dict(notas or {}),
    )


def _construir_parser() -> argparse.ArgumentParser:
    """Construye el analizador de argumentos de la línea de comandos."""
    parser = argparse.ArgumentParser(
        prog="simulador_futbol_mejorado",
        description="Simulador Dixon-Coles para partidos de fútbol "
                    "(estimación probabilística, no garantizada).",
    )
    parser.add_argument(
        "--config", default="ejemplo_partido.json",
        help="Ruta del archivo JSON con la configuración del partido "
             "(por defecto: ejemplo_partido.json).",
    )
    parser.add_argument(
        "--output", default=None,
        help="Ruta donde guardar el reporte JSON de resultados "
             "(si no se indica, solo se imprime en consola).",
    )
    parser.add_argument(
        "--sin-montecarlo", action="store_true",
        help="Desactiva la simulación Monte Carlo (solo matriz exacta).",
    )
    parser.add_argument(
        "--n", type=int, default=None,
        help="Sobrescribe el número de simulaciones de Monte Carlo.",
    )
    parser.add_argument(
        "--semilla", type=int, default=None,
        help="Sobrescribe la semilla del Monte Carlo.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Punto de entrada principal de la línea de comandos."""
    parser = _construir_parser()
    args = parser.parse_args(argv)

    try:
        params = cargar_config(args.config)
        if args.n is not None:
            params.n_simulaciones = args.n
        if args.semilla is not None:
            params.semilla = args.semilla

        reporte = simular_partido(params, con_monte_carlo=not args.sin_montecarlo)
        imprimir_reporte(reporte)

        if args.output:
            guardar_reporte_json(reporte, args.output)
            print(f"Reporte guardado en: {args.output}")
        return 0
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
