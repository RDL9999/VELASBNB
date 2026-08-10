#!/usr/bin/env python3
"""
Kit de Testnet Farming — Orbinum Network (airdrop CONFIRMADO, TGE Q4 2026)
===========================================================================
Airdrop Season 1 "Genesis Community": 20,000,000 ORB (2% del supply).
Snapshot: 14 días antes de mainnet. Método: ORB Credits proporcionales.

Qué hace este script:
  1. Verifica conectividad al RPC testnet de Orbinum (chain 2700)
  2. Proporciona comandos listos para: agregar red, faucet, quests on-chain
  3. Genera un plan de farming diario con checklist
  4. Monitorea la cadena (bloque actual) y calcula tiempos

REQUISITOS:
  - Python 3.8+
  - Una wallet tipo EVM (MetaMask/Rabby/Substrate) con la red Orbinum agregada
  - Fondos de testnet del faucet (gratis)
  - Discord, Telegram y X vinculados en el dashboard (bonus 20 créditos)

USO:
  python3 orbinum_farm_kit.py --check      # verifica red + genera checklist
  python3 orbinum_farm_kit.py --watch 60   # monitoriza cadena cada 60s

ADVERTENCIA DE SEGURIDAD:
  - NUNCA compartas tu seed phrase. Ningún airdrop legítimo la pide.
  - Solo usa el faucet oficial y el dashboard oficial (vía airdrops.io/dashboard).
"""

import argparse
import json
import sys
import time
import urllib.request

RPC = "https://rpc-1.testnet.orbinum.io"
CHAIN_ID = 2700
DEFAULT_MONITOR_INTERVAL = 60


def rpc_call(method: str, params=None) -> dict:
    body = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params or [],
    }).encode()
    req = urllib.request.Request(
        RPC,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "orbinum-farm-kit/1.0"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def check_network():
    print("=" * 60)
    print(" ORBINUM TESTNET FARM KIT — verificacion de red")
    print("=" * 60)
    try:
        cid = rpc_call("eth_chainId")
        cid_int = int(cid["result"], 16)
        print(f"[OK] Chain ID: {cid_int}" + (" (esperado 2700)" if cid_int == CHAIN_ID else " *** MISMATCH ***"))

        block = rpc_call("eth_blockNumber")
        block_int = int(block["result"], 16)
        print(f"[OK] Bloque actual: {block_int}")

        gas = rpc_call("eth_gasPrice")
        print(f"[OK] Gas price: {int(gas['result'], 16)}")

        clients = rpc_call("web3_clientVersion")
        print(f"[OK] Cliente: {clients.get('result', 'n/a')}")
        print("-> Red testnet ACTIVA y accesible desde este entorno.")
        return block_int
    except Exception as e:
        print(f"[ERROR] No se pudo conectar al RPC: {e}")
        return None


def print_daily_plan():
    print()
    print("=" * 60)
    print(" PLAN DE FARMING DIARIO (repeatable quests = mayor score)")
    print("=" * 60)
    plan = [
        ("1. Sign-up", "Conecta wallet en el dashboard oficial y vincula Discord, Telegram y X (bonus 20 creditos)."),
        ("2. Add network", "Agrega Orbinum Testnet: ChainID 2700, RPC https://rpc-1.testnet.orbinum.io"),
        ("3. Faucet", "Reclama testnet tokens en el faucet oficial (gratis, cubre gas)."),
        ("4. SHIELD", "Mueve testnet assets al shielded pool (repetible diariamente)."),
        ("5. PRIVATE TRANSFER", "Envia una transferencia blindada usando disclosure key (repetible)."),
        ("6. UNSHIELD", "Saca assets del shielded pool (repetible)."),
        ("7. SELECTIVE DISCLOSURE", "Revela detalles de una transaccion usando disclosure key (repetible)."),
        ("8. Weekly streak", "Mantiene la racha ISO semanal: multiplicador hasta 1.5x en quest rewards."),
        ("9. Referidos", "Cada referido verificado = 10 creditos + bonus en hitos."),
        ("10. Off-chain", "Follows, shares, quizzes y submissions del dashboard (apilan creditos)."),
    ]
    for title, desc in plan:
        print(f"  {title}")
        print(f"      -> {desc}")
    print()
    print("  CLAVE: haz las 4 quests on-chain TODOS los dias.")
    print("  Snapshot = 14 dias ANTES de mainnet; actividad posterior no cuenta.")


def watch_loop(interval: int):
    print(f"Monitorizando {RPC} cada {interval}s. Ctrl+C para salir.")
    while True:
        try:
            block = rpc_call("eth_blockNumber")
            print(f"[{time.strftime('%H:%M:%S')}] Bloque: {int(block['result'], 16)}")
        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] Error: {e}")
        time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description="Orbinum Testnet Farming Kit")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="Verifica la red y muestra el plan")
    group.add_argument("--watch", type=int, nargs="?", const=DEFAULT_MONITOR_INTERVAL,
                       metavar="SEG", help="Monitoriza la cadena cada N segundos")
    args = parser.parse_args()

    if args.check:
        check_network()
        print_daily_plan()
        print("=" * 60)
        print(" RECOMENDACION DE SEGURIDAD: verifica siempre la URL del dashboard")
        print(" en los canales oficiales del proyecto antes de conectar tu wallet.")
    elif args.watch:
        watch_loop(args.watch)


if __name__ == "__main__":
    sys.exit(main())
