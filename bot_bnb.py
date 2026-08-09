]633;E;echo "========== main.py ==========";a0d5697e-38d6-400a-a725-07f68d36d9fc]633;C========== main.py ==========
import hmac
import html
import json
import math
import os
import statistics
import sys
import threading
import time
import traceback
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from typing import Any, Dict, List, Optional, Tuple

import requests
from flask import Flask, jsonify, request
from web3 import Web3
from web3.exceptions import TransactionNotFound

from datos_mercado import obtener_precio_con_fallback, obtener_velas_multi_temporalidad
from db import (
    cargar_estado,
    guardar_estado,
    obtener_metricas,
    registrar_calidad_ejecucion,
    registrar_trade,
)
from estrategia import (
    DetectorSuelosReales,
    DetectorTechosReales,
    esta_en_bear_market,
    hay_crash_reciente,
    tendencia_corto_plazo_bajista,
)
from indicadores import calcular_atr, calcular_bollinger, calcular_ema, calcular_rsi

# ============================================================
# 🆕 ANTI-EUFORIA - CONFIGURACIÓN
# ============================================================
CUARENTENA_VELAS = 777
ATH_DISTANCIA_MAX = 15.0
SUB7D_VETO = 11.1  # 🏆 ÓPTIMO
SUB7D_REFUERZO = 18.0
VSEMA50_REFUERZO = 10.0
VELAS_7D = 42

# Variable global para cuarentena (se carga desde Supabase al iniciar)
cuarentena_hasta = 0.0

# 🆕 Variables para espera post-venta y doble verificación
ESPERA_POST_VENTA = 27  # Velas de espera tras cada venta
VELAS_VERIFICACION = 9  # Velas para doble verificación
ultima_venta_ts: float = 0.0  # Timestamp de la última venta
senal_compra_pendiente = False  # ¿Hay señal pendiente de verificar?
senal_compra_ts: float = 0.0  # Timestamp de la primera señal
suelo_pendiente = 0.0  # Suelo detectado en primera señal
razon_pendiente = ""  # Razón de la primera señal

# 🆕 Variables para health check
ultimo_ciclo_ts: float = 0.0
ultimo_ciclo_error: Optional[str] = None
ciclos_ejecutados: int = 0

# 🆕 Heartbeat diario
_ultimo_heartbeat: float = 0.0

# 🆕 Bear Market prolongado
_bear_alertas: int = 0

def veto_anti_euforia(closes: List[float]) -> Tuple[bool, str]:
    """Retorna (True, motivo) si la compra debe vetarse por euforia."""
    if len(closes) < VELAS_7D + 1:
        return False, ""
    precio = closes[-1]
    ath = max(closes)
    if ath <= 0:
        return False, ""
    distancia_ath = (ath - precio) / ath * 100.0
    if distancia_ath > ATH_DISTANCIA_MAX:
        return False, ""
    precio_hace_7d = closes[-(VELAS_7D + 1)]
    sub7d = (precio - precio_hace_7d) / precio_hace_7d * 100.0 if precio_hace_7d > 0 else 0.0
    ema50 = calcular_ema(closes, 50)
    vs_ema50 = 0.0
    if ema50[-1] is not None and ema50[-1] > 0:
        vs_ema50 = (precio - ema50[-1]) / ema50[-1] * 100.0
    if sub7d >= SUB7D_VETO:
        return True, f"Dist ATH {distancia_ath:.1f}% | Sub7d +{sub7d:.1f}% (>= {SUB7D_VETO:.0f}%) | vsEMA50 +{vs_ema50:.1f}%"
    if sub7d >= SUB7D_REFUERZO and vs_ema50 >= VSEMA50_REFUERZO:
        return True, f"Dist ATH {distancia_ath:.1f}% | Sub7d +{sub7d:.1f}% + vsEMA50 +{vs_ema50:.1f}%"
    return False, ""

# ============================================================
# 🆕 PERSISTENCIA DE CUARENTENA EN SUPABASE
# ============================================================

def _guardar_cuarentena() -> None:
    with STATE_LOCK:
        estado["cuarentena_hasta"] = cuarentena_hasta
        persistir_estado_bajo_lock()

def _cargar_cuarentena() -> None:
    global cuarentena_hasta
    cuarentena_hasta = float(estado.get("cuarentena_hasta", 0.0))
    if cuarentena_hasta > 0:
        ahora = time.time()
        if ahora < cuarentena_hasta:
            restante = cuarentena_hasta - ahora
            print(f"{Colores.AMARILLO}[CUARENTENA]{Colores.RESET} ❄️ Cargada de DB. Restan {restante/3600:.1f} horas")
        else:
            print(f"{Colores.VERDE}[CUARENTENA]{Colores.RESET} ✅ Cuarentena expirada, liberando bot")
            cuarentena_hasta = 0.0
            _guardar_cuarentena()

# ============================================================
# SISTEMA DE LOGGING Y COLORES
# ============================================================

class Colores:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    VERDE = "\033[92m"
    AMARILLO = "\033[93m"
    ROJO = "\033[91m"
    AZUL = "\033[94m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"
    BLANCO = "\033[97m"
    FONDO_VERDE = "\033[42m"
    FONDO_ROJO = "\033[41m"

def _timestamp_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

def _esc(texto: Any) -> str:
    return html.escape(str(texto), quote=False)

def _formatear_bnb(cantidad: float, decimales: int = 8) -> str:
    return f"{cantidad:.{decimales}f}"

def _formatear_usd(cantidad: float) -> str:
    if abs(cantidad) >= 1000:
        return f"${cantidad:,.2f}"
    return f"${cantidad:.2f}"

def _formatear_pct(valor: float) -> str:
    if valor > 0:
        return f"+{valor:.2f}%"
    elif valor < 0:
        return f"{valor:.2f}%"
    return f"{valor:.2f}%"

def _color_pnl(pnl: float) -> str:
    if pnl > 0:
        return f"{Colores.VERDE}+{pnl:.2f}%{Colores.RESET}"
    elif pnl < 0:
        return f"{Colores.ROJO}{pnl:.2f}%{Colores.RESET}"
    return f"{pnl:.2f}%"

# ============================================================
# NOTIFICACIONES
# ============================================================

DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK", "").strip()

def notificar_discord(mensaje: str) -> None:
    if not DISCORD_WEBHOOK:
        return
    try:
        requests.post(DISCORD_WEBHOOK, json={"content": mensaje}, timeout=5)
    except Exception:
        pass

def notificar_telegram(mensaje: str) -> None:
    token = TELEGRAM_TOKEN
    chat = TELEGRAM_CHAT
    if not token or not chat:
        return
    try:
        respuesta = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": mensaje, "parse_mode": "HTML"},
            timeout=10,
        )
        if respuesta.status_code != 200:
            print(f"[AVISO] Telegram: HTTP {respuesta.status_code}")
    except Exception as exc:
        print(f"[AVISO] Telegram: {exc}")

def notificar(mensaje: str) -> None:
    print(f"\n{Colores.BOLD}{Colores.CYAN}[NOTIFICACION]{Colores.RESET} {mensaje}")
    notificar_telegram(mensaje)

def notificar_compra(cantidad_bnb: float, precio: float, usdt_gastado: float, tx_hash: str = "", motivo: str = "") -> None:
    msg = (
        f"🟢 <b>COMPRA BNB - HUMANO-BOT</b> 🟢\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"💰 Cantidad: <b>{cantidad_bnb:.8f} BNB</b>\n"
        f"💵 Precio: <b>${precio:,.2f}</b>\n"
        f"💲 Total: <b>${usdt_gastado:,.2f}</b>\n"
        f"📝 Motivo: {_esc(motivo)}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🕐 {_timestamp_utc()}"
    )
    if tx_hash:
        msg += f"\n🔗 <a href='https://bscscan.com/tx/{tx_hash}'>Ver en BSCScan</a>"
    notificar(msg)
    notificar_discord(msg)

def notificar_venta(cantidad_bnb: float, precio: float, usdt_recibido: float, pnl: float, motivo: str = "", tx_hash: str = "") -> None:
    emoji = "🟢" if pnl >= 0 else "🔴"
    pnl_str = f"+{pnl:.2f}%" if pnl >= 0 else f"{pnl:.2f}%"
    msg = (
        f"{emoji} <b>VENTA BNB - HUMANO-BOT</b> {emoji}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"💰 Cantidad: <b>{cantidad_bnb:.8f} BNB</b>\n"
        f"💵 Precio: <b>${precio:,.2f}</b>\n"
        f"💲 USDT: <b>${usdt_recibido:,.2f}</b>\n"
        f"📊 PnL: <b>{pnl_str}</b>\n"
        f"📝 Motivo: {_esc(motivo)}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🕐 {_timestamp_utc()}"
    )
    if tx_hash:
        msg += f"\n🔗 <a href='https://bscscan.com/tx/{tx_hash}'>Ver en BSCScan</a>"
    notificar(msg)
    notificar_discord(msg)

def notificar_inicio() -> None:
    msg = (
        f"🤖 <b>BNB HUMANO-BOT v2.0</b> 🤖\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🧠 Estrategia: Suelos reales + Techos reales\n"
        f"📊 RSI {RSI_MAX_COMPRA} | Toma +{TOMA_PCT}%/{CAIDA_PCT}%\n"
        f"🛡️ Anti-Euforia: {CUARENTENA_VELAS}v cuarentena | Sub7d ≥{SUB7D_VETO}%\n"
        f"🕐 Inicio: {_timestamp_utc()}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"✅ Bot iniciado correctamente"
    )
    notificar(msg)

def notificar_error(mensaje: str) -> None:
    msg = (
        f"⚠️ <b>ERROR EN BOT</b> ⚠️\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📝 {_esc(mensaje)}\n"
        f"🕐 {_timestamp_utc()}"
    )
    notificar(msg)
    notificar_discord(msg)

def notificar_veto_euforia(precio: float, motivo: str, fin_cuarentena: str) -> None:
    msg = (
        f"🚫 <b>COMPRA BLOQUEADA - ANTI-EUFORIA</b> 🚫\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"💵 Precio: <b>${precio:,.2f}</b>\n"
        f"📝 Motivo: {_esc(motivo)}\n"
        f"❄️ Bot congelado {CUARENTENA_VELAS} velas hasta {fin_cuarentena}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🕐 {_timestamp_utc()}"
    )
    notificar(msg)
    notificar_discord(msg)

def notificar_gas_bajo(saldo_bnb: float, nivel: str) -> None:
    if nivel == "critico":
        msg = (
            f"🚨 <b>ALERTA CRÍTICA - SIN GAS</b> 🚨\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"⛽ Saldo BNB: <b>{saldo_bnb:.6f} BNB</b>\n"
            f"⚠️ Mínimo requerido: <b>{BNB_MINIMO_GAS:.6f} BNB</b>\n"
            f"❌ El bot NO PUEDE OPERAR\n"
            f"💡 Transfiere BNB a la wallet inmediatamente\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"🕐 {_timestamp_utc()}"
        )
    else:
        tx_posibles = int(saldo_bnb / BNB_MINIMO_GAS)
        msg = (
            f"⚠️ <b>ALERTA - GAS BAJO</b> ⚠️\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"⛽ Saldo BNB: <b>{saldo_bnb:.6f} BNB</b>\n"
            f"📉 Mínimo recomendado: <b>{BNB_MINIMO_GAS * 2:.6f} BNB</b>\n"
            f"⚠️ Solo alcanza para ~{tx_posibles} transacción(es)\n"
            f"💡 Considera recargar pronto\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"🕐 {_timestamp_utc()}"
        )
    notificar(msg)

def verificar_y_alertar_gas() -> None:
    try:
        saldo_bnb = balance_bnb_wei() / UNIDAD_BNB
        minimo_recomendado = BNB_MINIMO_GAS * 2
        if saldo_bnb < BNB_MINIMO_GAS:
            notificar_gas_bajo(saldo_bnb, "critico")
            print(f"\n{Colores.ROJO}{Colores.BOLD}[GAS CRÍTICO]{Colores.RESET} Saldo: {saldo_bnb:.6f} BNB - ¡SIN GAS SUFICIENTE!")
        elif saldo_bnb < minimo_recomendado:
            notificar_gas_bajo(saldo_bnb, "bajo")
            print(f"\n{Colores.AMARILLO}{Colores.BOLD}[GAS BAJO]{Colores.RESET} Saldo: {saldo_bnb:.6f} BNB - Recomendado: {minimo_recomendado:.6f} BNB")
    except Exception as exc:
        print(f"{Colores.ROJO}[ERROR]{Colores.RESET} Error al verificar gas: {exc}")

def notificar_heartbeat() -> None:
    global _ultimo_heartbeat
    ahora = time.time()
    if ahora - _ultimo_heartbeat < 86400:
        return
    _ultimo_heartbeat = ahora
    with STATE_LOCK:
        en_pos = estado.get("en_posicion", False)
    msg = (
        f"💓 <b>HUMANO-BOT - REPORTE DIARIO</b> 💓\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"✅ Bot operativo\n"
        f"📊 Posición: {'🟢 ABIERTA' if en_pos else '⚪ Sin posición'}\n"
        f"🔄 Ciclos ejecutados: {ciclos_ejecutados}\n"
        f"🛡️ Cuarentena: {'❄️ Activa' if cuarentena_hasta > time.time() else '✅ Libre'}\n"
        f"🕐 {_timestamp_utc()}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🏥 Estado: Healthy"
    )
    notificar(msg)

