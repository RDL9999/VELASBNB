# GUÍA MASTERCLASS DE AIRDROP FARMING
## Metodología validada el 2026-08-10 (parte del paquete digital vendible)

---

## 1. PRINCIPIOS BÁSICOS

1. **Solo farming de campañas CONFIRMADAS.** Airdrops "potenciales" = lotería.
   Confirmado = el proyecto anunció oficialmente distribución y tiene TGE.
2. **El multiplicador más importante es la CONSISTENCIA (streak).** La mayoría
   de programas (ej. Orbinum) dan hasta 1.5x por racha semanal. Perder un día
   cuesta más que un día extra de farmeo.
3. **Snapshot > TGE.** La elegibilidad se fija en el snapshot (a menudo 14 días
   ANTES del TGE). Actividad después del snapshot no cuenta.
4. **Anti-sybil:** no uses una sola IP/huella para muchas wallets "hermanas".
   Los proyectos filtran sybils y eliminan todo el clúster.
5. **Los socials vinculados multiplican.** Discord + Telegram + X verificados
   casi siempre dan bonus de signup (ej. Orbinum: 20 créditos).

## 2. DÓNDE ENCONTRAR CAMPAÑAS CONFIRMADAS

- airdrops.io/latest y /confirmed
- DefiLlama → sección "Airdrops" (tokenless protocols)
- Cuentas oficiales X de las L1s/L2s nuevas
- Twitter: buscar "confirmed airdrop" + "testnet"

## 3. KIT DE HERRAMIENTAS

- Wallets: MetaMask/Rabby (EVM), Phantom/Solflare (Solana), Substrate wallets
- Redes testnet: agregar manualmente (chain ID + RPC) — casi siempre gratis
- Faucets: del proyecto (nunca pagues por testnet tokens)
- Scripts: python3 con requests (ver orbinum_farm_kit.py)

## 4. PLAN DIARIO ÓPTIMO (30-40 min)

| Tiempo | Acción |
|--------|--------|
| 0-5 min | Check-in diario en todos los dashboards (claims diarios) |
| 5-15 min | Quest on-chain #1 (shield/mint) |
| 15-25 min | Quest on-chain #2 (transfer) |
| 25-35 min | Quest on-chain #3 (unshield/withdraw) |
| 35-40 min | Quests off-chain (follows, quizzes, referidos) |

## 5. HOJA DE SEGUIMIENTO (semanal)

```
Proyecto: ______   Snapshot: ______   TGE: ______
Semana | L | M | X | J | V | S | D | Streak | Créditos
  1    |   |   |   |   |   |   |   |   0    |   0
  2    |   |   |   |   |   |   |   |   0    |   0
```

## 6. ERRORES QUE EVITAR

- Conectar wallet a sitios NO oficiales (drainers). NUNCA dar seed phrase.
- Usar la misma wallet "quemada" para todo sin mantener streaks.
- Pagar por "testnet tokens" — siempre son gratis del faucet.
- Ignorar el snapshot y seguir farmeando después (trabajo perdido).

## 7. CASO DE ESTUDIO VALIDADO HOY: ORBINUM

- Chain: Substrate/EVM testnet, chain ID 2700, RPC rpc-1.testnet.orbinum.io
- Airdrop confirmado: 20M ORB (2% supply), Season 1 "Genesis Community"
- TGE: Q4 2026. Snapshot: 14 días antes de mainnet.
- Quests: shield / private transfer / unshield / selective disclosure (diarias)
- Bonus: 20 créditos por vincular Discord+TG+X; 10 créditos por referido verificado
- Streak semanal: hasta 1.5x en quest rewards
- Script de verificación incluido (probado: RPC responde, bloque 361,745+)

## 8. CÓMO VENDER ESTA GUÍA

1. Publica en Fiverr como GIG digital ($5-$30, ver gigs_fiverr.md)
2. Gumroad/Lemonsqueezy para venta directa
3. Personaliza el caso de estudio a un cliente nuevo → entrega "setup + guía"
