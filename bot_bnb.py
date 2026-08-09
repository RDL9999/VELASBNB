]633;E;echo "========== main.py ==========";236cd1ad-c02c-41e3-ae3a-61150c33e905]633;C========== main.py ==========
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
# 🚀 BOT FUTUROS SUI v11.0 - DATOS DESDE BINANCE
# ============================================================

# Variables globales
ultimo_ciclo_ts: float = 0.0
ultimo_ciclo_error: Optional[str] = None
ciclos_ejecutados: int = 0
_ultimo_heartbeat: float = 0.0
_bear_alertas: int = 0

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
# OBTENER VELAS DESDE BINANCE (SUI)
# ============================================================
# ============================================================
# OBTENER VELAS Y PRECIOS DESDE GATE.IO (SIN BLOQUEO)
# ============================================================

GATEIO_KLINES_URL = "https://api.gateio.ws/api/v4/spot/candlesticks"
GATEIO_TICKER_URL = "https://api.gateio.ws/api/v4/spot/tickers"
COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"

def obtener_velas_gateio(symbol: str = "SUI_USDT", interval: str = "4h", limit: int = 250) -> Optional[Dict[str, List[float]]]:
    """Obtiene velas desde Gate.io (sin bloqueo geográfico)"""
    try:
        params = {
            "currency_pair": symbol,
            "interval": interval,
            "limit": limit
        }
        resp = requests.get(GATEIO_KLINES_URL, params=params, timeout=15)
        
        print(f"[DEBUG] Gate.io status: {resp.status_code}")
        
        data = resp.json()
        
        if not isinstance(data, list) or len(data) < 60:
            print(f"[ERROR] Gate.io: datos insuficientes ({len(data) if isinstance(data, list) else type(data)})")
            return None
        
        resultado = {
            "time": [],
            "open": [],
            "high": [],
            "low": [],
            "close": [],
            "volume": []
        }
        
        for vela in data:
            try:
                # Gate.io: [timestamp, volume, close, high, low, open, amount]
                resultado["time"].append(int(float(vela[0])))
                resultado["open"].append(float(vela[5]))
                resultado["high"].append(float(vela[3]))
                resultado["low"].append(float(vela[4]))
                resultado["close"].append(float(vela[2]))
                resultado["volume"].append(float(vela[1]))
            except (IndexError, ValueError, TypeError):
                continue
        
        # Ordenar por tiempo
        idx = sorted(range(len(resultado["time"])), key=lambda i: resultado["time"][i])
        for key in resultado:
            resultado[key] = [resultado[key][i] for i in idx]
        
        print(f"[DEBUG] Velas parseadas: {len(resultado['close'])}")
        return resultado if len(resultado["close"]) >= 60 else None
        
    except Exception as e:
        print(f"[ERROR] obtener_velas_gateio: {e}")
        traceback.print_exc()
        return None

def obtener_precio_sui_gateio() -> Optional[float]:
    """Obtiene precio actual de SUI desde Gate.io"""
    try:
        params = {"currency_pair": "SUI_USDT"}
        resp = requests.get(GATEIO_TICKER_URL, params=params, timeout=10)
        data = resp.json()
        
        if isinstance(data, list) and len(data) > 0:
            precio = float(data[0]["last"])
            return precio if precio > 0 else None
        return None
    except Exception as e:
        print(f"[ERROR] Precio SUI Gate.io: {e}")
        return None

def obtener_precio_sui_coingecko() -> Optional[float]:
    """Obtiene precio de SUI desde CoinGecko (fallback)"""
    try:
        resp = requests.get(COINGECKO_URL, params={"ids": "sui", "vs_currencies": "usd"}, timeout=10)
        data = resp.json()
        precio = float(data["sui"]["usd"])
        return precio if precio > 0 else None
    except Exception:
        return None