def verificar_bear_prolongado(bear: bool) -> None:
    global _bear_alertas
    if bear:
        _bear_alertas += 1
        if _bear_alertas % 112 == 0:
            dias = _bear_alertas * 900 / 86400
            msg = (
                f"🐻 <b>BEAR MARKET PROLONGADO</b> 🐻\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"⏳ Días sin operar: ~{dias:.0f}\n"
                f"📊 El bot sigue esperando condiciones\n"
                f"💡 Todo funciona correctamente\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"🕐 {_timestamp_utc()}"
            )
            notificar(msg)
    else:
        _bear_alertas = 0

# ============================================================
# CONFIGURACIÓN
# ============================================================

try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

def env_bool(nombre: str, predeterminado: bool) -> bool:
    valor = os.getenv(nombre)
    if valor is None:
        return predeterminado
    return valor.strip().lower() in {"1", "true", "yes", "si", "sí", "on"}

def env_float(nombre: str, predeterminado: float) -> float:
    try:
        return float(os.getenv(nombre, str(predeterminado)))
    except (TypeError, ValueError):
        return predeterminado

def env_int(nombre: str, predeterminado: int) -> int:
    try:
        return int(os.getenv(nombre, str(predeterminado)))
    except (TypeError, ValueError):
        return predeterminado

# ============================================================
# PARÁMETROS DE LA ESTRATEGIA HUMANO-BOT
# ============================================================
RSI_MAX_COMPRA = env_float("RSI_MAX_COMPRA", 77.0)
TOMA_PCT = env_float("TOMA_PCT", 17.6)
CAIDA_PCT = env_float("CAIDA_PCT", 4.4)

MAX_DRAWDOWN = env_float("MAX_DRAWDOWN", 0.90)
MIN_BNB_VENTA = env_float("MIN_BNB_VENTA", 0.0001)
USDT_MINIMO = env_float("USDT_MINIMO", 9.0)
BNB_MINIMO_GAS = env_float("BNB_MINIMO_GAS", 0.002)

SLIPPAGE_BASE = env_float("SLIPPAGE_BASE", 0.005)
SLIPPAGE_MAX = env_float("SLIPPAGE_MAX", 0.015)
MAX_DESVIACION_EJECUCION = env_float("MAX_DESVIACION_EJECUCION", 0.03)

GAS_MIN_GWEI = max(env_float("GAS_MIN_GWEI", 1.0), 0.1)
GAS_MAX_GWEI = max(env_float("GAS_MAX_GWEI", 15.0), GAS_MIN_GWEI)
GAS_BUMP_FACTOR = max(env_float("GAS_BUMP_FACTOR", 1.20), 1.10)
GAS_WAIT_BEFORE_BUMP = max(env_int("GAS_WAIT_BEFORE_BUMP", 60), 15)
TX_TIMEOUT = max(env_int("TX_TIMEOUT", 240), GAS_WAIT_BEFORE_BUMP + 30)
TX_MAX_BUMPS = max(env_int("TX_MAX_BUMPS", 2), 0)

ESCANEO = max(env_int("ESCANEO", 900), 30)
CANDLE_INTERVAL = max(env_int("CANDLE_INTERVAL", 240), 1)

DRY_RUN = env_bool("DRY_RUN", False)
REQUIRE_DB = env_bool("REQUIRE_DB", True)
CHAIN_ID_ESPERADA = env_int("CHAIN_ID", 56)
RPC_MAX_REINTENTOS = max(env_int("RPC_MAX_REINTENTOS", 5), 1)
STATUS_TOKEN = os.getenv("STATUS_TOKEN", "").strip()
MAX_GASTO_TOTAL_USDT = env_float("MAX_GASTO_TOTAL_USDT", 0.0)

# ============================================================
# VARIABLES DE ENTORNO OBLIGATORIAS
# ============================================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT_ID", "").strip()
PRIVATE_KEY = os.getenv("PRIVATE_KEY", "").strip()
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip()
BSC_RPC = os.getenv("BSC_RPC", "https://bsc-dataseed.binance.org/").strip()

RPCS = list(dict.fromkeys(
    rpc for rpc in [
        BSC_RPC,
        "https://bsc-dataseed1.defibit.io/",
        "https://bsc-dataseed1.ninicoin.io/",
        "https://rpc.ankr.com/bsc",
    ] if rpc
))

if not PRIVATE_KEY:
    raise RuntimeError("Falta PRIVATE_KEY")
if REQUIRE_DB and (not SUPABASE_URL or not SUPABASE_KEY):
    raise RuntimeError("Faltan SUPABASE_URL o SUPABASE_KEY")

ROUTER_ADDRESS = Web3.to_checksum_address("0x10ED43C718714eb63d5aA57B78B54704E256024E")
WBNB = Web3.to_checksum_address("0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c")
USDT = Web3.to_checksum_address("0x55d398326f99059fF775485246999027B3197955")

ERC20_ABI = json.loads("""[
      {"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"stateMutability":"view","type":"function"},
      {"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint8"}],"stateMutability":"view","type":"function"},
      {"inputs":[{"name":"_spender","type":"address"},{"name":"_value","type":"uint256"}],"name":"approve","outputs":[{"name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"},
      {"inputs":[{"name":"_owner","type":"address"},{"name":"_spender","type":"address"}],"name":"allowance","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"}
    ]""")

ROUTER_ABI = json.loads("""[
      {"inputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"}],"name":"getAmountsOut","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"view","type":"function"},
      {"inputs":[{"internalType":"uint256","name":"amountOutMin","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapExactETHForTokens","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"payable","type":"function"},
      {"inputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"uint256","name":"amountOutMin","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapExactTokensForETH","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"nonpayable","type":"function"}
    ]""")

STATE_LOCK = threading.RLock()
TX_LOCK = threading.Lock()

# ============================================================
# CONEXIÓN WEB3
# ============================================================

def _inyectar_poa_middleware(proveedor: "Web3") -> None:
    try:
        from web3.middleware import ExtraDataToPOAMiddleware
        proveedor.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        return
    except ImportError:
        pass
    try:
        from web3.middleware import geth_poa_middleware
        proveedor.middleware_onion.inject(geth_poa_middleware, layer=0)
        return
    except ImportError:
        print(f"{Colores.AMARILLO}[AVISO]{Colores.RESET} POA middleware no disponible")

def conectar_web3() -> Web3:
    ultimo_error: Optional[Exception] = None
    for intento in range(1, RPC_MAX_REINTENTOS + 1):
        for rpc in RPCS:
            try:
                proveedor = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 30}))
                _inyectar_poa_middleware(proveedor)
                if proveedor.is_connected():
                    print(f"{Colores.VERDE}[OK]{Colores.RESET} RPC: {rpc}")
                    return proveedor
            except Exception as exc:
                ultimo_error = exc
        time.sleep(min(2 ** intento, 30))
    raise RuntimeError(f"No se pudo conectar a BSC: {ultimo_error}")

w3 = conectar_web3()
chain_id_real = int(w3.eth.chain_id)
if chain_id_real != CHAIN_ID_ESPERADA:
    raise RuntimeError(f"Chain ID incorrecto: {chain_id_real}")

wallet = w3.eth.account.from_key(PRIVATE_KEY)
MI_DIRECCION = Web3.to_checksum_address(wallet.address)
usdt_contract = w3.eth.contract(address=USDT, abi=ERC20_ABI)
router = w3.eth.contract(address=ROUTER_ADDRESS, abi=ROUTER_ABI)

USDT_DECIMALS = int(usdt_contract.functions.decimals().call())
UNIDAD_USDT = 10 ** USDT_DECIMALS
UNIDAD_BNB = 10 ** 18
estado = cargar_estado()

# ============================================================
# FUNCIONES DE BLOCKCHAIN
# ============================================================

def persistir_estado_bajo_lock() -> None:
    if not guardar_estado(estado, require_remote=REQUIRE_DB):
        raise RuntimeError("No se pudo persistir el estado")

def truncar_unidades(cantidad: float, decimales: int) -> int:
    factor = Decimal(10) ** decimales
    return int((Decimal(str(cantidad)) * factor).to_integral_value(rounding=ROUND_DOWN))

def hash_texto(tx_hash: Any) -> str:
    texto = tx_hash.hex()
    return texto if texto.startswith("0x") else f"0x{texto}"

def balance_bnb_wei() -> int:
    return int(w3.eth.get_balance(MI_DIRECCION))

def balance_usdt_wei() -> int:
    return int(usdt_contract.functions.balanceOf(MI_DIRECCION).call())

def campos_gas() -> Dict[str, int]:
    bloque = w3.eth.get_block("latest")
    base_fee = bloque.get("baseFeePerGas")
    if base_fee is None:
        gas_price = int(w3.eth.gas_price)
        gas_price = min(max(gas_price, int(w3.to_wei(GAS_MIN_GWEI, "gwei"))), int(w3.to_wei(GAS_MAX_GWEI, "gwei")))
        return {"gasPrice": gas_price}
    prioridad = int(w3.to_wei(GAS_MIN_GWEI, "gwei"))
    max_fee = int(int(base_fee) * 1.25 + prioridad)
    max_fee = min(max_fee, int(w3.to_wei(GAS_MAX_GWEI, "gwei")))
    return {"type": 2, "maxPriorityFeePerGas": prioridad, "maxFeePerGas": max_fee}

def campos_tx(nonce: Optional[int] = None) -> Dict[str, Any]:
    return {
        "from": MI_DIRECCION,
        "nonce": int(nonce) if nonce is not None else int(w3.eth.get_transaction_count(MI_DIRECCION, "pending")),
        "chainId": chain_id_real,
        **campos_gas(),
    }

def aumentar_gas(tx: Dict[str, Any]) -> Dict[str, Any]:
    nueva = dict(tx)
    limite = int(w3.to_wei(GAS_MAX_GWEI, "gwei"))
    if "gasPrice" in nueva:
        nueva["gasPrice"] = min(limite, max(int(nueva["gasPrice"] * GAS_BUMP_FACTOR), nueva["gasPrice"] + 1))
    else:
        prioridad = min(limite, max(int(nueva["maxPriorityFeePerGas"] * GAS_BUMP_FACTOR), nueva["maxPriorityFeePerGas"] + 1))
        max_fee = min(limite, max(int(nueva["maxFeePerGas"] * GAS_BUMP_FACTOR), nueva["maxFeePerGas"] + 1, prioridad))
        nueva["maxPriorityFeePerGas"] = prioridad
        nueva["maxFeePerGas"] = max_fee
    return nueva

def estimar_gas(funcion: Any, tx_base: Dict[str, Any]) -> int:
    estimado = int(funcion.estimate_gas(tx_base))
    return max(21_000, int(estimado * 1.20))

def _guardar_hash_pending(tx_hash: str) -> None:
    with STATE_LOCK:
        pending = dict(estado.get("tx_pending") or {})
        if not pending:
            return
        hashes = list(pending.get("hashes") or [])
        if tx_hash not in hashes:
            hashes.append(tx_hash)
        pending["hash"] = tx_hash
        pending["hashes"] = hashes
        estado["tx_pending"] = pending
        persistir_estado_bajo_lock()

def _buscar_receipt(hashes: List[str]) -> Tuple[Optional[str], Optional[Any]]:
    for tx_hash in reversed(hashes):
        try:
            receipt = w3.eth.get_transaction_receipt(tx_hash)
            if receipt is not None:
                return tx_hash, receipt
        except TransactionNotFound:
            continue
        except Exception:
            continue
    return None, None

def enviar_y_confirmar_con_bump(transaccion: Dict[str, Any], registrar_hash: bool = False) -> Tuple[str, Any]:
    if DRY_RUN:
        return "0x" + "d" * 64, None
    nonce = int(transaccion["nonce"])
    tx_actual = dict(transaccion)
    hashes: List[str] = []
    ultimo_envio = 0.0
    bumps = 0
    inicio = time.monotonic()
    while time.monotonic() - inicio < TX_TIMEOUT:
        if not hashes or (time.monotonic() - ultimo_envio >= GAS_WAIT_BEFORE_BUMP and bumps < TX_MAX_BUMPS):
            if hashes:
                tx_actual = aumentar_gas(tx_actual)
                bumps += 1
            firmado = w3.eth.account.sign_transaction(tx_actual, PRIVATE_KEY)
            raw = getattr(firmado, "raw_transaction", None) or getattr(firmado, "rawTransaction", None)
            try:
                tx_hash = hash_texto(w3.eth.send_raw_transaction(raw))
                if tx_hash not in hashes:
                    hashes.append(tx_hash)
                if registrar_hash:
                    _guardar_hash_pending(tx_hash)
                print(f"{Colores.VERDE}[TX]{Colores.RESET} Enviada: {tx_hash[:10]}...{tx_hash[-8:]}")
            except Exception as exc:
                texto = str(exc).lower()
                if "already known" not in texto and "known transaction" not in texto:
                    raise
            ultimo_envio = time.monotonic()
        encontrado_hash, receipt = _buscar_receipt(hashes)
        if receipt is not None:
            if int(receipt.status) != 1:
                raise RuntimeError(f"Transacción revertida: {encontrado_hash}")
            print(f"{Colores.VERDE}[TX]{Colores.RESET} Confirmada: {encontrado_hash[:10]}...{encontrado_hash[-8:]}")
            return encontrado_hash or hashes[-1], receipt
        time.sleep(3)
    raise RuntimeError("Transacción sin confirmación")

def cotizar_usdt_a_bnb(usdt_wei: int) -> Tuple[int, float]:
    salida = router.functions.getAmountsOut(usdt_wei, [USDT, WBNB]).call()
    bnb_wei = int(salida[-1])
    return bnb_wei, (usdt_wei / UNIDAD_USDT) / (bnb_wei / UNIDAD_BNB)

def cotizar_bnb_a_usdt(bnb_wei: int) -> Tuple[int, float]:
    salida = router.functions.getAmountsOut(bnb_wei, [WBNB, USDT]).call()
    usdt_wei = int(salida[-1])
    return usdt_wei, (usdt_wei / UNIDAD_USDT) / (bnb_wei / UNIDAD_BNB)

