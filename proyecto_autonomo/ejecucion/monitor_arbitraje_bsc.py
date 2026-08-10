#!/usr/bin/env python3
"""
MONITOR DE ARBITRAJE BSC — detección de oportunidades reales en tiempo real.
=========================================================
Con gas a ~$0.02/tx, una oportunidad de arbitraje es rentable si:
  spread_cross_dex > fees_swap1 + fees_swap2 + slippage + gas

Reglas de filtrado para evitar honeypots/pools falsos:
  - Liquidez del pool > $50k (valorado vía WBNB a ~$600)
  - Spread cross-DEX > 0.8% (margen sobre fees de ~0.5%)
  - El par debe existir en >=2 DEXs reales

USO:
  python3 monitor_arbitraje_bsc.py            # un escaneo
  python3 monitor_arbitraje_bsc.py --loop 60  # escaneo cada 60s (bucle)

Si se detecta una oportunidad, el script imprime la ruta exacta de swaps
y el beneficio estimado; el operador decide ejecutar.
"""
import argparse
import json
import time
import urllib.request

RPC = "https://bsc-dataseed.bnbchain.org"

WBNB = "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"
USDT = "0x55d398326f99059fF775485246999027B3197955"
USDC = "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d"
CAKE = "0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82"
BUSD = "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56"

DEXES = {
    "PCS": {"factory": "0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73", "fee": 0.0025},
    "Biswap": {"factory": "0x858E3312ed3A876947EA49d572A7C42DE08af7EE", "fee": 0.001},
    "SquadSwap": {"factory": "0xd8eE964c577D607D6426FE6b4bC0114557E0AE99", "fee": 0.0025},
    "Mdex": {"factory": "0x3CD1C46068dAEa5Ebb0d3f55F6915B10648062B8", "fee": 0.003},
}

TOKENS = {
    "USDT": USDT,
    "USDC": USDC,
    "CAKE": CAKE,
}

MIN_LIQ_BNB = 80  # ~$50k
MIN_SPREAD = 0.008  # 0.8%


def rpc(method, params):
    body = json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": 1}).encode()
    req = urllib.request.Request(RPC, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def pair_for(factory, a, b):
    t0, t1 = sorted([a, b], key=lambda x: int(x, 16))
    data = "0xe6a43905" + "0" * 24 + t0[2:] + "0" * 24 + t1[2:]
    res = rpc("eth_call", [{"to": factory, "data": data}, "latest"])
    out = res.get("result")
    if not out or out == "0x" or out[-40:] == "0" * 40:
        return None
    return "0x" + out[-40:]


def get_price_and_liq(pair, tok, base):
    """Devuelve (precio del token en WBNB, liquidez en WBNB aprox)."""
    res = rpc("eth_call", [{"to": pair, "data": "0x0902f1ac"}, "latest"])["result"]
    r0 = int(res[2:66], 16) / 1e18
    r1 = int(res[66:130], 16) / 1e18
    if r0 == 0 or r1 == 0:
        return None, 0
    t0 = rpc("eth_call", [{"to": pair, "data": "0x0dfe1681"}, "latest"])["result"][-40:]
    tok0_is_tok = t0 == tok[2:].lower()
    if tok0_is_tok:
        price = r1 / r0  # WBNB per token
        liq_bnb = r1
    else:
        price = r0 / r1
        liq_bnb = r0
    return price, liq_bnb


def scan_once():
    print("=" * 66)
    print("ESCÁNER DE ARBITRAJE BSC  %s" % time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()))
    print("=" * 66)
    found = False
    for tok_name, tok in TOKENS.items():
        prices = {}
        for dex_name, cfg in DEXES.items():
            try:
                pair = pair_for(cfg["factory"], tok, WBNB)
                if not pair:
                    continue
                price, liq = get_price_and_liq(pair, tok, WBNB)
                if price and liq > MIN_LIQ_BNB:
                    prices[dex_name] = (price, liq)
            except Exception:
                continue
        if len(prices) < 2:
            continue
        vals = [v[0] for v in prices.values()]
        mx, mn = max(vals), min(vals)
        spread = (mx - mn) / mn
        if spread > MIN_SPREAD:
            found = True
            best = [k for k, v in prices.items() if v[0] == mx][0]
            worst = [k for k, v in prices.items() if v[0] == mn][0]
            liq_min = min(v[1] for v in prices.values())
            est_profit = 16 * (spread - 0.005)  # con $16 de capital
            print(f"  OPPORTUNITY: {tok_name}")
            print(f"    Comprar en {worst} ({mn:.6f} WBNB/tok), vender en {best} ({mx:.6f})")
            print(f"    Spread bruto: {spread*100:.2f}% | Liq min: {liq_min:.0f} WBNB")
            print(f"    Beneficio estimado con $16: ${est_profit:.2f}")
    if not found:
        print("  Sin oportunidades rentables ahora (spreads < 0.8% en pares líquidos).")
    print()
    return found


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--loop", type=int, default=0, help="escaneo continuo cada N segundos")
    args = p.parse_args()
    if args.loop:
        while True:
            try:
                scan_once()
            except Exception as e:
                print("Error:", e)
            time.sleep(args.loop)
    else:
        scan_once()


if __name__ == "__main__":
    main()
