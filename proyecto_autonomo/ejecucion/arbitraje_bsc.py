#!/usr/bin/env python3
"""
Arbitraje BSC — escáner de precios entre DEXs.
Usa getReserves de pares USDT/WBNB y CAKE/WBNB en los DEX principales.
Reporta spreads que superen fees (PCS V2: 0.25%, otros: 0.25-0.3%).
"""
import json
import urllib.request
import sys

RPC = "https://bsc-dataseed.bnbchain.org"

WBNB = "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"
USDT = "0x55d398326f99059fF775485246999027B3197955"
USDC = "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d"
CAKE = "0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82"

DEXES = {
    "PancakeV2": {
        "router": "0x10ED43C718714eb63d5aA57B78B54704E256024E",
        "fee": 0.0025,
    },
    "Biswap": {
        "router": "0x3a6d8cA21D1CF76F653A67577FA0D274E50Dd858",
        "fee": 0.001,  # 0.1% base, a veces 0.2%
    },
    "ApeSwap": {
        "router": "0xcF0feBd3f17CEf5b47b0cD257aCF6025c5BFf3b7",
        "fee": 0.0025,
    },
    "BabySwap": {
        "router": "0x325E343f1dE602396E256B67eFd1F61C3A6B38Bd",
        "fee": 0.0025,
    },
}


def rpc(method, params):
    body = json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": 1}).encode()
    req = urllib.request.Request(RPC, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def get_reserves(pair):
    data = "0x0902f1ac"
    res = rpc("eth_call", [{"to": pair, "data": data}, "latest"])
    out = res.get("result")
    if not out or out == "0x":
        return None
    r0 = int(out[2:66], 16)
    r1 = int(out[66:130], 16)
    return r0, r1


# Addresses de pares USDT/WBNB por DEX (verificadas en BscScan)
PAIRS = {
    "PancakeV2": "0x16b9a82891338f9bA80E2D6970FddA79D1eb0daE",
    "Biswap": "0x3aCa72530D7f2bc51d1Ee732aE2fdd1a3Ea2E1E2",
    "ApeSwap": "0x51E6D27FA57373d8d4C478231C80Cc335FbD8976",
    "BabySwap": "0x1514D7E5A7d2221d5b7c77eb51D8d99E8F6eAbAa",
}

# Par alternativo para confirmar dirección de cada DEX (pares por factory)
FACTORIES = {
    "PancakeV2": "0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73",
    "Biswap": "0x858E3312ed3A876947EA49d572A7C42DE08af7EE",
    "ApeSwap": "0x0841BD2B559b470B2424cFa6ebF2bAa4d84690b6",
    "BabySwap": "0x86407bEa2078ea5f5EB5b52A6382aCe37012f013",
}


def pair_for(factory, a, b):
    def sort(x, y):
        return (x, y) if int(x, 16) < int(y, 16) else (y, x)

    t0, t1 = sort(a, b)
    data = "0xe6a43905" + "0" * 24 + t0[2:] + "0" * 24 + t1[2:]
    res = rpc("eth_call", [{"to": factory, "data": data}, "latest"])
    out = res.get("result")
    if not out or out == "0x":
        return None
    return "0x" + out[-40:]


def price_usdt_per_wbnb(r0, r1, tok0):
    # returns USDT per WBNB
    if tok0.lower() == USDT.lower():
        return r1 / r0  # r0=USDT, r1=WBNB -> WBNB/USDT = r1/r0? careful
    else:
        return r0 / r1


def main():
    prices = {}
    print("=" * 60)
    print("ESCÁNER DE ARBITRAJE BSC — USDT/WBNB por DEX")
    print("=" * 60)
    for name, factory in FACTORIES.items():
        try:
            pair = pair_for(factory, USDT, WBNB)
            if not pair or pair == "0x" + "0" * 40:
                print(f"{name}: pair no encontrado (posible direccion de fábrica distinta)")
                continue
            res = get_reserves(pair)
            if not res:
                print(f"{name}: sin reserves")
                continue
            r0, r1 = res
            # decidir token0
            data = "0x0dfe1681"
            tok0res = rpc("eth_call", [{"to": pair, "data": data}, "latest"])
            tok0 = "0x" + tok0res.get("result")[-40:]
            # precio: cantidad de USDT por 1 WBNB
            if tok0.lower() == WBNB.lower():
                price = r1 / r0  # r0=WBNB, r1=USDT
            else:
                price = r0 / r1  # r0=USDT, r1=WBNB
            prices[name] = price
            print(f"{name:12s} pair={pair}  precio USDT/WBNB = {price:,.2f}")
        except Exception as e:
            print(f"{name}: ERROR {e}")

    print()
    if len(prices) >= 2:
        best = max(prices, key=prices.get)
        worst = min(prices, key=prices.get)
        spread = (prices[best] - prices[worst]) / prices[worst]
        print(f"Máximo: {best} ({prices[best]:,.2f}) vs Mínimo: {worst} ({prices[worst]:,.2f})")
        print(f"Spread bruto: {spread*100:.3f}%")
        print(f"Fees combinados (swap compra+vend.): ~0.5%")
        profitable = spread > 0.006
        print(f"PROFITABLE tras fees: {'SÍ ✓' if profitable else 'NO ✗'}")
        if profitable:
            print(">>> EJECUTAR: comprar WBNB barato, vender caro, swap directo WBNB->USDT")
    else:
        print("No hay suficientes precios para comparar.")


if __name__ == "__main__":
    main()