def precio_dex_referencia() -> Optional[float]:
    try:
        return cotizar_bnb_a_usdt(UNIDAD_BNB)[1]
    except Exception:
        return None

def precio_valido(precio_dex: float, limite: float) -> bool:
    if precio_dex <= 0:
        return False
    referencia = obtener_precio_con_fallback("BNBUSD", "BNBUSDT")
    if referencia is None or referencia <= 0:
        return DRY_RUN
    desviacion = abs(precio_dex - referencia) / referencia
    return desviacion <= limite

def calcular_slippage_dinamico(valor_usd: float) -> float:
    extra = min(0.02, max(0.0, valor_usd) / 1_000_000.0)
    return min(SLIPPAGE_MAX, SLIPPAGE_BASE + extra)

def _calcular_twap(symbol: str = "BNBUSD", minutos: int = 3) -> Optional[float]:
    try:
        url = "https://api.kraken.com/0/public/OHLC"
        since = str(int(time.time() - (minutos + 2) * 60))
        resp = requests.get(url, params={"pair": symbol, "interval": 1, "since": since}, timeout=10)
        data = resp.json()
        if data.get("error"):
            return None
        key = next((k for k in data.get("result", {}) if k != "last"), None)
        if not key:
            return None
        ohlc = data["result"].get(key, [])
        closes = [float(c[4]) for c in ohlc if len(c) > 4 and float(c[4]) > 0]
        return statistics.mean(closes[-minutos:]) if len(closes) >= 2 else None
    except Exception:
        return None

def aprobar_usdt_si_necesario(cantidad_wei: int) -> None:
    allowance = int(usdt_contract.functions.allowance(MI_DIRECCION, ROUTER_ADDRESS).call())
    if allowance >= cantidad_wei or DRY_RUN:
        return
    funcion = usdt_contract.functions.approve(ROUTER_ADDRESS, cantidad_wei)
    tx_base = campos_tx()
    tx_base["gas"] = estimar_gas(funcion, tx_base)
    tx = funcion.build_transaction(tx_base)
    enviar_y_confirmar_con_bump(tx)

def _cerrar_estado() -> None:
    estado.update({
        "en_posicion": False, "precio_entrada": 0.0, "cantidad": 0.0,
        "precio_maximo": 0.0, "timestamp_entrada": None, "tx_hash_entrada": "",
        "ganancia_max_pct": 0.0, "velas_en_posicion": 0, "atr_inicial": 0.0,
        "suelo_compra": 0.0,
    })

def reconciliar_estado() -> None:
    with TX_LOCK:
        with STATE_LOCK:
            pending = dict(estado.get("tx_pending") or {})
        if not pending:
            return
        print(f"\n{Colores.BOLD}{Colores.AZUL}[RECONCILIACION]{Colores.RESET} Revisando transacciones pendientes...")
        hashes = [h for h in pending.get("hashes", [pending.get("hash")]) if isinstance(h, str) and h.startswith("0x")]
        tx_hash, receipt = _buscar_receipt(hashes)
        if receipt is None:
            print(f"{Colores.AZUL}[INFO]{Colores.RESET} Sin confirmación aún")
            return
        if int(receipt.status) != 1:
            with STATE_LOCK:
                estado["tx_pending"] = None
                persistir_estado_bajo_lock()
            return
        print(f"{Colores.VERDE}[OK]{Colores.RESET} TX reconciliada: {tx_hash[:10]}...{tx_hash[-8:]}")
        tipo = str(pending.get("tipo") or "")
        saldo_bnb = balance_bnb_wei() / UNIDAD_BNB
        with STATE_LOCK:
            if tipo == "COMPRA":
                saldo_antes = float(pending.get("saldo_bnb_antes", 0.0))
                cantidad = max(0.0, saldo_bnb - saldo_antes)
                if cantidad >= MIN_BNB_VENTA:
                    precio = float(pending.get("precio_estimado") or precio_dex_referencia() or 0.0)
                    estado.update({
                        "en_posicion": True, "cantidad": cantidad, "precio_entrada": precio,
                        "precio_maximo": precio, "timestamp_entrada": datetime.now(timezone.utc).isoformat(),
                        "ultima_operacion": "RECONCILIACION_COMPRA", "tx_hash_entrada": tx_hash or "",
                        "ganancia_max_pct": 0.0, "velas_en_posicion": 0,
                    })
            elif tipo == "VENTA":
                _cerrar_estado()
            estado["tx_pending"] = None
            persistir_estado_bajo_lock()

# ============================================================
# COMPRAR
# ============================================================

def comprar(cantidad_usdt: float, motivo: str = "", suelo: float = 0.0, rsi: float = 0.0, atr_inicial: float = 0.0) -> bool:
    with TX_LOCK:
        inicio = time.monotonic()
        try:
            with STATE_LOCK:
                if estado.get("en_posicion") or estado.get("tx_pending"):
                    return False
            saldo_usdt = balance_usdt_wei()
            cantidad_wei = min(truncar_unidades(cantidad_usdt, USDT_DECIMALS), saldo_usdt)
            cantidad_real = cantidad_wei / UNIDAD_USDT
            if cantidad_real < USDT_MINIMO:
                return False
            
            if MAX_GASTO_TOTAL_USDT > 0:
                gastado = float(estado.get("gasto_total_usdt", 0.0))
                if gastado + cantidad_real > MAX_GASTO_TOTAL_USDT:
                    return False
            
            esperado_wei, precio_dex = cotizar_usdt_a_bnb(cantidad_wei)
            if not DRY_RUN:
                twap = _calcular_twap()
                if twap and precio_dex and abs(precio_dex - twap) / twap > (MAX_DESVIACION_EJECUCION * 1.5):
                    return False
            if not precio_valido(precio_dex, MAX_DESVIACION_EJECUCION):
                return False
            
            slippage = calcular_slippage_dinamico(cantidad_real)
            minimo = int(esperado_wei * (1.0 - slippage))
            precio_esperado = cantidad_real / (esperado_wei / UNIDAD_BNB)
            
            if DRY_RUN:
                cantidad_comprada = esperado_wei / UNIDAD_BNB
                tx_hash = "0x" + "d" * 64
                precio_ejecucion = precio_esperado
            else:
                aprobar_usdt_si_necesario(cantidad_wei)
                nonce = int(w3.eth.get_transaction_count(MI_DIRECCION, "pending"))
                balance_antes = balance_bnb_wei() / UNIDAD_BNB
                with STATE_LOCK:
                    estado["tx_pending"] = {
                        "hash": "", "hashes": [], "timestamp": time.time(), "tipo": "COMPRA",
                        "nonce": nonce, "saldo_bnb_antes": balance_antes,
                        "precio_estimado": precio_dex,
                    }
                    persistir_estado_bajo_lock()
                funcion = router.functions.swapExactTokensForETH(cantidad_wei, minimo, [USDT, WBNB], MI_DIRECCION, int(time.time()) + 300)
                tx_base = campos_tx(nonce)
                tx_base["gas"] = estimar_gas(funcion, tx_base)
                tx = funcion.build_transaction(tx_base)
                tx_hash, receipt = enviar_y_confirmar_con_bump(tx, registrar_hash=True)
                balance_despues = balance_bnb_wei() / UNIDAD_BNB
                cantidad_comprada = max(0.0, balance_despues - balance_antes)
                precio_ejecucion = cantidad_real / cantidad_comprada if cantidad_comprada > 0 else precio_dex
                
                if receipt:
                    registrar_calidad_ejecucion(
                        tx_hash=tx_hash, tipo="COMPRA", precio_esperado=precio_esperado,
                        precio_ejecutado=precio_ejecucion, slippage_real=abs(precio_ejecucion - precio_esperado) / precio_esperado * 100,
                        twap_referencia=_calcular_twap(), gas_usd=0, latencia_confirmacion=time.monotonic() - inicio,
                        liquidez_sesion="N/A",
                    )
            
            with STATE_LOCK:
                estado.update({
                    "en_posicion": True, "precio_entrada": precio_ejecucion, "precio_maximo": precio_ejecucion,
                    "cantidad": cantidad_comprada, "timestamp_entrada": datetime.now(timezone.utc).isoformat(),
                    "ultima_operacion": "COMPRA", "tx_hash_entrada": tx_hash, "tx_pending": None,
                    "ganancia_max_pct": 0.0, "velas_en_posicion": 0,
                    "atr_inicial": atr_inicial, "suelo_compra": suelo,
                    "gasto_total_usdt": float(estado.get("gasto_total_usdt", 0.0)) + cantidad_real,
                })
                persistir_estado_bajo_lock()
            
            if not DRY_RUN:
                registrar_trade("COMPRA", precio_ejecucion, cantidad_comprada, rsi, motivo, cantidad_real, tx_hash)
            
            print(f"\n{'🟢' * 40}")
            print(f"{Colores.BOLD}{Colores.FONDO_VERDE} {Colores.BLANCO}COMPRA CONFIRMADA{Colores.RESET}")
            print(f"{'🟢' * 40}")
            print(f"  💰 Cantidad : {_formatear_bnb(cantidad_comprada)} BNB")
            print(f"  💵 Precio   : {_formatear_usd(precio_ejecucion)}")
            print(f"  💲 Total    : {_formatear_usd(cantidad_real)} USDT")
            print(f"  📝 Motivo   : {motivo}")
            print(f"{'🟢' * 40}")
            notificar_compra(cantidad_comprada, precio_ejecucion, cantidad_real, tx_hash, motivo)
            return True
        except Exception as exc:
            print(f"{Colores.ROJO}[ERROR COMPRA]{Colores.RESET} {exc}")
            notificar_error(f"Error de compra: {exc}")
            return False

# ============================================================
# VENDER
# ============================================================

def vender(porcentaje: float = 1.0, motivo: str = "") -> bool:
    with TX_LOCK:
        inicio = time.monotonic()
        try:
            porcentaje = min(max(float(porcentaje), 0.0), 1.0)
            with STATE_LOCK:
                if not estado.get("en_posicion") or estado.get("tx_pending"):
                    return False
                cantidad_gestionada = float(estado.get("cantidad", 0.0))
                precio_entrada = float(estado.get("precio_entrada", 0.0))
            
            saldo_bnb = balance_bnb_wei() / UNIDAD_BNB
            disponible = min(cantidad_gestionada, saldo_bnb)
            maximo_por_gas = max(0.0, saldo_bnb - BNB_MINIMO_GAS)
            cantidad_vender = min(disponible * porcentaje, maximo_por_gas)
            if porcentaje >= 0.999:
                cantidad_vender = min(disponible, maximo_por_gas)
            if cantidad_vender < MIN_BNB_VENTA:
                return False
            
            bnb_wei = truncar_unidades(cantidad_vender, 18)
            estimado_wei, precio_dex = cotizar_bnb_a_usdt(bnb_wei)
            
            if not DRY_RUN:
                twap = _calcular_twap()
                if twap and precio_dex and abs(precio_dex - twap) / twap > (MAX_DESVIACION_EJECUCION * 1.5):
                    notificar_error(f"⛔ VENTA BLOQUEADA (TWAP) | {motivo}")
                    return False
            if not precio_valido(precio_dex, MAX_DESVIACION_EJECUCION):
                referencia = obtener_precio_con_fallback("BNBUSD", "BNBUSDT") or 0.0
                notificar_error(f"⛔ VENTA BLOQUEADA (precio) | {motivo}")
                return False
            
            valor_estimado = estimado_wei / UNIDAD_USDT
            slippage = calcular_slippage_dinamico(valor_estimado)
            minimo = int(estimado_wei * (1.0 - slippage))
            
            if DRY_RUN:
                tx_hash = "0x" + "e" * 64
                usdt_recibido = valor_estimado
                precio_ejecucion = precio_dex
            else:
                nonce = int(w3.eth.get_transaction_count(MI_DIRECCION, "pending"))
                bnb_antes = balance_bnb_wei()
                usdt_antes = balance_usdt_wei()
                with STATE_LOCK:
                    estado["tx_pending"] = {
                        "hash": "", "hashes": [], "timestamp": time.time(), "tipo": "VENTA",
                        "nonce": nonce, "cantidad_antes": cantidad_gestionada, "cantidad_objetivo": cantidad_vender,
                    }
                    persistir_estado_bajo_lock()
                funcion = router.functions.swapExactETHForTokens(minimo, [WBNB, USDT], MI_DIRECCION, int(time.time()) + 300)
                tx_base = campos_tx(nonce)
                tx_base["value"] = bnb_wei
                try:
                    tx_base["gas"] = estimar_gas(funcion, tx_base)
                except Exception:
                    tx_base["gas"] = 300_000
                tx = funcion.build_transaction(tx_base)
                tx_hash, receipt = enviar_y_confirmar_con_bump(tx, registrar_hash=True)
                bnb_despues = balance_bnb_wei()
                usdt_despues = balance_usdt_wei()
                gas_used = int(getattr(receipt, "gasUsed", 0))
                egp = getattr(receipt, "effectiveGasPrice", None)
                if egp is None or int(egp) <= 0:
                    egp = int(tx_base.get("gasPrice") or tx_base.get("maxFeePerGas") or w3.eth.gas_price)
                gas = gas_used * int(egp)
                usdt_recibido = max(0, usdt_despues - usdt_antes) / UNIDAD_USDT
                cantidad_vendida = max(0, bnb_antes - bnb_despues) / UNIDAD_BNB
                precio_ejecucion = (usdt_recibido / cantidad_vendida) if cantidad_vendida > 0 and usdt_recibido > 0 else precio_dex
                
                registrar_calidad_ejecucion(
                    tx_hash=tx_hash, tipo="VENTA", precio_esperado=precio_dex,
                    precio_ejecutado=precio_ejecucion, slippage_real=abs(precio_ejecucion - precio_dex) / precio_dex * 100,
                    twap_referencia=_calcular_twap(), gas_usd=(gas / UNIDAD_BNB * precio_dex),
                    latencia_confirmacion=time.monotonic() - inicio, liquidez_sesion="N/A",
                )
            
            pnl = ((precio_ejecucion - precio_entrada) / precio_entrada * 100.0) if precio_entrada > 0 else 0.0
            restante = max(0.0, cantidad_gestionada - cantidad_vender)
            cierre_total = restante < MIN_BNB_VENTA
            
            with STATE_LOCK:
                if cierre_total:
                    _cerrar_estado()
                    estado["ultima_operacion"] = "VENTA"
                else:
                    estado["cantidad"] = restante
                    estado["ultima_operacion"] = "VENTA_PARCIAL"
                estado["tx_pending"] = None
                persistir_estado_bajo_lock()
            
            if not DRY_RUN:
                registrar_trade("VENTA" if cierre_total else "VENTA_PARCIAL", precio_ejecucion, cantidad_vender, 0, motivo, usdt_recibido, tx_hash, pnl)
            
            # 🆕 Resetear señal pendiente al vender
            global senal_compra_pendiente, senal_compra_ts, ultima_venta_ts
            senal_compra_pendiente = False
            senal_compra_ts = 0.0
            ultima_venta_ts = time.time()
            
            emoji = "🔴" if pnl < 0 else "🟢"
            print(f"\n{emoji * 40}")
            print(f"{Colores.BOLD}{Colores.FONDO_ROJO if pnl < 0 else Colores.FONDO_VERDE} {Colores.BLANCO}VENTA CONFIRMADA{Colores.RESET}")
            print(f"{emoji * 40}")
            print(f"  💰 Cantidad : {_formatear_bnb(cantidad_vender)} BNB")
            print(f"  💵 Precio   : {_formatear_usd(precio_ejecucion)}")
            print(f"  💲 USDT     : {_formatear_usd(usdt_recibido)}")
            print(f"  📊 PnL      : {_color_pnl(pnl)}")
            print(f"  📝 Motivo   : {motivo}")
            print(f"{emoji * 40}")
            notificar_venta(cantidad_vender, precio_ejecucion, usdt_recibido, pnl, motivo, tx_hash)
            return True
        except Exception as exc:
            print(f"{Colores.ROJO}[ERROR VENTA]{Colores.RESET} {exc}")
            notificar_error(f"Error de venta: {exc}")
            return False

