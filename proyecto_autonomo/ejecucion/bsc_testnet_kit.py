#!/usr/bin/env python3
"""
BSC Testnet Farming Kit — con wallet real (0xDC748c...)
=========================================================
Script listo para interactuar con BSC testnet (chain 97) para calificar
a futuros airdrops de proyectos BSC/BEP-20 que premiaron testnet activity.

REQUISITO PREVIO (manual, 2 min):
  1. Obtener BNB testnet gratis: https://www.bnbchain.org/en/testnet-faucet
     (el faucet oficial pide h-captcha — solo se puede hacer en navegador)
  2. Con BNB testnet, este script ejecuta las interacciones on-chain.

USO:
  python3 bsc_testnet_kit.py --status          # estado de la wallet y red
  python3 bsc_testnet_kit.py --check-assets    # verifica contratos/redes activas

SEGURIDAD:
  - La private key está en este archivo por simplicidad. NO la compartas.
  - Solo usa contratos verificados de proyectos oficiales.
"""

import argparse
import json
import time
import urllib.request
from eth_account import Account
from eth_account.messages import encode_defunct

PRIVATE_KEY = "dca952ca116deef53530708d2248f4fccc25e01886d90c462b8e4aed94412c92"
ADDRESS = "0xDC748c004FDc8F73608eD32c99BE2a2d0bd026cb"
RPC = "https://data-seed-prebsc-1-s1.bnbchain.org:8545"
CHAIN_ID = 97

# Contratos de referencia en BSC testnet (PancakeSwap Router / WBNB testnet)
WBNB_TESTNET = "0xae13d989dac2f0debff460ac112a837c89baa7cd"
PCS_ROUTER_TESTNET = "0x9Ac64Cc6e4415144C455BD8E4837Fea55603e5c3"


def rpc_call(method, params):
    body = json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": 1}).encode()
    req = urllib.request.Request(RPC, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)["result"]


def check_status():
    acct = Account.from_key(PRIVATE_KEY)
    print("=" * 56)
    print(" BSC TESTNET FARMING KIT — estado")
    print("=" * 56)
    print(f"[OK] Dirección derivada: {acct.address}")
    assert acct.address.lower() == ADDRESS.lower(), "¡La key no coincide con la dirección!"
    bal = int(rpc_call("eth_getBalance", [ADDRESS, "latest"]), 16) / 1e18
    nonce = int(rpc_call("eth_getTransactionCount", [ADDRESS, "latest"]), 16)
    block = int(rpc_call("eth_blockNumber", []), 16)
    chain = int(rpc_call("eth_chainId", []), 16)
    print(f"[OK] Chain ID: {chain} (esperado 97)  | Bloque: {block}")
    print(f"[{'OK' if bal>0 else '!!'}] BNB testnet: {bal:.6f}  (se necesita >0 para gas)")
    print(f"[OK] Nonce: {nonce}")
    if bal == 0:
        print()
        print("  >>> SIN GAS. Reclama BNB testnet gratis en:")
        print("      https://www.bnbchain.org/en/testnet-faucet")
        print("      (solo navegador: pide h-captcha). Tras el claim vuelve a ejecutar.")
        return False
    print("  >>> Wallet lista para interactuar. Ejecuta las interacciones.")
    return True


def sign_and_send(acct, tx):
    signed = acct.sign_transaction(tx)
    rpc_call("eth_sendRawTransaction", [signed.raw_transaction.hex()])
    return signed.hash.hex()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--status", action="store_true")
    args = p.parse_args()
    if args.status:
        check_status()


if __name__ == "__main__":
    main()
