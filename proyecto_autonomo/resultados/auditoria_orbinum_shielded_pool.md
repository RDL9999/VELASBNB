# ADVISORY DE SEGURIDAD — Orbinum Shielded Pool (pre-mainnet/testnet)

Fecha: 2026-08-10
Analista: agente autónomo (RDL9999)
Estado: VERIFICADO por lectura de código (no explotado en red)

## RESUMEN

Hallazgo **CRITICAL**: la operación `shield` no vincula criptográficamente el valor
de la nota privada (`note_value`) con el monto depositado (`amount`). Un atacante
puede acuñar una nota que codifica un valor arbitrario (hasta u64::MAX) depositando
una cantidad mínima, y luego `unshield` para extraer el balance total del pool —
incluyendo los fondos de otros usuarios.

## UBICACIÓN

- `frame/shielded-pool/src/operations/shield.rs:39-48` — `ShieldOperation::execute`
- `frame/shielded-pool/src/operations/unshield.rs` — `UnshieldOperation::execute`
- `primitives/zk-circuits/src/circuits/unshield.rs:276-311` — constraints del circuito

## DETALLE TÉCNICO

El commitment de una nota es `C = Poseidon4(note_value, asset_id, owner_pk, blinding)`
(`types/ids.rs:20`). El circuito `unshield` verifica:

1. `C == Poseidon4(note_value, asset_id, owner_pk, blinding)` (commitment correctness)
2. Merkle membership: `C` está en el árbol
3. Nullifier: `Poseidon2(C, spending_key) == nullifier`
4. Balance: `note_value == amount + fee`

`note_value` es un *witness privado* — el que gasta lo elige libremente. En `shield`
**no hay prueba alguna** que fuerce `note_value == amount_depositado`. El único guard
en `unshield` contra drenaje es `PoolBalancePerAsset >= amount + fee` (unshield.rs:104-108),
que comprueba contra el balance *total del pool* (fondos de todos los usuarios).

El propio equipo documentó la amenaza y la mitigó SOLO en `claim_shielded_fees`
con un `value_proof` (fees.rs:25: "Without this proof a relayer could craft a
commitment encoding an inflated amount and drain the pool on `unshield`"), pero la
misma protección NO existe en `shield`, que es el camino por donde cualquier usuario
crea notas.

## ESCENARIO DE ATAQUE (paso a paso)

1. Ataque A genera `owner_pk`, `blinding`, y elige `V = u64::MAX`.
2. A calcula `C = Poseidon4(V, asset_id, owner_pk, blinding)` y el nullifier.
3. A llama `shield(asset_id, amount=1, commitment=C, memo)`. El pool recibe **1** unidad.
   El ledger `PoolBalancePerAsset[asset_id]` queda en 1. `C` entra al árbol.
4. Usuarios honestos depositan fondos. El pool físico y el ledger crecen a `T`.
5. A llama `unshield(proof, root_actual, nullifier, asset_id, amount=T, recipient=A, fee=0, change_commitment=C2, ...)`.
   - El proof es **genuinamente válido**: C está en el árbol, el nullifier deriva del
     preimagen que A conoce, y `note_value(V) == amount(T) + fee(0)` se satisface.
   - El guard `PoolBalance >= T` pasa porque el pool contiene los fondos de B.
6. El pool transfiere `T` a A. A repite hasta vaciar el pool.

El ataque es dinámico: con *partial unshield* (dejando `change_commitment`) el atacante
puede drenar incrementalmente cualquier balance del pool sin necesidad de predecirlo.

## SEVERIDAD

**Critical.** Drenaje completo del pool. Requiere corregir antes de mainnet.
En testnet con verificación real activa (no `skip-proof-verification`), el ataque
es criptográficamente válido end-to-end.

## MITIGACIÓN RECOMENDADA

1. Requerir un `value_proof` (circuito "value_proof") en `shield` que pruebe que
   el commitment codifica exactamente `(amount, asset_id)` — igual que ya se hace
   en `claim_shielded_fees`.
2. Alternativa: denominaciones fijas/limitadas en el circuito, o que el circuito
   `unshield` fuerce `note_value` dentro de un rango acotado por denominación.
3. Agregar test de integración: shield con commitment de valor grande + unshield
   por encima del monto depositado debe fallar con `InsufficientPoolBalance`.

## HALLAZGOS SECUNDARIOS

### MEDIUM — Crecimiento no acotado de la cola de raíces históricas (DoS de almacenamiento)
`merkle/service.rs:168-194`: cuando `head - tail >= MaxHistoricRoots` y el slot del
tail está aún vivo, se re-encola con su expiry original y se avanza `head` dos veces
por insert → la cola crece +1 por insert mientras la rama se dispare. El drain loop
hace `break` en el primer slot vivo, así que los slots re-encolados no se limpian
hasta que expiren todos los precedentes. Condicional a alcanzar el cap
(`MaxHistoricRoots=16384`, requiere >55 inserts/bloque sostenidos).

### LOW — `validate_unshield` admite `amount == 0`
`validate_unsigned/unshield.rs`: no valida `amount != 0` (el extrinsic sí). Spam de
transacciones gratis que fallan en ejecución. DoS menor.

### INFORMATIONAL — `circuit_version` no está ligado a la nota
La versión de circuito es elegida por el submitter en cada gasto
(`zk-verifier/src/lib.rs:277-288`). Si una versión antigua tuviera un bug, los fondos
de las notas de esa versión siguen en riesgo hasta que governance llame `retire_version`.
`remove_verification_key` de una versión en uso congelaría permanentemente esas notas.

## NOTA SOBRE EL CÓDIGO RESTANTE

El resto del protocolo es sólido y bien testeado:
- Reutilización de nullifiers correcta, con `provides` tags (nullifier+relayer) sin replay.
- Árboles sellados permanentes; raíces históricas con ventana de expiración por bloques.
- Ledger `PoolBalancePerAsset` vs balance físico con `try_state`.
- Atribución de fees solo a relayers registrados o block author.
- Precompile EVM con mapeo de caller correcto.

## CONTACTO DE REPORTE

Según `SECURITY.md` del repo: medium/high → security@bitarray.dev.
Orbinum mantiene además un programa de airdrop testnet (confirmado, TGE Q4 2026).
No se ha confirmado programa público de recompensas; se recomienda contactar al equipo
directamente antes de mainnet (Q4 2026) — es exactamente el tipo de hallazgo que
evita un desastre de launch.