# ============================================================
# CICLO PRINCIPAL
# ============================================================

def ejecutar_ciclo() -> None:
    global cuarentena_hasta, ultimo_ciclo_ts, ultimo_ciclo_error, ciclos_ejecutados
    global senal_compra_pendiente, senal_compra_ts, suelo_pendiente, razon_pendiente, ultima_venta_ts
    
    detector_suelos = DetectorSuelosReales(ventana=48, toques_minimos=2)
    detector_techos = DetectorTechosReales()
    
    print(f"\n{Colores.BOLD}{Colores.CYAN}══{'═' * 78}{Colores.RESET}")
    print(f"{Colores.BOLD}{Colores.CYAN}[BOT]{Colores.RESET} {Colores.BOLD}NUEVO CICLO HUMANO-BOT{Colores.RESET} | {_timestamp_utc()}")
    
    if cuarentena_hasta > 0:
        ahora = time.time()
        if ahora < cuarentena_hasta:
            restante = cuarentena_hasta - ahora
            print(f"{Colores.AMARILLO}[CUARENTENA]{Colores.RESET} ❄️ Bot congelado. Restan {restante/3600:.1f} horas")
        else:
            print(f"{Colores.VERDE}[CUARENTENA]{Colores.RESET} ✅ Cuarentena finalizada")
            cuarentena_hasta = 0.0
            _guardar_cuarentena()
    
    print(f"{Colores.BOLD}{Colores.CYAN}══{'═' * 78}{Colores.RESET}")
    
    velas_multi = obtener_velas_multi_temporalidad("BNBUSD", CANDLE_INTERVAL, 1440, 10080)
    velas_4h = velas_multi.get("4h")
    
    if not velas_4h or not velas_4h.get("close") or len(velas_4h["close"]) < 48:
        print(f"\n{Colores.AMARILLO}[VELAS]{Colores.RESET} Sin datos suficientes, saltando ciclo")
        ultimo_ciclo_ts = time.time()
        ultimo_ciclo_error = None
        ciclos_ejecutados += 1
        return
    
    precio_dex = precio_dex_referencia()
    precio_externo = obtener_precio_con_fallback("BNBUSD", "BNBUSDT")
    precio = precio_dex or precio_externo or 0.0
    
    if precio is None or precio <= 0:
        print(f"\n{Colores.ROJO}[ERROR]{Colores.RESET} No se pudo obtener precio")
        ultimo_ciclo_ts = time.time()
        ultimo_ciclo_error = "No se pudo obtener precio"
        ciclos_ejecutados += 1
        return
    
    closes_hist = velas_4h["close"]
    highs_hist = velas_4h["high"]
    lows_hist = velas_4h["low"]
    opens_hist = velas_4h["open"]
    volumes_hist = velas_4h["volume"]
    
    rsi_arr = calcular_rsi(closes_hist, 14)
    rsi_actual = rsi_arr[-1] if rsi_arr[-1] is not None else 50.0
    
    atr_arr = calcular_atr(highs_hist, lows_hist, closes_hist, 14)
    atr_actual = atr_arr[-1] if atr_arr[-1] is not None else precio * 0.02
    
    ema_20_arr = calcular_ema(closes_hist, 20)
    ema_50_arr = calcular_ema(closes_hist, 50)
    ema_200_arr = calcular_ema(closes_hist, 200)
    
    ema_20 = ema_20_arr[-1] if ema_20_arr[-1] is not None else precio
    ema_50 = ema_50_arr[-1] if ema_50_arr[-1] is not None else precio
    ema_200 = ema_200_arr[-1] if ema_200_arr[-1] is not None else precio
    
    _, bb_media, bb_inf = calcular_bollinger(closes_hist, 20, 2.0)
    bb_inferior = bb_inf[-1] if bb_inf[-1] is not None else precio * 0.95
    bb_media_val = bb_media[-1] if bb_media[-1] is not None else precio
    
    print(f"\n{Colores.BOLD}{Colores.AZUL}[INDICADORES 4H]{Colores.RESET}")
    print(f"  {Colores.DIM}Velas disponibles{Colores.RESET} : {len(closes_hist)}")
    print(f"  {Colores.DIM}RSI (14){Colores.RESET}         : {rsi_actual:.1f} (umbral compra: ≤{RSI_MAX_COMPRA})")
    print(f"  {Colores.DIM}ATR (14){Colores.RESET}         : {atr_actual:.4f} ({atr_actual/precio*100:.2f}% del precio)")
    print(f"  {Colores.DIM}EMA 20{Colores.RESET}           : {_formatear_usd(ema_20)}")
    print(f"  {Colores.DIM}EMA 50{Colores.RESET}           : {_formatear_usd(ema_50)}")
    print(f"  {Colores.DIM}EMA 200{Colores.RESET}          : {_formatear_usd(ema_200)}")
    print(f"  {Colores.DIM}BB Inferior{Colores.RESET}      : {_formatear_usd(bb_inferior)}")
    print(f"  {Colores.DIM}BB Media{Colores.RESET}         : {_formatear_usd(bb_media_val)}")
    
    saldo_bnb = balance_bnb_wei() / UNIDAD_BNB
    saldo_usdt = balance_usdt_wei() / UNIDAD_USDT
    valor_total = saldo_bnb * precio + saldo_usdt
    
    print(f"\n{Colores.BOLD}{Colores.CYAN}[SALDOS]{Colores.RESET}")
    print(f"  {Colores.DIM}BNB{Colores.RESET}              : {_formatear_bnb(saldo_bnb)}")
    print(f"  {Colores.DIM}USDT{Colores.RESET}             : {_formatear_usd(saldo_usdt)}")
    print(f"  {Colores.DIM}VALOR TOTAL{Colores.RESET}      : {_formatear_usd(valor_total)}")
    
    verificar_y_alertar_gas()
    notificar_heartbeat()
    
    if precio_dex and precio_externo:
        diferencia = ((precio_dex - precio_externo) / precio_externo * 100)
        print(f"\n{Colores.BOLD}{Colores.CYAN}[MERCADO]{Colores.RESET}")
        print(f"  {Colores.DIM}PRECIO DEX{Colores.RESET}      : {_formatear_usd(precio_dex)}")
        print(f"  {Colores.DIM}PRECIO KRAKEN{Colores.RESET}   : {_formatear_usd(precio_externo)}")
        print(f"  {Colores.DIM}DIFERENCIA{Colores.RESET}      : {_formatear_pct(diferencia)}")
    
    with STATE_LOCK:
        en_posicion = bool(estado.get("en_posicion"))
        entrada = float(estado.get("precio_entrada", 0.0))
        cantidad = float(estado.get("cantidad", 0.0))
        ganancia_max = float(estado.get("ganancia_max_pct", 0.0))
        velas_en_pos = int(estado.get("velas_en_posicion", 0))
        suelo_compra = float(estado.get("suelo_compra", 0.0))
    
    bear = esta_en_bear_market(closes_hist)
    crash = hay_crash_reciente(closes_hist)
    tend_bajista = tendencia_corto_plazo_bajista(closes_hist)
    
    verificar_bear_prolongado(bear)
    
    print(f"\n{Colores.BOLD}{Colores.MAGENTA}[FILTROS DE MERCADO]{Colores.RESET}")
    print(f"  {Colores.DIM}Bear Market{Colores.RESET}      : {'⚠️ SÍ' if bear else '✅ NO'}")
    print(f"  {Colores.DIM}Crash Reciente{Colores.RESET}   : {'⚠️ SÍ' if crash else '✅ NO'}")
    print(f"  {Colores.DIM}Tendencia Bajista{Colores.RESET} : {'⚠️ SÍ' if tend_bajista else '✅ NO'}")
    
    es_suelo, precio_suelo, distancia, razon = detector_suelos.es_suelo_real(
        lows_hist, closes_hist, volumes_hist, opens_hist
    )
    
    print(f"\n{Colores.BOLD}{Colores.MAGENTA}[DETECTOR DE SUELO]{Colores.RESET}")
    if es_suelo:
        print(f"  {Colores.VERDE}✅ SUELO DETECTADO{Colores.RESET}")
        print(f"  {Colores.DIM}Precio Suelo{Colores.RESET}    : {_formatear_usd(precio_suelo)}")
        print(f"  {Colores.DIM}Distancia{Colores.RESET}        : {distancia:.1f}% (máx: 6%)")
        print(f"  {Colores.DIM}RSI Actual{Colores.RESET}       : {rsi_actual:.1f} (umbral: ≤{RSI_MAX_COMPRA})")
        print(f"  {Colores.DIM}Razón{Colores.RESET}            : {razon}")
    else:
        print(f"  {Colores.DIM}Estado{Colores.RESET}           : {razon}")
    
    with STATE_LOCK:
        pico_previo = float(estado.get('historico_valor_pico', valor_total) or valor_total)
        pico_actual = max(pico_previo, valor_total)
        estado['historico_valor_pico'] = pico_actual
    
    drawdown_actual = ((pico_actual - valor_total) / pico_actual) if pico_actual > 0 else 0.0
    
    print(f"\n{Colores.BOLD}{Colores.MAGENTA}[PROTECCIÓN]{Colores.RESET}")
    print(f"  {Colores.DIM}Drawdown Actual{Colores.RESET}  : {drawdown_actual*100:.2f}% (máx: {MAX_DRAWDOWN*100:.0f}%)")
    
    if drawdown_actual >= MAX_DRAWDOWN:
        print(f"  {Colores.ROJO}⚠️ DRAWDOWN EXCEDIDO - Bot bloqueado hasta recuperación{Colores.RESET}")
        if en_posicion:
            vender(1.0, f"PROTECCION_DRAWDOWN {drawdown_actual*100:.2f}%")
        else:
            notificar_error(
                f"🚨 BOT BLOQUEADO: Drawdown {drawdown_actual*100:.1f}% excede máximo {MAX_DRAWDOWN*100:.0f}%. "
                f"Sin posición abierta. El bot no comprará hasta que el valor de cartera se recupere."
            )
        ultimo_ciclo_ts = time.time()
        ultimo_ciclo_error = f"Drawdown {drawdown_actual*100:.1f}% excede máximo {MAX_DRAWDOWN*100:.0f}%"
        ciclos_ejecutados += 1
        return
    
    if not en_posicion:
        print(f"\n{Colores.BOLD}{Colores.AZUL}[ESTRATEGIA]{Colores.RESET} Modo: Buscando entrada")
        
        # 🆕 PASO 1: Espera post-venta
        if ultima_venta_ts > 0 and (time.time() - ultima_venta_ts) < (ESPERA_POST_VENTA * 4 * 3600):
            restante = (ESPERA_POST_VENTA * 4 * 3600) - (time.time() - ultima_venta_ts)
            print(f"  {Colores.AMARILLO}⏳ PASO 1: Espera post-venta. Restan {restante/3600:.1f} horas{Colores.RESET}")
            ultimo_ciclo_ts = time.time()
            ultimo_ciclo_error = None
            ciclos_ejecutados += 1
            return
        
        # 🆕 PASO 2: Cuarentena
        if cuarentena_hasta > 0 and time.time() < cuarentena_hasta:
            restante = cuarentena_hasta - time.time()
            print(f"  {Colores.AMARILLO}❄️ PASO 2: Bot en cuarentena. Restan {restante/3600:.1f} horas{Colores.RESET}")
            ultimo_ciclo_ts = time.time()
            ultimo_ciclo_error = None
            ciclos_ejecutados += 1
            return
        
        # 🆕 PASO 3: Bear Market
        if bear:
            print(f"  {Colores.ROJO}⛔ PASO 3: Bear Market - Sin compras{Colores.RESET}")
            ultimo_ciclo_ts = time.time()
            ultimo_ciclo_error = None
            ciclos_ejecutados += 1
            return
        
        # 🆕 PASO 4: Crash Reciente
        if crash:
            print(f"  {Colores.ROJO}⛔ PASO 4: Crash Reciente - Sin compras{Colores.RESET}")
            ultimo_ciclo_ts = time.time()
            ultimo_ciclo_error = None
            ciclos_ejecutados += 1
            return
        
        # 🆕 PASO 5: Tendencia Bajista
        if tend_bajista:
            print(f"  {Colores.ROJO}⛔ PASO 5: Tendencia Bajista - Sin compras{Colores.RESET}")
            ultimo_ciclo_ts = time.time()
            ultimo_ciclo_error = None
            ciclos_ejecutados += 1
            return
        
        # 🆕 PASO 6: Suelo Real
        if not es_suelo:
            print(f"  {Colores.DIM}PASO 6: Sin suelo válido - {razon}{Colores.RESET}")
            ultimo_ciclo_ts = time.time()
            ultimo_ciclo_error = None
            ciclos_ejecutados += 1
            return
        else:
            print(f"  {Colores.VERDE}✅ PASO 6: Suelo detectado ✓{Colores.RESET}")
        
        # 🆕 PASO 7: RSI
        if rsi_actual > RSI_MAX_COMPRA:
            print(f"  {Colores.AMARILLO}⏳ PASO 7: RSI {rsi_actual:.1f} > {RSI_MAX_COMPRA}{Colores.RESET}")
            ultimo_ciclo_ts = time.time()
            ultimo_ciclo_error = None
            ciclos_ejecutados += 1
            return
        else:
            print(f"  {Colores.VERDE}✅ PASO 7: RSI {rsi_actual:.1f} ≤ {RSI_MAX_COMPRA} ✓{Colores.RESET}")
        
        # 🆕 PASO 8: Vela Verde
        c = closes_hist[-1]
        o = opens_hist[-1]
        if c <= o:
            print(f"  {Colores.AMARILLO}⏳ PASO 8: Vela roja - Esperando confirmación{Colores.RESET}")
            ultimo_ciclo_ts = time.time()
            ultimo_ciclo_error = None
            ciclos_ejecutados += 1
            return
        else:
            print(f"  {Colores.VERDE}✅ PASO 8: Vela verde ✓{Colores.RESET}")
        
        # 🆕 PASO 9: Anti-Euforia
        vetar, razon_veto = veto_anti_euforia(closes_hist)
        if vetar:
            cuarentena_hasta = time.time() + (CUARENTENA_VELAS * 4 * 3600)
            _guardar_cuarentena()
            fin_cuarentena = datetime.fromtimestamp(cuarentena_hasta, timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
            print(f"\n  {Colores.AMARILLO}🚫 PASO 9: COMPRA BLOQUEADA - ANTI-EUFORIA{Colores.RESET}")
            print(f"  {Colores.DIM}   {razon_veto}{Colores.RESET}")
            print(f"  {Colores.DIM}   ❄️ Bot congelado hasta {fin_cuarentena} (guardado en DB){Colores.RESET}")
            notificar_veto_euforia(c, razon_veto, fin_cuarentena)
            ultimo_ciclo_ts = time.time()
            ultimo_ciclo_error = None
            ciclos_ejecutados += 1
            return
        else:
            print(f"  {Colores.VERDE}✅ PASO 9: Anti-Euforia OK ✓{Colores.RESET}")
        
        # 🆕 PASO 10: USDT Suficiente
        monto = saldo_usdt * 0.95
        if monto < USDT_MINIMO:
            print(f"  {Colores.AMARILLO}⏳ PASO 10: USDT insuficiente ${saldo_usdt:.2f} (mínimo: ${USDT_MINIMO:.2f}){Colores.RESET}")
            ultimo_ciclo_ts = time.time()
            ultimo_ciclo_error = None
            ciclos_ejecutados += 1
            return
        else:
            print(f"  {Colores.VERDE}✅ PASO 10: USDT suficiente (${saldo_usdt:.2f}) ✓{Colores.RESET}")
        
        # 🆕 PASO 11: Doble Verificación
        if not senal_compra_pendiente:
            # Primera señal: guardar y esperar 9 velas
            senal_compra_pendiente = True
            senal_compra_ts = time.time()
            suelo_pendiente = precio_suelo
            razon_pendiente = razon
            print(f"\n  {Colores.AMARILLO}🔍 PASO 11: ¡SEÑAL DETECTADA! - Esperando {VELAS_VERIFICACION} velas para confirmar{Colores.RESET}")
            print(f"  {Colores.DIM}Suelo{Colores.RESET}             : {_formatear_usd(precio_suelo)}")
            print(f"  {Colores.DIM}RSI{Colores.RESET}               : {rsi_actual:.1f}")
            print(f"  {Colores.DIM}USDT Disponible{Colores.RESET}   : {_formatear_usd(saldo_usdt)}")
            print(f"  {Colores.DIM}Próxima verificación{Colores.RESET}: en ~36 horas")
        else:
            # Segunda verificación: ¿pasaron 9 velas?
            velas_transcurridas = (time.time() - senal_compra_ts) / (4 * 3600)
            if velas_transcurridas >= VELAS_VERIFICACION:
                print(f"\n  {Colores.CYAN}🔍 PASO 11: Verificación final (pasaron {velas_transcurridas:.1f} velas){Colores.RESET}")
                
                # Re-verificar todo
                if bear:
                    print(f"  {Colores.ROJO}❌ Verificación fallida: Bear Market{Colores.RESET}")
                elif crash:
                    print(f"  {Colores.ROJO}❌ Verificación fallida: Crash Reciente{Colores.RESET}")
                elif tend_bajista:
                    print(f"  {Colores.ROJO}❌ Verificación fallida: Tendencia Bajista{Colores.RESET}")
                elif not es_suelo:
                    print(f"  {Colores.ROJO}❌ Verificación fallida: Suelo ya no es válido{Colores.RESET}")
                elif rsi_actual > RSI_MAX_COMPRA:
                    print(f"  {Colores.ROJO}❌ Verificación fallida: RSI {rsi_actual:.1f} > {RSI_MAX_COMPRA}{Colores.RESET}")
                elif c <= o:
                    print(f"  {Colores.ROJO}❌ Verificación fallida: Vela roja{Colores.RESET}")
                else:
                    print(f"  {Colores.VERDE}🚀 ¡SEÑAL DE COMPRA CONFIRMADA!{Colores.RESET}")
                    print(f"  {Colores.DIM}Monto{Colores.RESET}             : {_formatear_usd(monto)}")
                    print(f"  {Colores.DIM}Suelo{Colores.RESET}             : {_formatear_usd(suelo_pendiente)}")
                    print(f"  {Colores.DIM}RSI{Colores.RESET}               : {rsi_actual:.1f}")
                    print(f"  {Colores.DIM}Precio Entrada{Colores.RESET}    : {_formatear_usd(c)}")
                    motivo = f"{razon_pendiente} | ✅ Verificado +{VELAS_VERIFICACION}v"
                    comprar(monto, motivo, suelo_pendiente, rsi_actual, atr_actual)
                
                # Resetear
                senal_compra_pendiente = False
                senal_compra_ts = 0.0
            else:
                restante = (VELAS_VERIFICACION * 4 * 3600) - (time.time() - senal_compra_ts)
                print(f"  {Colores.DIM}PASO 11: Esperando verificación... Restan {restante/3600:.1f} horas{Colores.RESET}")
        
        ultimo_ciclo_ts = time.time()
        ultimo_ciclo_error = None
        ciclos_ejecutados += 1
        return
    
    if entrada <= 0 or cantidad < MIN_BNB_VENTA:
        ultimo_ciclo_ts = time.time()
        ultimo_ciclo_error = None
        ciclos_ejecutados += 1
        return
    
    ganancia_pct = (precio - entrada) / entrada * 100
    
    with STATE_LOCK:
        precio_max = float(estado.get("precio_maximo", entrada))
        nuevo_max = max(precio_max, precio)
        ganancia_max = max(ganancia_max, (nuevo_max - entrada) / entrada * 100)
        velas_en_pos += 1
        
        estado["precio_maximo"] = nuevo_max
        estado["ganancia_max_pct"] = ganancia_max
        estado["velas_en_posicion"] = velas_en_pos
        persistir_estado_bajo_lock()
    
    print(f"\n{Colores.BOLD}{Colores.MAGENTA}[POSICIÓN ABIERTA]{Colores.RESET}")
    print(f"  {Colores.DIM}Entrada{Colores.RESET}           : {_formatear_usd(entrada)}")
    print(f"  {Colores.DIM}Actual{Colores.RESET}            : {_formatear_usd(precio)}")
    print(f"  {Colores.DIM}Cantidad{Colores.RESET}          : {_formatear_bnb(cantidad)} BNB")
    print(f"  {Colores.DIM}Valor Posición{Colores.RESET}    : {_formatear_usd(cantidad * precio)}")
    print(f"  {Colores.DIM}PnL Actual{Colores.RESET}        : {_color_pnl(ganancia_pct)}")
    print(f"  {Colores.DIM}Máximo Alcanzado{Colores.RESET}  : {_formatear_usd(nuevo_max)} (+{ganancia_max:.1f}%)")
    print(f"  {Colores.DIM}Velas en posición{Colores.RESET} : {velas_en_pos} ({velas_en_pos*4/24:.1f} días)")
    print(f"  {Colores.DIM}Suelo Compra{Colores.RESET}      : {_formatear_usd(suelo_compra)}")
    
    toma_nivel = entrada * (1 + TOMA_PCT/100)
    
    print(f"\n{Colores.BOLD}{Colores.MAGENTA}[NIVELES DE SALIDA]{Colores.RESET}")
    print(f"  {Colores.DIM}Toma +{TOMA_PCT}%{Colores.RESET}          : {_formatear_usd(toma_nivel)} (caída {CAIDA_PCT}% desde máximo)")
    
    motivo_venta = None
    
    # 🏆 TOMA +17.6%/-4.4%
    if ganancia_max >= TOMA_PCT:
        caida = (nuevo_max - precio) / nuevo_max * 100
        print(f"\n{Colores.BOLD}{Colores.AMARILLO}[EVALUANDO TOMA]{Colores.RESET}")
        print(f"  {Colores.DIM}Ganancia Máx{Colores.RESET}     : +{ganancia_max:.1f}% (≥ {TOMA_PCT}%)")
        print(f"  {Colores.DIM}Caída desde máx{Colores.RESET}  : -{caida:.1f}% (umbral: {CAIDA_PCT}%)")
        if caida >= CAIDA_PCT:
            motivo_venta = f"💎 TOMA +{ganancia_max:.1f}% | Caída -{caida:.1f}%"
            print(f"  {Colores.VERDE}✅ TOMA ACTIVADA{Colores.RESET}")
        else:
            print(f"  {Colores.DIM}⏳ Esperando caída{Colores.RESET}")
    
    # 🏔️ TECHO
    elif ganancia_pct >= 9.0:
        es_techo, razon_techo = detector_techos.es_techo_real(
            closes_hist, opens_hist, highs_hist, entrada, atr_actual
        )
        print(f"\n{Colores.BOLD}{Colores.AMARILLO}[EVALUANDO TECHO]{Colores.RESET}")
        print(f"  {Colores.DIM}Ganancia{Colores.RESET}         : +{ganancia_pct:.2f}%")
        print(f"  {Colores.DIM}Resultado{Colores.RESET}        : {razon_techo}")
        if es_techo:
            motivo_venta = f"🏔️ TECHO | {razon_techo} | Gan +{ganancia_pct:.2f}%"
            print(f"  {Colores.VERDE}✅ TECHO CONFIRMADO{Colores.RESET}")
    
    if motivo_venta:
        print(f"\n{Colores.BOLD}{Colores.VERDE}[VENTA]{Colores.RESET} {motivo_venta}")
        vender(1.0, motivo_venta)
        ultimo_ciclo_ts = time.time()
        ultimo_ciclo_error = None
        ciclos_ejecutados += 1
        return
    
    print(f"\n{Colores.DIM}[ESTADO]{Colores.RESET} Sin señales de venta. Próximo ciclo en {ESCANEO}s")
    
    ultimo_ciclo_ts = time.time()
    ultimo_ciclo_error = None
    ciclos_ejecutados += 1

# ============================================================
# RATE LIMITING
# ============================================================

_rate_limits = defaultdict(list)

def rate_limit(max_requests=10, window=60):
    def decorator(f):
        def wrapper(*args, **kwargs):
            ip = request.remote_addr or "unknown"
            now = time.time()
            _rate_limits[ip] = [t for t in _rate_limits[ip] if now - t < window]
            if len(_rate_limits[ip]) >= max_requests:
                return jsonify({"error": "rate limit exceeded"}), 429
            _rate_limits[ip].append(now)
            return f(*args, **kwargs)
        wrapper.__name__ = f.__name__
        return wrapper
    return decorator

# ============================================================
# FLASK
# ============================================================

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot BNB Humano-Bot v2.0 activo", 200

@app.route("/status")
@rate_limit(max_requests=10, window=60)
def status():
    if not STATUS_TOKEN:
        return jsonify({"error": "STATUS_TOKEN no configurado"}), 503
    cabecera = request.headers.get("Authorization", "").strip()
    recibido = cabecera[7:].strip() if cabecera.lower().startswith("bearer ") else cabecera
    if not hmac.compare_digest(recibido, STATUS_TOKEN):
        return jsonify({"error": "unauthorized"}), 401
    
    ahora = datetime.now(timezone.utc)
    tiempo_desde_ultimo_ciclo = (ahora.timestamp() - ultimo_ciclo_ts) if ultimo_ciclo_ts > 0 else None
    
    with STATE_LOCK:
        copia = {
            "en_posicion": estado.get("en_posicion"),
            "cantidad": estado.get("cantidad"),
            "precio_entrada": estado.get("precio_entrada"),
            "ganancia_max_pct": estado.get("ganancia_max_pct"),
            "velas_en_posicion": estado.get("velas_en_posicion"),
        }
    
    rpc_ok = False
    try:
        w3.eth.get_block_number()
        rpc_ok = True
    except Exception:
        pass
    
    supabase_ok = False
    try:
        test = cargar_estado()
        supabase_ok = test is not None
    except Exception:
        pass
    
    try:
        saldo_bnb = balance_bnb_wei() / UNIDAD_BNB
        gas_ok = saldo_bnb >= BNB_MINIMO_GAS * 2
    except Exception:
        saldo_bnb = 0.0
        gas_ok = False
    
    if not rpc_ok:
        estado_general = "critical"
    elif not supabase_ok:
        estado_general = "degraded"
    elif tiempo_desde_ultimo_ciclo and tiempo_desde_ultimo_ciclo > ESCANEO * 3:
        estado_general = "degraded"
    elif ultimo_ciclo_error:
        estado_general = "warning"
    elif not gas_ok:
        estado_general = "warning"
    else:
        estado_general = "healthy"
    
    return jsonify({
        "status": estado_general,
        "dry_run": DRY_RUN,
        "chain_id": chain_id_real,
        "wallet": f"{MI_DIRECCION[:8]}...{MI_DIRECCION[-6:]}",
        "timestamp": ahora.isoformat(),
        "ciclos_ejecutados": ciclos_ejecutados,
        "ultimo_ciclo_hace_segundos": round(tiempo_desde_ultimo_ciclo, 1) if tiempo_desde_ultimo_ciclo else None,
        "ultimo_error": ultimo_ciclo_error,
        "conexiones": {
            "rpc": rpc_ok,
            "supabase": supabase_ok,
        },
        "gas": {
            "bnb_saldo": round(saldo_bnb, 6),
            "bnb_minimo_requerido": round(BNB_MINIMO_GAS * 2, 6),
            "suficiente": gas_ok,
        },
        "cuarentena_hasta": cuarentena_hasta if cuarentena_hasta > 0 else 0,
        **copia,
    })

@app.route("/metrics")
@rate_limit(max_requests=10, window=60)
def metrics():
    if not STATUS_TOKEN:
        return jsonify({"error": "STATUS_TOKEN no configurado"}), 503
    cabecera = request.headers.get("Authorization", "").strip()
    recibido = cabecera[7:].strip() if cabecera.lower().startswith("bearer ") else cabecera
    if not hmac.compare_digest(recibido, STATUS_TOKEN):
        return jsonify({"error": "unauthorized"}), 401
    return jsonify({"timestamp": datetime.now(timezone.utc).isoformat(), "performance": obtener_metricas()})

def _run_flask() -> None:
    puerto = env_int("PORT", 8080)
    app.run(host="0.0.0.0", port=puerto, use_reloader=False, threaded=True)

# ============================================================
# MAIN
# ============================================================

def main() -> None:
    global cuarentena_hasta, ultimo_ciclo_ts, ultimo_ciclo_error, ciclos_ejecutados
    
    threading.Thread(target=_run_flask, daemon=True).start()
    if not STATUS_TOKEN:
        print(f"{Colores.AMARILLO}[AVISO]{Colores.RESET} STATUS_TOKEN no configurado")
    
    _cargar_cuarentena()
    
    notificar_inicio()
    print(f"\n{Colores.BOLD}{Colores.CYAN}{'=' * 80}{Colores.RESET}")
    print(f"{Colores.BOLD}{Colores.CYAN}  BNB HUMANO-BOT v2.0{Colores.RESET}")
    print(f"{Colores.BOLD}{Colores.CYAN}  RSI {RSI_MAX_COMPRA} | Toma +{TOMA_PCT}%/{CAIDA_PCT}% | Techo 9%{Colores.RESET}")
    print(f"{Colores.BOLD}{Colores.CYAN}  🛡️ Anti-Euforia: {CUARENTENA_VELAS}v (persistente en DB){Colores.RESET}")
    print(f"{Colores.BOLD}{Colores.CYAN}  Wallet: {MI_DIRECCION[:8]}...{MI_DIRECCION[-6:]}{Colores.RESET}")
    print(f"{Colores.BOLD}{Colores.CYAN}{'=' * 80}{Colores.RESET}")
    while True:
        inicio = time.monotonic()
        try:
            reconciliar_estado()
            ejecutar_ciclo()
        except KeyboardInterrupt:
            print(f"\n{Colores.AMARILLO}[AVISO]{Colores.RESET} Bot detenido por usuario")
            notificar("⚠️ Bot detenido por usuario")
            break
        except Exception as exc:
            print(f"{Colores.ROJO}[ERROR]{Colores.RESET} CICLO: {type(exc).__name__}: {exc}")
            traceback.print_exc()
            notificar_error(f"Error general del ciclo: {exc}")
            ultimo_ciclo_error = f"{type(exc).__name__}: {str(exc)[:200]}"
            ultimo_ciclo_ts = time.time()
        duracion = time.monotonic() - inicio
        espera = max(5, ESCANEO - int(duracion))
        print(f"\n{'-' * 80}")
        print(f"{Colores.BOLD}{Colores.CYAN}[INFO]{Colores.RESET} PROXIMO CICLO en {espera}s | Duración {duracion:.2f}s")
        print(f"{'-' * 80}")
        time.sleep(espera)

if __name__ == "__main__":
    main()

========== estrategia.py ==========
from typing import List, Tuple

from indicadores import (
    calcular_bollinger,
    calcular_ema,
    calcular_macd,
    calcular_rsi,
)

# ============================================================
# ESTRATEGIA HUMANO-BOT v2.0
# 🏆 Versión alineada con backtest ganador (+738%)
# 🐻 Bear Market: SOLO EMA50 < EMA200
# ============================================================

class DetectorSuelosReales:
    """Detecta suelos reales basados en toques múltiples"""
    def __init__(self, ventana: int = 48, toques_minimos: int = 2):
        self.ventana = ventana
        self.toques_minimos = toques_minimos

    def contar_toques(self, lows: List[float], nivel: float, tolerancia_pct: float = 2.5) -> int:
        toques = 0
        for low in lows[-self.ventana:]:
            if nivel > 0 and abs(low - nivel) / nivel * 100 <= tolerancia_pct:
                toques += 1
        return toques

    def es_suelo_real(self, lows: List[float], closes: List[float],
                      volumes: List[float], opens: List[float]) -> Tuple[bool, float, float, str]:
        if len(lows) < self.ventana:
            return False, 0.0, 100.0, "Datos insuficientes"

        precio_actual = closes[-1]
        lows_recientes = lows[-self.ventana:]
        candidatos = []

        for i in range(1, len(lows_recientes) - 1):
            if lows_recientes[i] <= lows_recientes[i-1] and lows_recientes[i] <= lows_recientes[i+1]:
                nivel = lows_recientes[i]
                toques = self.contar_toques(lows, nivel)
                if toques >= self.toques_minimos and nivel <= precio_actual:
                    candidatos.append((nivel, toques))

        if not candidatos:
            return False, 0.0, 100.0, "Sin suelos válidos"

        suelo_real = max(c[0] for c in candidatos)
        toques_suelo = max(c[1] for c in candidatos if c[0] == suelo_real)
        distancia_pct = (precio_actual - suelo_real) / suelo_real * 100 if suelo_real > 0 else 100.0

        if distancia_pct < 0:
            return False, suelo_real, distancia_pct, "Precio POR DEBAJO del suelo"
        if distancia_pct > 6.0:
            return False, suelo_real, distancia_pct, f"Distancia {distancia_pct:.1f}%"

        # Volumen SUBIENDO
        if len(volumes) >= 3:
            if volumes[-1] <= volumes[-2]:
                return False, suelo_real, distancia_pct, "Volumen bajando"

        if closes[-1] <= opens[-1]:
            return False, suelo_real, distancia_pct, "Vela roja (sin rebote)"

        return True, suelo_real, distancia_pct, f"Suelo ${suelo_real:.2f} ({toques_suelo} toques) | {distancia_pct:.1f}%"


class DetectorTechosReales:
    """Detecta techos reales con Bollinger + RSI + MACD"""
    def es_techo_real(self, closes: List[float], opens: List[float], highs: List[float],
                      precio_entrada: float, atr: float) -> Tuple[bool, str]:
        if len(closes) < 20:
            return False, "Datos insuficientes"

        precio_actual = closes[-1]
        apertura_actual = opens[-1]

        ema_20 = calcular_ema(closes, 20)
        ema_50 = calcular_ema(closes, 50)

        en_tendencia = False
        if ema_20[-1] and ema_50[-1] and ema_20[-10] and ema_50[-10]:
            pendiente_20 = (ema_20[-1] - ema_20[-10]) / ema_20[-10] * 100
            pendiente_50 = (ema_50[-1] - ema_50[-10]) / ema_50[-10] * 100
            en_tendencia = abs(pendiente_20) > 2.0 and abs(pendiente_50) > 1.5

        ganancia_minima = 15.0 if en_tendencia else 9.0

        if precio_entrada > 0:
            ganancia = (precio_actual - precio_entrada) / precio_entrada * 100
            if ganancia < ganancia_minima:
                return False, f"Gan {ganancia:+.1f}% (<{ganancia_minima:.0f}%)"

        _, _, superior_bb = calcular_bollinger(closes, 20, 2.0)
        bb_sup = superior_bb[-1] if superior_bb[-1] is not None else precio_actual * 1.1

        rsi = calcular_rsi(closes, 14)
        rsi_actual = rsi[-1] if rsi[-1] is not None else 50.0

        _, _, histogram = calcular_macd(closes)
        macd_debilitandose = False
        if len(histogram) >= 3 and histogram[-1] and histogram[-2] and histogram[-3]:
            macd_debilitandose = (histogram[-1] < histogram[-2] and histogram[-2] < histogram[-3])

        cerca_bb = precio_actual >= bb_sup * 0.98
        rsi_alto = rsi_actual > 68
        vela_roja = precio_actual < apertura_actual

        if vela_roja and rsi_alto and macd_debilitandose:
            return True, "Techo confirmado"
        if vela_roja and rsi_actual > 75:
            return True, "Sobrecompra"
        if vela_roja and cerca_bb and rsi_actual > 65:
            return True, "Techo BB"

        return False, "Sin confirmación"


# ============================================================
# FILTROS DE MERCADO (ALINEADOS CON BACKTEST GANADOR)
# ============================================================

def esta_en_bear_market(closes: List[float]) -> bool:
    """
    🏆 VERSIÓN BACKTEST GANADOR:
    Solo bloquea si EMA50 < EMA200
    Sin filtros extra de precio < EMA200
    """
    if len(closes) < 200:
        return False
    
    ema_50 = calcular_ema(closes, 50)
    ema_200 = calcular_ema(closes, 200)
    
    if ema_50[-1] is None or ema_200[-1] is None:
        return False
    
    # ÚNICA CONDICIÓN: EMA50 < EMA200
    if ema_50[-1] > 0 and ema_200[-1] > 0 and ema_50[-1] < ema_200[-1]:
        return True
    
    return False


def hay_crash_reciente(closes: List[float]) -> bool:
    if len(closes) < 180:
        return False
    recientes = closes[-180:]
    if not recientes:
        return False
    maximo = max(recientes)
    actual = closes[-1]
    if maximo <= 0:
        return False
    return (maximo - actual) / maximo * 100 >= 20.0


def tendencia_corto_plazo_bajista(closes: List[float]) -> bool:
    if len(closes) < 30:
        return False
    ema_20 = calcular_ema(closes, 20)
    if ema_20[-1] is None or len(ema_20) < 10 or ema_20[-10] is None:
        return False
    pendiente = (ema_20[-1] - ema_20[-10]) / ema_20[-10] * 100
    return pendiente < -2.0

========== indicadores.py ==========
import math
from typing import List, Optional, Sequence, Tuple

Serie = List[Optional[float]]

def calcular_ema(precios: Sequence[float], periodo: int) -> List[Optional[float]]:
    """🏆 VERSIÓN BACKTEST GANADOR - Sin validaciones extra"""
    if len(precios) < periodo:
        return [None] * len(precios)
    
    resultado = [None] * len(precios)
    multiplicador = 2.0 / (periodo + 1.0)
    
    # Semilla simple (promedio de primeras 'periodo' velas)
    semilla = sum(precios[:periodo]) / periodo
    resultado[periodo - 1] = semilla
    
    for i in range(periodo, len(precios)):
        if resultado[i-1] is not None:
            resultado[i] = precios[i] * multiplicador + resultado[i-1] * (1 - multiplicador)
    
    return resultado


def calcular_rsi(precios: Sequence[float], periodo: int = 14) -> List[Optional[float]]:
    """🏆 VERSIÓN BACKTEST GANADOR"""
    if len(precios) < periodo + 1:
        return [None] * len(precios)
    
    resultado = [None] * len(precios)
    ganancias = []
    perdidas = []
    
    for i in range(1, len(precios)):
        cambio = precios[i] - precios[i-1]
        ganancias.append(max(cambio, 0.0))
        perdidas.append(max(-cambio, 0.0))
    
    ganancia_media = sum(ganancias[:periodo]) / periodo
    perdida_media = sum(perdidas[:periodo]) / periodo
    
    def rsi_valor(g, p):
        if p == 0:
            return 100.0 if g > 0 else 50.0
        return 100.0 - (100.0 / (1.0 + g / p))
    
    resultado[periodo] = rsi_valor(ganancia_media, perdida_media)
    
    for i in range(periodo + 1, len(precios)):
        ganancia_media = (ganancia_media * (periodo - 1) + ganancias[i-1]) / periodo
        perdida_media = (perdida_media * (periodo - 1) + perdidas[i-1]) / periodo
        resultado[i] = rsi_valor(ganancia_media, perdida_media)
    
    return resultado


def calcular_bollinger(precios: Sequence[float], periodo: int = 20, desv: float = 2.0):
    """🏆 VERSIÓN BACKTEST GANADOR"""
    if len(precios) < periodo:
        return [None]*len(precios), [None]*len(precios), [None]*len(precios)
    
    superior = [None]*len(precios)
    media = [None]*len(precios)
    inferior = [None]*len(precios)
    
    for i in range(periodo-1, len(precios)):
        ventana = precios[i-periodo+1:i+1]
        promedio = sum(ventana)/periodo
        varianza = sum((v-promedio)**2 for v in ventana)/periodo
        desviacion = math.sqrt(varianza)
        media[i] = promedio
        superior[i] = promedio + desviacion*desv
        inferior[i] = promedio - desviacion*desv
    
    return superior, media, inferior


def calcular_atr(highs: List[float], lows: List[float], closes: List[float], periodo: int = 14) -> List[Optional[float]]:
    """🏆 VERSIÓN BACKTEST GANADOR"""
    if len(closes) < periodo+1:
        return [None]*len(closes)
    
    atr = [None]*len(closes)
    true_range = [0.0]*len(closes)
    
    for i in range(1, len(closes)):
        true_range[i] = max(
            highs[i]-lows[i],
            abs(highs[i]-closes[i-1]),
            abs(lows[i]-closes[i-1])
        )
    
    atr[periodo] = sum(true_range[1:periodo+1])/periodo
    
    for i in range(periodo+1, len(closes)):
        if atr[i-1] is not None:
            atr[i] = (atr[i-1]*(periodo-1) + true_range[i])/periodo
    
    return atr


def calcular_macd(precios: Sequence[float]):
    """🏆 VERSIÓN BACKTEST GANADOR"""
    ema_12 = calcular_ema(precios, 12)
    ema_26 = calcular_ema(precios, 26)
    
    macd_line = [None] * len(precios)
    for i in range(len(precios)):
        if ema_12[i] is not None and ema_26[i] is not None:
            macd_line[i] = ema_12[i] - ema_26[i]
    
    signal = calcular_ema([v if v is not None else 0 for v in macd_line], 9)
    
    histogram = [None] * len(precios)
    for i in range(len(precios)):
        if macd_line[i] is not None and signal[i] is not None:
            histogram[i] = macd_line[i] - signal[i]
    
    return macd_line, signal, histogram


def calcular_sma(precios: Sequence[float], periodo: int) -> Serie:
    """SMA simple"""
    if len(precios) < periodo:
        return [None] * len(precios)
    
    resultado = [None] * len(precios)
    suma = sum(precios[:periodo])
    resultado[periodo - 1] = suma / periodo
    
    for i in range(periodo, len(precios)):
        suma += precios[i] - precios[i - periodo]
        resultado[i] = suma / periodo
    
    return resultado


def calcular_adx(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], periodo: int = 14) -> Tuple[Serie, Serie, Serie]:
    """ADX (mantenido por compatibilidad)"""
    n = len(closes)
    adx = [None] * n
    plus_di = [None] * n
    minus_di = [None] * n
    return adx, plus_di, minus_di


