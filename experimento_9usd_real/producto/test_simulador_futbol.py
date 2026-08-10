#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pruebas unitarias para simulador_futbol_mejorado.py.

Ejecutar con:
    python3 -m unittest -v test_simulador_futbol.py
"""

import json
import math
import tempfile
import unittest

import simulador_futbol_mejorado as sim


class TestPoissonPmf(unittest.TestCase):
    """Pruebas de la función de masa de probabilidad de Poisson."""

    def test_valores_conocidos(self):
        self.assertAlmostEqual(sim.poisson_pmf(0, 1.0), math.exp(-1.0), places=9)
        self.assertAlmostEqual(sim.poisson_pmf(1, 1.0), math.exp(-1.0), places=9)
        self.assertAlmostEqual(sim.poisson_pmf(2, 2.0), math.exp(-2.0) * 4 / 2, places=9)
        self.assertAlmostEqual(sim.poisson_pmf(3, 5.0),
                               math.exp(-5.0) * (5.0 ** 3) / math.factorial(3), places=9)

    def test_lambda_cero(self):
        self.assertEqual(sim.poisson_pmf(0, 0.0), 1.0)
        self.assertEqual(sim.poisson_pmf(1, 0.0), 0.0)


class TestMatrizExacta(unittest.TestCase):
    """Pruebas de la construcción y análisis de la matriz teórica."""

    def setUp(self):
        self.lam_local = 1.8
        self.lam_visitante = 0.32
        self.matriz, self.cobertura, self.max_goles = sim.construir_matriz(
            self.lam_local, self.lam_visitante, -0.15, 10
        )

    def test_suma_matriz_es_uno(self):
        total = sum(sum(fila) for fila in self.matriz)
        self.assertAlmostEqual(total, 1.0, places=9)

    def test_suma_1x2_es_uno(self):
        probs = sim.analizar_matriz(self.matriz, self.lam_local, self.lam_visitante)
        suma = probs["local"] + probs["empate"] + probs["visitante"]
        self.assertAlmostEqual(suma, 1.0, places=9)

    def test_probabilidades_en_rango(self):
        probs = sim.analizar_matriz(self.matriz, self.lam_local, self.lam_visitante)
        for clave, valor in probs.items():
            if clave.startswith("xg"):
                continue
            self.assertGreaterEqual(valor, 0.0, msg=f"{clave} negativo")
            self.assertLessEqual(valor, 1.0, msg=f"{clave} mayor que 1")

    def test_sobre_y_under_suman_uno(self):
        probs = sim.analizar_matriz(self.matriz, self.lam_local, self.lam_visitante)
        for u in (1, 2, 3, 4):
            over = probs[f"over_{u}_5"]
            under = probs[f"under_{u}_5"]
            self.assertAlmostEqual(over + under, 1.0, places=9)

    def test_cobertura_casi_uno(self):
        self.assertGreater(self.cobertura, 0.99)

    def test_expansion_automatica(self):
        # Lambdas grandes: el máximo pedido (2) deja demasiada cola,
        # por lo que el máximo usado debe crecer automáticamente.
        _, _, usado = sim.construir_matriz(6.0, 5.0, -0.15, 2)
        self.assertGreater(usado, 2)


class TestValidacion(unittest.TestCase):
    """Pruebas de validación de parámetros y de tau."""

    def test_parametro_negativo(self):
        p = sim.ParametrosPartido(alpha_local=-1.0)
        with self.assertRaises(ValueError):
            sim.validar_parametros(p)

    def test_mu_cero(self):
        p = sim.ParametrosPartido(mu=0.0)
        with self.assertRaises(ValueError):
            sim.validar_parametros(p)

    def test_rho_fuera_de_rango(self):
        p = sim.ParametrosPartido(rho=0.50)
        with self.assertRaises(ValueError):
            sim.validar_parametros(p)

    def test_n_simulaciones_invalido(self):
        p = sim.ParametrosPartido(n_simulaciones=-3)
        with self.assertRaises(ValueError):
            sim.validar_parametros(p)

    def test_rechazo_tau_invalido(self):
        # Lambda local muy grande con rho negativo hace tau(0,1) <= 0.
        with self.assertRaises(ValueError):
            sim.validar_tau(37.5, 1.0, -0.30)
        # rho = 1.0 hace tau(1,1) = 0 (y además está fuera de rango).
        with self.assertRaises(ValueError):
            sim.validar_tau(1.0, 1.0, 1.0)

    def test_tau_valido_no_lanza(self):
        sim.validar_tau(1.8, 0.32, -0.15)


class TestLambdas(unittest.TestCase):
    """Pruebas del cálculo de goles esperados (lambdas)."""

    def test_calculo_lambdas(self):
        p = sim.ParametrosPartido(
            alpha_local=1.85, delta_visitante=1.15,
            alpha_visitante=0.70, delta_local=0.70,
            mu=0.65, gamma=1.30,
        )
        lam_local, lam_visitante = sim.calcular_lambdas(p)
        self.assertAlmostEqual(lam_local, 1.85 * 1.15 * 1.30 * 0.65, places=9)
        self.assertAlmostEqual(lam_visitante, 0.70 * 0.70 * 0.65, places=9)


class TestRatings(unittest.TestCase):
    """Pruebas de la estimación de ratings desde estadísticas históricas."""

    def test_estimar_ratings(self):
        alpha, delta = sim.estimar_ratings(goles_a_favor=9, goles_en_contra=3,
                                           partidos=5, mu=0.65)
        self.assertAlmostEqual(alpha, (9 / 5) / 0.65, places=9)
        self.assertAlmostEqual(delta, (3 / 5) / 0.65, places=9)

    def test_estimar_ratings_invalidos(self):
        with self.assertRaises(ValueError):
            sim.estimar_ratings(9, 3, partidos=0, mu=0.65)
        with self.assertRaises(ValueError):
            sim.estimar_ratings(9, 3, partidos=5, mu=0.0)


class TestMonteCarlo(unittest.TestCase):
    """Pruebas del Monte Carlo reproducible."""

    def setUp(self):
        self.lam_local = 1.8
        self.lam_visitante = 0.32
        self.matriz, _, _ = sim.construir_matriz(
            self.lam_local, self.lam_visitante, -0.15, 10
        )

    def test_reproducibilidad_con_misma_semilla(self):
        c1, s1l, s1v = sim.monte_carlo(self.matriz, 5000, semilla=42)
        c2, s2l, s2v = sim.monte_carlo(self.matriz, 5000, semilla=42)
        self.assertEqual(c1, c2)
        self.assertEqual(s1l, s2l)
        self.assertEqual(s1v, s2v)

    def test_semillas_distintas_dan_resultados_distintos(self):
        c1, _, _ = sim.monte_carlo(self.matriz, 5000, semilla=1)
        c2, _, _ = sim.monte_carlo(self.matriz, 5000, semilla=999)
        self.assertNotEqual(c1, c2)

    def test_mc_converge_a_matriz(self):
        conteos, suma_local, suma_visitante = sim.monte_carlo(
            self.matriz, 200000, semilla=123
        )
        probs = sim.analizar_matriz(self.matriz, self.lam_local, self.lam_visitante)
        n = 200000
        for clave in ("local", "empate", "visitante", "ambos_marcan"):
            self.assertAlmostEqual(conteos[clave] / n, probs[clave], delta=0.01)
        self.assertAlmostEqual(suma_local / n, probs["xg_local"], delta=0.05)
        self.assertAlmostEqual(suma_visitante / n, probs["xg_visitante"], delta=0.05)

    def test_wilson_intervalo_valido(self):
        wi = sim.intervalo_wilson(conteos=500, n_total=1000)
        self.assertGreaterEqual(wi["lim_inf"], 0.0)
        self.assertLessEqual(wi["lim_sup"], 1.0)
        self.assertLessEqual(wi["lim_inf"], wi["proporcion"])
        self.assertLessEqual(wi["proporcion"], wi["lim_sup"])
        self.assertAlmostEqual(wi["proporcion"], 0.5, places=2)


class TestIntegracion(unittest.TestCase):
    """Prueba de flujo completo simular_partido."""

    def test_reporte_completo(self):
        p = sim.ParametrosPartido(
            equipo_local="Pachuca", equipo_visitante="Querétaro",
            alpha_local=1.85, delta_local=0.70,
            alpha_visitante=0.70, delta_visitante=1.15,
            mu=0.65, gamma=1.30, rho=-0.15,
            max_goles=10, n_simulaciones=20000, semilla=20260726,
        )
        reporte = sim.simular_partido(p, con_monte_carlo=True)
        self.assertIn("matriz_exacta", reporte)
        self.assertIn("monte_carlo", reporte)
        self.assertIsNotNone(reporte["monte_carlo"])
        self.assertAlmostEqual(
            reporte["matriz_exacta"]["cobertura"], 1.0, delta=0.01
        )
        self.assertGreater(reporte["lambdas"]["local"], 0)
        self.assertGreater(reporte["lambdas"]["visitante"], 0)

    def test_reporte_sin_monte_carlo(self):
        p = sim.ParametrosPartido(n_simulaciones=100, semilla=1)
        reporte = sim.simular_partido(p, con_monte_carlo=False)
        self.assertIsNone(reporte["monte_carlo"])

    def test_aviso_presente(self):
        p = sim.ParametrosPartido()
        reporte = sim.simular_partido(p, con_monte_carlo=False)
        self.assertTrue("estimación" in reporte["advertencia"].lower())


class TestCargarConfig(unittest.TestCase):
    """Pruebas de robustez al cargar configuraciones JSON."""

    def _escribir(self, contenido):
        """Escribe contenido JSON en un archivo temporal y devuelve su ruta."""
        with tempfile.NamedTemporaryFile("w", suffix=".json",
                                         delete=False, encoding="utf-8") as fh:
            fh.write(contenido)
            return fh.name

    def _config_valida(self):
        return {
            "equipo_local": "A", "equipo_visitante": "B",
            "alpha_local": 1.5, "delta_local": 0.8,
            "alpha_visitante": 0.9, "delta_visitante": 1.1,
            "mu": 0.65, "gamma": 1.2, "rho": -0.15,
            "max_goles": 10, "n_simulaciones": 1000, "semilla": 1,
        }

    def test_config_valida(self):
        ruta = self._escribir(json.dumps(self._config_valida()))
        try:
            params = sim.cargar_config(ruta)
            self.assertEqual(params.equipo_local, "A")
            self.assertEqual(params.alpha_local, 1.5)
            self.assertEqual(params.n_simulaciones, 1000)
        finally:
            import os
            os.remove(ruta)

    def test_null_rechazado(self):
        cfg = self._config_valida()
        cfg["alpha_local"] = None
        ruta = self._escribir(json.dumps(cfg))
        try:
            with self.assertRaises(ValueError):
                sim.cargar_config(ruta)
        finally:
            import os
            os.remove(ruta)

    def test_valor_no_numerico_rechazado(self):
        cfg = self._config_valida()
        cfg["mu"] = "abc"
        ruta = self._escribir(json.dumps(cfg))
        try:
            with self.assertRaises(ValueError):
                sim.cargar_config(ruta)
        finally:
            import os
            os.remove(ruta)

    def test_json_lista_rechazado(self):
        ruta = self._escribir("[1, 2, 3]")
        try:
            with self.assertRaises(ValueError):
                sim.cargar_config(ruta)
        finally:
            import os
            os.remove(ruta)


if __name__ == "__main__":
    unittest.main()