def obtener_precio_sui() -> Optional[float]:
    """Precio SUI con fallback: Gate.io → CoinGecko"""
    precio = obtener_precio_sui_gateio()
    if precio:
        return precio
    return obtener_precio_sui_coingecko()
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
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": mensaje, "parse_mode": "HTML"},
            timeout=10,
        )
        if resp.status_code != 200:
            print(f"[AVISO] Telegram: HTTP {resp.status_code}")
    except Exception as exc:
        print(f"[AVISO] Telegram: {exc}")

def notificar(mensaje: str) -> None:
    print(f"\n{Colores.BOLD}{Colores.CYAN}[NOTIFICACION]{Colores.RESET} {mensaje}")
    notificar_telegram(mensaje)

def notificar_compra(cantidad: float, precio: float, usdt_gastado: float, tx_hash: str = "", motivo: str = "") -> None:
    msg = (
        f"🟢 <b>COMPRA SUI - BOT FUTUROS v11.0</b> 🟢\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"💰 Cantidad: <b>{cantidad:.4f} SUI</b>\n"
        f"💵 Precio: <b>${precio:,.4f}</b>\n"
        f"💲 Total: <b>${usdt_gastado:,.2f}</b>\n"
        f"📝 Motivo: {_esc(motivo)}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🕐 {_timestamp_utc()}"
    )
    if tx_hash:
        msg += f"\n🔗 <a href='https://suiscan.xyz/tx/{tx_hash}'>Ver en SuiScan</a>"
    notificar(msg)
    notificar_discord(msg)

def notificar_venta(cantidad: float, precio: float, usdt_recibido: float, pnl: float, motivo: str = "", tx_hash: str = "") -> None:
    emoji = "🟢" if pnl >= 0 else "🔴"
    pnl_str = f"+{pnl:.2f}%" if pnl >= 0 else f"{pnl:.2f}%"
    msg = (
        f"{emoji} <b>VENTA SUI - BOT FUTUROS v11.0</b> {emoji}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"💰 Cantidad: <b>{cantidad:.4f} SUI</b>\n"
        f"💵 Precio: <b>${precio:,.4f}</b>\n"
        f"💲 USDT: <b>${usdt_recibido:,.2f}</b>\n"
        f"📊 PnL: <b>{pnl_str}</b>\n"
        f"📝 Motivo: {_esc(motivo)}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🕐 {_timestamp_utc()}"
    )
    if tx_hash:
        msg += f"\n🔗 <a href='https://suiscan.xyz/tx/{tx_hash}'>Ver en SuiScan</a>"
    notificar(msg)
    notificar_discord(msg)

def notificar_inicio() -> None:
    msg = (
        f"🤖 <b>BOT FUTUROS SUI v11.0</b> 🤖\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🧠 Estrategia: Suelos reales + Techos reales (v11.0)\n"
        f"📊 RSI {RSI_MAX_COMPRA} | Toma +{TOMA_PCT}%/{CAIDA_PCT}%\n"
        f"📡 Datos: Gate.io API (SUI/USDT)\n"
        f"⚡ Modo: Compra directa | Sin Anti-Euforia\n"
        f"🕐 Inicio: {_timestamp_utc()}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"✅ Bot iniciado correctamente"
    )
    notificar(msg)

def notificar_error(mensaje: str) -> None:
    msg = (
        f"⚠️ <b>ERROR EN BOT SUI</b> ⚠️\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📝 {_esc(mensaje)}\n"
        f"🕐 {_timestamp_utc()}"
    )
    notificar(msg)
    notificar_discord(msg)