def volumen_por_encima_promedio(volumenes: Sequence[float], periodo: int = 20, factor: float = 1.0) -> bool:
    """Volumen sobre promedio (mantenido por compatibilidad)"""
    if len(volumenes) < periodo + 1:
        return False
    promedio = sum(volumenes[-periodo-1:-1]) / periodo
    return volumenes[-1] >= promedio * factor

========== db.py ==========
import json
import math
import os
import threading
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip()
ESTADO_ID = int(os.getenv("BOT_STATE_ID", "1"))
ARCHIVO_ESTADO_LOCAL = os.getenv(
    "BOT_STATE_FILE",
    "/tmp/bnb_bot_estado.json",
)

_DB_LOCK = threading.RLock()
supabase = (
    create_client(SUPABASE_URL, SUPABASE_KEY)
    if SUPABASE_URL and SUPABASE_KEY
    else None
)

DEFAULT_ESTADO: Dict[str, Any] = {
    "en_posicion": False,
    "precio_entrada": 0.0,
    "cantidad": 0.0,
    "precio_maximo": 0.0,
    "timestamp_entrada": None,
    "timestamp_sl": None,
    "ultima_operacion": None,
    "tx_hash_entrada": "",
    "tp1_hecho": False,
    "tx_pending": None,
    "version": 0,
    "gasto_total_usdt": 0.0,
}

def _ahora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _a_float(valor: Any, predeterminado: float = 0.0) -> float:
    try:
        resultado = float(valor if valor is not None else predeterminado)
    except (TypeError, ValueError):
        return predeterminado
    if not math.isfinite(resultado):
        return predeterminado
    return resultado

def _normalizar_pending(valor: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(valor, dict):
        return None

    tipo = str(valor.get("tipo") or "").upper()
    if tipo not in {"COMPRA", "VENTA"}:
        return None

    pending = deepcopy(valor)
    pending["tipo"] = tipo
    pending["hash"] = str(pending.get("hash") or "")
    pending["hashes"] = [
        str(item)
        for item in pending.get("hashes", [])
        if isinstance(item, str)
    ]

    try:
        pending["timestamp"] = float(pending.get("timestamp", 0.0))
    except (TypeError, ValueError):
        pending["timestamp"] = 0.0

    try:
        pending["nonce"] = int(pending["nonce"])
    except (KeyError, TypeError, ValueError):
        pending["nonce"] = None

    return pending

def _normalizar_estado(datos: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    datos = datos or {}
    resultado = deepcopy(DEFAULT_ESTADO)
    resultado.update(
        {
            "en_posicion": bool(datos.get("en_posicion", False)),
            "precio_entrada": max(0.0, _a_float(datos.get("precio_entrada"))),
            "cantidad": max(0.0, _a_float(datos.get("cantidad"))),
            "precio_maximo": max(0.0, _a_float(datos.get("precio_maximo"))),
            "timestamp_entrada": datos.get("timestamp_entrada"),
            "timestamp_sl": datos.get("timestamp_sl"),
            "ultima_operacion": datos.get("ultima_operacion"),
            "tx_hash_entrada": str(datos.get("tx_hash_entrada") or ""),
            "tp1_hecho": bool(datos.get("tp1_hecho", False)),
            "tx_pending": _normalizar_pending(datos.get("tx_pending")),
            "version": max(0, int(datos.get("version", 0) or 0)),
            "gasto_total_usdt": max(0.0, _a_float(datos.get("gasto_total_usdt"))),
        }
    )

    if "historico_valor_pico" in datos:
        resultado["historico_valor_pico"] = max(
            0.0, _a_float(datos.get("historico_valor_pico"))
        )

    if not resultado["en_posicion"]:
        resultado.update(
            {
                "precio_entrada": 0.0,
                "cantidad": 0.0,
                "precio_maximo": 0.0,
                "timestamp_entrada": None,
                "tx_hash_entrada": "",
                "tp1_hecho": False,
            }
        )

    return resultado

def _guardar_local(estado: Dict[str, Any]) -> bool:
    temporal = f"{ARCHIVO_ESTADO_LOCAL}.tmp"
    try:
        directorio = os.path.dirname(ARCHIVO_ESTADO_LOCAL)
        if directorio:
            os.makedirs(directorio, exist_ok=True)

        with open(temporal, "w", encoding="utf-8") as archivo:
            json.dump(estado, archivo, ensure_ascii=False, indent=2)
            archivo.flush()
            os.fsync(archivo.fileno())

        os.replace(temporal, ARCHIVO_ESTADO_LOCAL)
        return True
    except Exception as exc:
        print(f"Error guardando estado local: {exc}", flush=True)
        try:
            if os.path.exists(temporal):
                os.remove(temporal)
        except OSError:
            pass
        return False

def _cargar_local() -> Optional[Dict[str, Any]]:
    try:
        if not os.path.exists(ARCHIVO_ESTADO_LOCAL):
            return None
        with open(ARCHIVO_ESTADO_LOCAL, "r", encoding="utf-8") as archivo:
            contenido = json.load(archivo)
        return _normalizar_estado(contenido)
    except Exception as exc:
        print(f"Error cargando estado local: {exc}", flush=True)
        return None

def _cargar_remoto() -> Optional[Dict[str, Any]]:
    if supabase is None:
        return None

    try:
        respuesta = (
            supabase.table("estado_bot")
            .select("*")
            .eq("id", ESTADO_ID)
            .limit(1)
            .execute()
        )
        filas = respuesta.data or []
        return _normalizar_estado(filas[0]) if filas else None
    except Exception as exc:
        print(f"Error cargando estado remoto: {exc}", flush=True)
        return None

def _version_remota() -> Optional[int]:
    if supabase is None:
        return None
    try:
        respuesta = (
            supabase.table("estado_bot")
            .select("version")
            .eq("id", ESTADO_ID)
            .limit(1)
            .execute()
        )
        filas = respuesta.data or []
        if not filas:
            return None
        return max(0, int(filas[0].get("version", 0) or 0))
    except Exception as exc:
        print(f"Error leyendo versión remota: {exc}", flush=True)
        return None

def cargar_estado() -> Dict[str, Any]:
    with _DB_LOCK:
        remoto = None
        try:
            remoto = _cargar_remoto()
        except Exception as exc:
            print(f"Error cargar_estado Supabase: {exc}", flush=True)

        local = _cargar_local()

        if remoto is not None and local is not None:
            if int(local["version"]) > int(remoto["version"]):
                print(
                    "Aviso: estado local más reciente; se usará para "
                    "recuperación y se intentará resincronizar",
                    flush=True,
                )
                guardar_estado(local, require_remote=False)
                return local

            _guardar_local(remoto)
            return remoto

        if remoto is not None:
            _guardar_local(remoto)
            return remoto

        if local is not None:
            return local

        return deepcopy(DEFAULT_ESTADO)

def guardar_estado(
    estado: Dict[str, Any],
    require_remote: bool = False,
) -> bool:
    with _DB_LOCK:
        actual = _normalizar_estado(estado)
        version_base = int(actual.get("version", 0))
        candidato = deepcopy(actual)
        candidato["version"] = version_base + 1
        candidato["ultima_actualizacion"] = _ahora_iso()

        remoto_ok = False
        local_ok = False

        if supabase is not None:
            try:
                # BUG 4 CORREGIDO: Update condicional con versión
                respuesta = (
                    supabase.table("estado_bot")
                    .update(candidato)
                    .eq("id", ESTADO_ID)
                    .eq("version", version_base)  # <-- SOLO SI NADIE MÁS ESCRIBIÓ
                    .execute()
                )
                remoto_ok = bool(respuesta.data)
                
                # Si no se actualizó (versión distinta), alguien más escribió
                if not remoto_ok:
                    # Intenta insertar si es la primera vez (versión 0)
                    if version_base == 0:
                        respuesta = (
                            supabase.table("estado_bot")
                            .insert({"id": ESTADO_ID, **candidato})
                            .execute()
                        )
                        remoto_ok = bool(respuesta.data)
                    else:
                        # Conflicto de concurrencia: recargar estado fresco
                        print(
                            f"Conflicto de versión: local={version_base}, "
                            "otra instancia actualizó. Reintentando...",
                            flush=True
                        )
                        # Recargar estado y reintentar
                        estado_fresco = cargar_estado()
                        if estado_fresco:
                            estado.update(estado_fresco)
                            return guardar_estado(estado, require_remote)
                        
            except Exception as exc:
                print(f"Error guardar_estado Supabase: {exc}", flush=True)
                if require_remote:
                    local_ok = _guardar_local(candidato)
                    print(
                        "Aviso: copia local escrita como fallback tras error remoto.",
                        flush=True
                    )

        if not (require_remote and not remoto_ok):
            if not local_ok:
                local_ok = _guardar_local(candidato)

        aceptado = remoto_ok if require_remote else (remoto_ok or local_ok)

        if aceptado:
            estado.clear()
            estado.update(candidato)
            return True

        if require_remote and local_ok:
            print(
                "Aviso: copia local escrita, pero la operación se considera "
                "fallida porque Supabase era obligatorio",
                flush=True
            )
        return False

def actualizar_estado_atomicamente(
    cambios: Dict[str, Any],
    require_remote: bool = False,
) -> Optional[Dict[str, Any]]:
    with _DB_LOCK:
        actual = cargar_estado()
        candidato = deepcopy(actual)
        candidato.update(cambios)

        if guardar_estado(candidato, require_remote=require_remote):
            return deepcopy(candidato)
        return None

def registrar_trade(
    tipo: str,
    precio: float,
    cantidad: float,
    rsi: Optional[float],
    motivo: str,
    usdt_valor: float,
    tx_hash: str,
    pnl_pct: Optional[float] = None,
) -> bool:
    if supabase is None:
        print(
            "Supabase no configurado: el trade no pudo persistirse",
            flush=True,
        )
        return False

    datos = {
        "tipo": str(tipo),
        "precio": float(precio),
        "cantidad": float(cantidad),
        "rsi": float(rsi) if rsi is not None else None,
        "motivo": str(motivo),
        "valor_usd": float(usdt_valor),
        "tx_hash": str(tx_hash),
        "pnl_pct": (
            float(pnl_pct) if pnl_pct is not None else None
        ),
        "fecha": _ahora_iso(),
    }

    try:
        respuesta = (
            supabase.table("trades")
            .upsert(datos, on_conflict="tx_hash")
            .execute()
        )
        return bool(respuesta.data)
    except Exception as exc:
        print(f"Error registrar_trade: {exc}", flush=True)
        return False

def contar_perdidas_seguidas(limite: int = 3) -> int:
    if limite <= 0 or supabase is None:
        return 0

    try:
        respuesta = (
            supabase.table("trades")
            .select("pnl_pct,fecha,tipo")
            .like("tipo", "VENTA%")
            .not_.is_("pnl_pct", "null")
            .order("fecha", desc=True)
            .limit(100)
            .execute()
        )

        racha = 0
        for fila in respuesta.data or []:
            tipo = str(fila.get("tipo") or "").upper()
            if not tipo.startswith("VENTA"):
                continue

            pnl = fila.get("pnl_pct")
            if pnl is None:
                continue

            if float(pnl) < 0:
                racha += 1
                if racha >= limite:
                    break
            else:
                break

        return racha
    except Exception as exc:
        print(f"Error contar_perdidas_seguidas: {exc}", flush=True)
        return 0

def obtener_trades_historial(
    limite: int = 1000,
) -> List[Dict[str, Any]]:
    if supabase is None:
        return []

    limite = max(1, min(int(limite), 5000))
    try:
        respuesta = (
            supabase.table("trades")
            .select("*")
            .order("fecha", desc=True)
            .limit(limite)
            .execute()
        )
        return respuesta.data or []
    except Exception as exc:
        print(f"Error obteniendo historial: {exc}", flush=True)
        return []

def obtener_metricas() -> Dict[str, Any]:
    trades = obtener_trades_historial(500)
    cierres = [
        trade
        for trade in trades        if str(trade.get("tipo", "")).upper().startswith("VENTA")
        and trade.get("pnl_pct") is not None
    ]

    if not cierres:
        return {
            "total_trades": len(trades),
            "ventas": 0,
            "win_rate": 0.0,
            "avg_pnl": 0.0,
            "total_pnl": 0.0,
            "max_drawdown": 0.0,
            "wins": 0,
            "losses": 0,
            "last_pnl": 0.0,
        }

    cronologico = list(reversed(cierres))
    pnls = [float(t["pnl_pct"]) for t in cronologico]
    wins = sum(p > 0 for p in pnls)
    losses = sum(p < 0 for p in pnls)
    total = len(pnls)

    acumulado = 0.0
    pico = 0.0
    max_drawdown = 0.0
    for pnl in pnls:
        acumulado += pnl
        pico = max(pico, acumulado)
        max_drawdown = max(max_drawdown, pico - acumulado)

    return {
        "total_trades": len(trades),
        "ventas": total,
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / total * 100.0, 2),
        "avg_pnl": round(sum(pnls) / total, 2),
        "total_pnl": round(sum(pnls), 2),
        "max_drawdown": round(max_drawdown, 2),
        "last_pnl": round(pnls[-1], 2),
    }

def registrar_calidad_ejecucion(
    tx_hash: str,
    tipo: str,
    precio_esperado: float,
    precio_ejecutado: float,
    slippage_real: float,
    twap_referencia: Optional[float],
    gas_usd: float,
    latencia_confirmacion: float,
    liquidez_sesion: str,
) -> bool:
    if supabase is None:
        return False

    datos = {
        "tx_hash": str(tx_hash),
        "tipo": str(tipo),
        "precio_esperado": float(precio_esperado),
        "precio_ejecutado": float(precio_ejecutado),
        "slippage_real_pct": float(slippage_real),
        "twap_referencia": float(twap_referencia) if twap_referencia else None,
        "desviacion_twap_pct": (
            float(abs(precio_ejecutado - twap_referencia) / twap_referencia * 100)
            if twap_referencia and twap_referencia > 0 else None
        ),
        "gas_usd": float(gas_usd),
        "latencia_confirmacion_seg": float(latencia_confirmacion),
        "liquidez_sesion": str(liquidez_sesion),
        "fecha": _ahora_iso(),
    }

    try:
        respuesta = (
            supabase.table("execution_quality")
            .upsert(datos, on_conflict="tx_hash")
            .execute()
        )
        return bool(respuesta.data)
    except Exception as exc:
        print(f"[AVISO] registrar_calidad_ejecucion (no crítico): {exc}", flush=True)
        return False

========== datos_mercado.py ==========
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

import requests

KRAKEN_OHLC_URL = "https://api.kraken.com/0/public/OHLC"
KRAKEN_TICKER_URL = "https://api.kraken.com/0/public/Ticker"
BINANCE_TICKER_URL = "https://api.binance.com/api/v3/ticker/price"
COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "bnb-trading-bot/4.0"})
_CACHE_LOCK = threading.Lock()
_PRECIO_CACHE: Dict[str, Tuple[float, float]] = {}
CACHE_PRECIO_SEGUNDOS = 15