def notificar_heartbeat() -> None:
    global _ultimo_heartbeat
    ahora = time.time()
    if ahora - _ultimo_heartbeat < 86400:
        return
    _ultimo_heartbeat = ahora
    with STATE_LOCK:
        en_pos = estado.get("en_posicion", False)
    msg = (
        f"💓 <b>BOT FUTUROS SUI - REPORTE DIARIO</b> 💓\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"✅ Bot operativo\n"
        f"📊 Posición: {'🟢 ABIERTA' if en_pos else '⚪ Sin posición'}\n"
        f"🔄 Ciclos ejecutados: {ciclos_ejecutados}\n"
        f"📡 Datos: Gate.io SUI/USDT\n"
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
                f"🐻 <b>BEAR MARKET PROLONGADO - SUI</b> 🐻\n"
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
# PARÁMETROS DE LA ESTRATEGIA v11.0 SUI
# ============================================================
RSI_MAX_COMPRA = env_float("RSI_MAX_COMPRA", 77.0)
TOMA_PCT = env_float("TOMA_PCT", 24.6)
CAIDA_PCT = env_float("CAIDA_PCT", 6.6)
TECHO_MIN = 9.0

ESCANEO = max(env_int("ESCANEO", 900), 30)
CANDLE_INTERVAL = 240  # 4H fijo para SUI

DRY_RUN = env_bool("DRY_RUN", True)
REQUIRE_DB = env_bool("REQUIRE_DB", True)
STATUS_TOKEN = os.getenv("STATUS_TOKEN", "").strip()

# ============================================================
# VARIABLES DE ENTORNO
# ============================================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT_ID", "").strip()
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip()

if REQUIRE_DB and (not SUPABASE_URL or not SUPABASE_KEY):
    raise RuntimeError("Faltan SUPABASE_URL o SUPABASE_KEY")

STATE_LOCK = threading.RLock()

# Estado simulado (no hay blockchain real en DRY_RUN)
estado = cargar_estado()

# ============================================================
# FUNCIONES DE ESTADO (SIMULADO)
# ============================================================

def persistir_estado_bajo_lock() -> None:
    if not guardar_estado(estado, require_remote=REQUIRE_DB):
        raise RuntimeError("No se pudo persistir el estado")

def _cerrar_estado() -> None:
    estado.update({
        "en_posicion": False, "precio_entrada": 0.0, "cantidad": 0.0,
        "precio_maximo": 0.0, "timestamp_entrada": None, "tx_hash_entrada": "",
        "ganancia_max_pct": 0.0, "velas_en_posicion": 0, "atr_inicial": 0.0,
        "suelo_compra": 0.0,
    })

# ============================================================
# COMPRA SIMULADA
# ============================================================

def comprar_simulado(cantidad_usdt: float, motivo: str = "", suelo: float = 0.0, rsi: float = 0.0, atr_inicial: float = 0.0, precio_actual: float = 0.0) -> bool:
    """Simula una compra (DRY_RUN)"""
    with STATE_LOCK:
        if estado.get("en_posicion") or estado.get("tx_pending"):
            return False
        
        cantidad_sui = (cantidad_usdt * 0.95) / (precio_actual * 1.002)
        precio_entrada = precio_actual * 1.002
        
        estado.update({
            "en_posicion": True, "precio_entrada": precio_entrada,
            "precio_maximo": precio_entrada, "cantidad": cantidad_sui,
            "timestamp_entrada": datetime.now(timezone.utc).isoformat(),
            "ultima_operacion": "COMPRA_SIMULADA", "tx_hash_entrada": "0xSIMULADO",
            "ganancia_max_pct": 0.0, "velas_en_posicion": 0,
            "atr_inicial": atr_inicial, "suelo_compra": suelo,
        })
        persistir_estado_bajo_lock()
    
    print(f"\n{'🟢' * 40}")
    print(f"{Colores.BOLD}{Colores.FONDO_VERDE} {Colores.BLANCO}COMPRA SIMULADA (DRY RUN){Colores.RESET}")
    print(f"{'🟢' * 40}")
    print(f"  💰 Cantidad : {_formatear_bnb(cantidad_sui, 4)} SUI")
    print(f"  💵 Precio   : {_formatear_usd(precio_entrada)}")
    print(f"  💲 Total    : {_formatear_usd(cantidad_usdt)} USDT")
    print(f"  📝 Motivo   : {motivo}")
    print(f"{'🟢' * 40}")
    notificar_compra(cantidad_sui, precio_entrada, cantidad_usdt, "SIMULADO", motivo)
    return True

def vender_simulado(motivo: str = "", precio_actual: float = 0.0) -> bool:
    """Simula una venta (DRY_RUN)"""
    with STATE_LOCK:
        if not estado.get("en_posicion") or estado.get("tx_pending"):
            return False
        
        cantidad = float(estado.get("cantidad", 0.0))
        precio_entrada = float(estado.get("precio_entrada", 0.0))
        
        precio_salida = precio_actual * 0.998
        usdt_recibido = cantidad * precio_salida * 0.997
        pnl = (precio_salida - precio_entrada) / precio_entrada * 100
        
        _cerrar_estado()
        estado["ultima_operacion"] = "VENTA_SIMULADA"
        estado["tx_pending"] = None
        persistir_estado_bajo_lock()
    
    emoji = "🔴" if pnl < 0 else "🟢"
    print(f"\n{emoji * 40}")
    print(f"{Colores.BOLD}{Colores.FONDO_ROJO if pnl < 0 else Colores.FONDO_VERDE} {Colores.BLANCO}VENTA SIMULADA (DRY RUN){Colores.RESET}")
    print(f"{emoji * 40}")
    print(f"  💰 Cantidad : {_formatear_bnb(cantidad, 4)} SUI")
    print(f"  💵 Precio   : {_formatear_usd(precio_salida)}")
    print(f"  💲 USDT     : {_formatear_usd(usdt_recibido)}")
    print(f"  📊 PnL      : {_color_pnl(pnl)}")
    print(f"  📝 Motivo   : {motivo}")
    print(f"{emoji * 40}")
    notificar_venta(cantidad, precio_salida, usdt_recibido, pnl, motivo, "SIMULADO")
    return True

# ============================================================
# CICLO PRINCIPAL - ESTRATEGIA v11.0 SUI
# ============================================================

def ejecutar_ciclo() -> None:
    global ultimo_ciclo_ts, ultimo_ciclo_error, ciclos_ejecutados
    
    detector_suelos = DetectorSuelosReales(ventana=48, toques_minimos=2)
    detector_techos = DetectorTechosReales()
    
    print(f"\n{Colores.BOLD}{Colores.CYAN}══{'═' * 78}{Colores.RESET}")
    print(f"{Colores.BOLD}{Colores.CYAN}[BOT FUTUROS SUI v11.0]{Colores.RESET} | {_timestamp_utc()}")
    print(f"{Colores.BOLD}{Colores.CYAN}══{'═' * 78}{Colores.RESET}")
    
    # Obtener velas SUI desde Binance
    velas_4h = obtener_velas_gateio("SUI_USDT", "4h", 250)
    
    if not velas_4h or not velas_4h.get("close") or len(velas_4h["close"]) < 48:
        print(f"\n{Colores.AMARILLO}[VELAS]{Colores.RESET} Sin datos suficientes de SUI, saltando ciclo")
        ultimo_ciclo_ts = time.time()
        ultimo_ciclo_error = None
        ciclos_ejecutados += 1
        return
    
    # Obtener precio actual
    precio = obtener_precio_sui()
    
    if precio is None or precio <= 0:
        print(f"\n{Colores.ROJO}[ERROR]{Colores.RESET} No se pudo obtener precio de SUI")
        ultimo_ciclo_ts = time.time()
        ultimo_ciclo_error = "No se pudo obtener precio SUI"
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
    
    ema_50_arr = calcular_ema(closes_hist, 50)
    ema_200_arr = calcular_ema(closes_hist, 200)
    
    ema_50 = ema_50_arr[-1] if ema_50_arr[-1] is not None else precio
    ema_200 = ema_200_arr[-1] if ema_200_arr[-1] is not None else precio
    
    print(f"\n{Colores.BOLD}{Colores.AZUL}[INDICADORES SUI 4H]{Colores.RESET}")
    print(f"  {Colores.DIM}Velas disponibles{Colores.RESET} : {len(closes_hist)}")
    print(f"  {Colores.DIM}RSI (14){Colores.RESET}         : {rsi_actual:.1f} (umbral: ≤{RSI_MAX_COMPRA})")
    print(f"  {Colores.DIM}ATR (14){Colores.RESET}         : {atr_actual:.4f} ({atr_actual/precio*100:.2f}%)")
    print(f"  {Colores.DIM}EMA 50{Colores.RESET}           : {_formatear_usd(ema_50)}")
    print(f"  {Colores.DIM}EMA 200{Colores.RESET}          : {_formatear_usd(ema_200)}")
    print(f"  {Colores.DIM}PRECIO SUI{Colores.RESET}       : {_formatear_usd(precio)}")
    
    # Saldo simulado (USDT virtual)
    saldo_usdt = 1000.0  # Capital inicial simulado
    print(f"\n{Colores.BOLD}{Colores.CYAN}[SALDOS SIMULADOS]{Colores.RESET}")
    print(f"  {Colores.DIM}USDT (virtual){Colores.RESET}    : {_formatear_usd(saldo_usdt)}")
    print(f"  {Colores.DIM}Modo{Colores.RESET}              : {'🟡 DRY RUN (simulación)' if DRY_RUN else '🟢 REAL'}")
    
    notificar_heartbeat()
    
    with STATE_LOCK:
        en_posicion = bool(estado.get("en_posicion"))
        entrada = float(estado.get("precio_entrada", 0.0))
        cantidad = float(estado.get("cantidad", 0.0))
        ganancia_max = float(estado.get("ganancia_max_pct", 0.0))
        velas_en_pos = int(estado.get("velas_en_posicion", 0))
        atr_inicial = float(estado.get("atr_inicial", 0.0))
    
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
        print(f"  {Colores.DIM}RSI Actual{Colores.RESET}       : {rsi_actual:.1f}")
    else:
        print(f"  {Colores.DIM}Estado{Colores.RESET}           : {razon}")
    
    if not en_posicion:
        print(f"\n{Colores.BOLD}{Colores.AZUL}[ESTRATEGIA v11.0]{Colores.RESET} Modo: Buscando entrada (COMPRA DIRECTA)")
        
        if bear:
            print(f"  {Colores.ROJO}⛔ Bear Market - Sin compras{Colores.RESET}")
        elif crash:
            print(f"  {Colores.ROJO}⛔ Crash Reciente - Sin compras{Colores.RESET}")
        elif tend_bajista:
            print(f"  {Colores.ROJO}⛔ Tendencia Bajista - Sin compras{Colores.RESET}")
        elif not es_suelo:
            print(f"  {Colores.DIM}Sin suelo válido{Colores.RESET}")
        elif rsi_actual > RSI_MAX_COMPRA:
            print(f"  {Colores.AMARILLO}⏳ RSI {rsi_actual:.1f} > {RSI_MAX_COMPRA}{Colores.RESET}")
        elif closes_hist[-1] <= opens_hist[-1]:
            print(f"  {Colores.AMARILLO}⏳ Vela roja{Colores.RESET}")
        else:
            # 🚀 COMPRA DIRECTA
            print(f"\n  {Colores.VERDE}🚀 ¡SEÑAL DE COMPRA SUI! (Compra directa v11.0){Colores.RESET}")
            print(f"  {Colores.DIM}Suelo{Colores.RESET}             : {_formatear_usd(precio_suelo)}")
            print(f"  {Colores.DIM}RSI{Colores.RESET}               : {rsi_actual:.1f}")
            print(f"  {Colores.DIM}Precio Entrada{Colores.RESET}    : {_formatear_usd(closes_hist[-1])}")
            
            monto = saldo_usdt * 0.95
            comprar_simulado(monto, razon, precio_suelo, rsi_actual, atr_actual, closes_hist[-1])
        
        ultimo_ciclo_ts = time.time()
        ultimo_ciclo_error = None
        ciclos_ejecutados += 1
        return
    
    # ============================================================
    # EN POSICIÓN - EVALUAR VENTA
    # ============================================================
    
    if entrada <= 0:
        ultimo_ciclo_ts = time.time()
        ultimo_ciclo_error = None
        ciclos_ejecutados += 1
        return
    
    ganancia_pct = (precio - entrada) / entrada * 100
    drawdown = (entrada - precio) / entrada * 100
    
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
    print(f"  {Colores.DIM}PnL Actual{Colores.RESET}        : {_color_pnl(ganancia_pct)}")
    print(f"  {Colores.DIM}Máximo{Colores.RESET}            : +{ganancia_max:.1f}%")
    print(f"  {Colores.DIM}Velas{Colores.RESET}             : {velas_en_pos}")
    
    motivo_venta = None
    
    # 1. TOMA
    if ganancia_max >= TOMA_PCT:
        caida = (nuevo_max - precio) / nuevo_max * 100
        if caida >= CAIDA_PCT:
            motivo_venta = f"💎 TOMA +{ganancia_max:.1f}% | Caída -{caida:.1f}%"
    
    # 2. TECHO
    elif ganancia_pct >= TECHO_MIN:
        es_techo, razon_techo = detector_techos.es_techo_real(
            closes_hist, opens_hist, highs_hist, entrada, atr_actual
        )
        if es_techo:
            motivo_venta = f"🏔️ TECHO | {razon_techo} | Gan +{ganancia_pct:.2f}%"
    
    # 3. PÁNICO
    elif velas_en_pos >= 20 and atr_inicial > 0:
        if atr_actual > atr_inicial * 3.0 and ganancia_pct < -10.0:
            motivo_venta = f"🚨 PÁNICO | ATR x{atr_actual/atr_inicial:.1f}"
    
    # 4. TIME STOP
    elif velas_en_pos >= 2599:
        motivo_venta = f"⏰ TIME STOP {velas_en_pos}v"
    
    # 5. STOP LOSS
    elif drawdown >= 90.0:
        motivo_venta = f"🛑 STOP LOSS -{drawdown:.1f}%"
    
    if motivo_venta:
        print(f"\n{Colores.BOLD}{Colores.VERDE}[VENTA]{Colores.RESET} {motivo_venta}")
        vender_simulado(motivo_venta, precio)
    else:
        print(f"\n{Colores.DIM}[ESTADO]{Colores.RESET} Sin señales de venta")
    
    ultimo_ciclo_ts = time.time()
    ultimo_ciclo_error = None
    ciclos_ejecutados += 1

# ============================================================
# FLASK
# ============================================================

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot Futuros SUI v11.0 (DRY RUN)", 200

@app.route("/status")
def status():
    if not STATUS_TOKEN:
        return jsonify({"error": "STATUS_TOKEN no configurado"}), 503
    cabecera = request.headers.get("Authorization", "").strip()
    recibido = cabecera[7:].strip() if cabecera.lower().startswith("bearer ") else cabecera
    if not hmac.compare_digest(recibido, STATUS_TOKEN):
        return jsonify({"error": "unauthorized"}), 401
    
    ahora = datetime.now(timezone.utc)
    tiempo_desde = (ahora.timestamp() - ultimo_ciclo_ts) if ultimo_ciclo_ts > 0 else None
    
    with STATE_LOCK:
        copia = {
            "en_posicion": estado.get("en_posicion"),
            "cantidad": estado.get("cantidad"),
            "precio_entrada": estado.get("precio_entrada"),
            "ganancia_max_pct": estado.get("ganancia_max_pct"),
        }
    
    return jsonify({
        "status": "healthy" if not ultimo_ciclo_error else "warning",
        "dry_run": DRY_RUN,
        "moneda": "SUI",
        "timestamp": ahora.isoformat(),
        "ciclos_ejecutados": ciclos_ejecutados,
        "ultimo_ciclo_hace_segundos": round(tiempo_desde, 1) if tiempo_desde else None,
        "ultimo_error": ultimo_ciclo_error,
        **copia,
    })

def _run_flask() -> None:
    puerto = env_int("PORT", 8080)
    app.run(host="0.0.0.0", port=puerto, use_reloader=False, threaded=True)

# ============================================================
# MAIN
# ============================================================

def main() -> None:
    global ultimo_ciclo_ts, ultimo_ciclo_error, ciclos_ejecutados
    
    threading.Thread(target=_run_flask, daemon=True).start()
    
    notificar_inicio()
    print(f"\n{Colores.BOLD}{Colores.CYAN}{'=' * 80}{Colores.RESET}")
    print(f"{Colores.BOLD}{Colores.CYAN}  BOT FUTUROS SUI v11.0 - ESTRATEGIA BACKTEST{Colores.RESET}")
    print(f"{Colores.BOLD}{Colores.CYAN}  📡 Datos: Gate.io API (SUI/USDT 4H){Colores.RESET}")
    print(f"{Colores.BOLD}{Colores.CYAN}  RSI {RSI_MAX_COMPRA} | Toma +{TOMA_PCT}%/{CAIDA_PCT}% | Techo {TECHO_MIN}%{Colores.RESET}")
    print(f"{Colores.BOLD}{Colores.CYAN}  ⚡ Compra directa | Sin Anti-Euforia | DRY RUN{Colores.RESET}")
    print(f"{Colores.BOLD}{Colores.CYAN}{'=' * 80}{Colores.RESET}")
    
    while True:
        inicio = time.monotonic()
        try:
            ejecutar_ciclo()
        except KeyboardInterrupt:
            print(f"\n{Colores.AMARILLO}[AVISO]{Colores.RESET} Bot detenido")
            break
        except Exception as exc:
            print(f"{Colores.ROJO}[ERROR]{Colores.RESET} CICLO: {type(exc).__name__}: {exc}")
            traceback.print_exc()
            notificar_error(f"Error: {exc}")
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
# ESTRATEGIA v11.0 - BOT FUTUROS
# 🐻 Bear Market ESTRICTO | 📊 Volumen promedio 20 velas
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

        # 🆕 Volumen promedio 20 velas (v11.0)
        if len(volumes) >= 20:
            vol_promedio = sum(volumes[-20:]) / 20
            if volumes[-1] < vol_promedio:
                return False, suelo_real, distancia_pct, "Volumen bajo"

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
# FILTROS DE MERCADO (v11.0 - ESTRICTOS)
# ============================================================

def esta_en_bear_market(closes: List[float]) -> bool:
    """
    🐻 VERSIÓN BACKTEST v11.0 (ESTRICTO):
    Bloquea si EMA50 < EMA200 Y precio < EMA200
    O si precio < 85% del EMA200
    """
    if len(closes) < 200:
        return False
    
    ema_50 = calcular_ema(closes, 50)
    ema_200 = calcular_ema(closes, 200)
    
    if ema_50[-1] is None or ema_200[-1] is None:
        return False
    
    precio = closes[-1]
    
    # Condición 1: EMA50 < EMA200 Y precio debajo de EMA200
    if ema_50[-1] < ema_200[-1] and precio < ema_200[-1]:
        return True
    
    # Condición 2: Precio muy por debajo de EMA200 (bear severo)
    if ema_200[-1] > 0 and precio < ema_200[-1] * 0.85:
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