def _extraer_clave_par(resultados: Dict[str, Any]) -> Optional[str]:
    return next((clave for clave in resultados if clave != "last"), None)

def _esperar_reintento(intento: int) -> None:
    time.sleep(min(2 ** intento, 8))

def _get_json(
    url: str,
    params: Dict[str, Any],
    timeout: int = 15,
    reintentos: int = 3,
) -> Optional[Dict[str, Any]]:
    ultimo_error: Optional[Exception] = None

    for intento in range(reintentos):
        try:
            respuesta = _SESSION.get(url, params=params, timeout=timeout)
            respuesta.raise_for_status()
            data = respuesta.json()
            if not isinstance(data, dict):
                raise ValueError("La respuesta JSON no es un objeto")
            return data
        except (requests.RequestException, ValueError) as exc:
            ultimo_error = exc
            if intento < reintentos - 1:
                _esperar_reintento(intento)

    print(
        f"[AVISO] GET falló tras {reintentos} intentos "
        f"({url}): {ultimo_error}",
        flush=True,
    )
    return None

def _request_kraken(
    url: str,
    params: Dict[str, Any],
    timeout: int = 15,
    reintentos: int = 3,
) -> Dict[str, Any]:
    ultimo_error: Optional[Exception] = None

    for intento in range(reintentos):
        try:
            data = _get_json(url, params, timeout, 1)
            if data is None:
                raise RuntimeError("Sin respuesta válida")

            errores = data.get("error") or []
            if errores:
                raise RuntimeError(f"Kraken: {errores}")

            if not isinstance(data.get("result"), dict):
                raise RuntimeError("Respuesta inválida de Kraken")

            return data
        except RuntimeError as exc:
            ultimo_error = exc
            if intento < reintentos - 1:
                _esperar_reintento(intento)

    raise RuntimeError(
        f"No se pudo consultar Kraken tras {reintentos} intentos: "
        f"{ultimo_error}"
    )

def _fila_ohlc_valida(fila: List[Any]) -> bool:
    if len(fila) < 7:
        return False
    try:
        apertura = float(fila[1])
        high = float(fila[2])
        low = float(fila[3])
        close = float(fila[4])
        volumen = float(fila[6])
    except (TypeError, ValueError):
        return False

    valores = (apertura, high, low, close, volumen)
    return (
        all(math.isfinite(v) for v in valores)
        and apertura > 0
        and high > 0
        and low > 0
        and close > 0
        and volumen >= 0
        and high >= max(apertura, close, low)
        and low <= min(apertura, close, high)
    )

def obtener_velas(
    par: str = "BNBUSD",
    intervalo: int = 240,
    cantidad: int = 250,
    excluir_vela_abierta: bool = True,
) -> Optional[Dict[str, List[float]]]:
    if intervalo <= 0:
        raise ValueError("El intervalo debe ser mayor que cero")

    cantidad = max(int(cantidad), 60)
    segundos_intervalo = intervalo * 60
    since = int(time.time() - (cantidad + 10) * segundos_intervalo)

    try:
        data = _request_kraken(
            KRAKEN_OHLC_URL,
            {"pair": par, "interval": intervalo, "since": since},
        )
        resultados = data["result"]
        clave = _extraer_clave_par(resultados)
        if not clave:
            raise RuntimeError(f"Kraken no devolvió velas para {par}")

        ahora = int(time.time())
        filas = []
        for fila in resultados.get(clave) or []:
            if not _fila_ohlc_valida(fila):
                continue

            timestamp = int(float(fila[0]))
            if (
                excluir_vela_abierta
                and timestamp + segundos_intervalo > ahora
            ):
                continue
            filas.append(fila)

        filas.sort(key=lambda item: int(float(item[0])))
        filas = filas[-cantidad:]

        if len(filas) < 60:
            raise RuntimeError(
                f"Velas cerradas insuficientes: {len(filas)}/60"
            )

        return {
            "time": [int(float(f[0])) for f in filas],
            "open": [float(f[1]) for f in filas],
            "high": [float(f[2]) for f in filas],
            "low": [float(f[3]) for f in filas],
            "close": [float(f[4]) for f in filas],
            "volume": [float(f[6]) for f in filas],
        }
    except Exception as exc:
        print(f"[ERROR] Al obtener velas de Kraken: {exc}", flush=True)
        return None

def obtener_velas_multi_temporalidad(
    par: str = "BNBUSD",
    intervalo_4h: int = 240,
    intervalo_1d: int = 1440,
    intervalo_1w: int = 10080,
) -> Dict[str, Optional[Dict[str, List[float]]]]:
    tareas = {
        "4h": (par, intervalo_4h, 250, True),
        "1d": (par, intervalo_1d, 250, True),
        "1w": (par, intervalo_1w, 60, True),
    }

    resultados: Dict[str, Optional[Dict[str, List[float]]]] = {}
    with ThreadPoolExecutor(max_workers=3) as executor:
        futuros = {
            clave: executor.submit(obtener_velas, *argumentos)
            for clave, argumentos in tareas.items()
        }
        for clave, futuro in futuros.items():
            try:
                resultados[clave] = futuro.result()
            except Exception as exc:
                print(f"[ERROR] {clave}: {exc}", flush=True)
                resultados[clave] = None

    return resultados

def obtener_precio_actual(par: str = "BNBUSD") -> Optional[float]:
    try:
        data = _request_kraken(
            KRAKEN_TICKER_URL,
            {"pair": par},
            timeout=10,
        )
        resultados = data["result"]
        clave = _extraer_clave_par(resultados)
        if not clave:
            raise RuntimeError(f"Kraken no devolvió ticker para {par}")

        precio = float(resultados[clave]["c"][0])
        return precio if math.isfinite(precio) and precio > 0 else None
    except Exception as exc:
        print(f"[ERROR] Precio Kraken: {exc}", flush=True)
        return None

def obtener_multiple_pares(pares: List[str]) -> Dict[str, float]:
    pares_limpios = [p.strip() for p in pares if p and p.strip()]
    if not pares_limpios:
        return {}

    try:
        data = _request_kraken(
            KRAKEN_TICKER_URL,
            {"pair": ",".join(pares_limpios)},
            timeout=10,
        )
        precios: Dict[str, float] = {}
        for clave, valor in data["result"].items():
            try:
                precio = float(valor["c"][0])
                if math.isfinite(precio) and precio > 0:
                    precios[clave] = precio
            except (KeyError, TypeError, ValueError, IndexError):
                continue
        return precios
    except Exception as exc:
        print(f"[ERROR] Múltiples pares: {exc}", flush=True)
        return {}

def obtener_precio_binance(par: str = "BNBUSDT") -> Optional[float]:
    data = _get_json(
        BINANCE_TICKER_URL,
        {"symbol": par},
        timeout=10,
    )
    if data is None:
        return None
    try:
        precio = float(data["price"])
        return precio if math.isfinite(precio) and precio > 0 else None
    except (ValueError, KeyError, TypeError):
        return None

def obtener_precio_coingecko() -> Optional[float]:
    data = _get_json(
        COINGECKO_URL,
        {"ids": "binancecoin", "vs_currencies": "usd"},
        timeout=10,
    )
    if data is None:
        return None
    try:
        precio = float(data["binancecoin"]["usd"])
        return precio if math.isfinite(precio) and precio > 0 else None
    except (ValueError, KeyError, TypeError):
        return None

def obtener_precio_coinmarketcap() -> Optional[float]:
    return obtener_precio_coingecko()

def obtener_precio_con_fallback(
    par_kraken: str = "BNBUSD",
    par_binance: str = "BNBUSDT",
) -> Optional[float]:
    cache_key = f"{par_kraken}:{par_binance}"
    ahora = time.monotonic()

    with _CACHE_LOCK:
        cache = _PRECIO_CACHE.get(cache_key)
        if cache and ahora - cache[0] <= CACHE_PRECIO_SEGUNDOS:
            return cache[1]

    proveedores = (
        lambda: obtener_precio_actual(par_kraken),
        lambda: obtener_precio_binance(par_binance),
        obtener_precio_coingecko,
    )

    for proveedor in proveedores:
        precio = proveedor()
        if precio is not None and precio > 0:
            with _CACHE_LOCK:
                _PRECIO_CACHE[cache_key] = (ahora, precio)
            return precio

    print("[ERROR] Todos los proveedores de precios fallaron", flush=True)
    return None

