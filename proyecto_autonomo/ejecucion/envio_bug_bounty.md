# PAQUETE DE ENVÍO — Hallazgo crítico Orbinum Shielded Pool

Este paquete contiene TODO lo necesario para reportar el hallazgo crítico.
El usuario solo debe copiar-pegar el email abajo y enviarlo.

## Datos de contacto (del SECURITY.md del repo)
- medium/high severity: security@bitarray.dev
- contacto directo: Wei <wei@bitarray.dev>
- Proyecto: https://github.com/orbinum (repos: node, protocol-core)
- Testnet viva, TGE mainnet previsto Q4 2026

## EMAIL LISTO PARA ENVIAR

```
To: security@bitarray.dev
Cc: wei@bitarray.dev
Subject: [CRITICAL] Shielded Pool — value of note not bound to deposit in
shield() enables full pool drain (pre-mainnet)

Hello Orbinum team,

I am an independent security researcher. I found a critical vulnerability in
the Orbinum shielded pool that allows any user to drain the entire pool
balance, including funds deposited by other users. Since mainnet is planned
for Q4 2026, I am reporting this before launch.

TITLE: shield() does not bind the note value to the deposited amount ->
unbounded note minting -> pool drain via unshield()

LOCATION:
- frame/shielded-pool/src/operations/shield.rs (ShieldOperation::execute)
- frame/shielded-pool/src/operations/unshield.rs (UnshieldOperation::execute)
- primitives/zk-circuits/src/circuits/unshield.rs (constraint 4: note_value == amount + fee)

DESCRIPTION:
The note commitment is C = Poseidon4(note_value, asset_id, owner_pk, blinding).
The unshield circuit proves: (1) C correct, (2) Merkle membership, (3)
nullifier correctness, (4) note_value == amount + fee. note_value is a PRIVATE
witness freely chosen by the spender. In shield() there is NO value proof
forcing note_value == deposited amount (unlike claim_shielded_fees, which
requires a value_proof for exactly this reason). The only guard in unshield is
PoolBalancePerAsset >= amount + fee, which checks against the pool TOTAL
(including other users' deposits).

ATTACK (step by step):
1. Attacker A chooses V = u64::MAX and generates blinding/owner_pk.
2. A computes C = Poseidon4(V, asset_id, owner_pk, blinding) and nullifier.
3. A calls shield(asset_id, amount=1, commitment=C, memo). Pool gets 1 unit.
4. Honest users deposit funds; pool balance grows to T.
5. A calls unshield(proof, root, nullifier, asset_id, amount=T, recipient=A,
   fee=0, change_commitment=C2). The proof is cryptographically valid (C in
   tree, nullifier from known preimage, note_value=V >= T). PoolBalance >= T
   passes. Pool pays T to A. A repeats until pool is empty.

SEVERITY: Critical (loss of all user funds; similar to the classic "deposit
amount mismatch" / "note minting" bug in private pools).

MITIGATION: require a value_proof in shield (as already done in
claim_shielded_fees), or use fixed denominations, or constrain note_value in
the circuit.

I also identified a secondary Medium issue (unbounded growth of the historic
roots queue under sustained load - merkle/service.rs) and a Low (validate_unshield accepts amount=0).

Full report attached (PDF/markdown). Happy to answer any questions.

Please acknowledge receipt and let me know if you have a bug bounty program
for pre-mainnet findings; I would be happy to coordinate disclosure.

Best regards,
Independent researcher
```

## PASOS PARA EL USUARIO
1. Enviar el email desde rdl2.job@gmail.com (o cualquier cuenta).
2. Si no hay respuesta en 3-5 días, escalar por X (@orbinumnetwork) o Discord.
3. Guardar el acuse de recibo — sirve para coordinar disclosure responsable
   y/o solicitar recompensa si tienen programa.
4. Opcional: crear GitHub Security Advisory en el repo (tab "Security" ->
   "Report a vulnerability").

## VALOR POTENCIAL
- Pre-mainnet critical: típicamente $5,000 - $50,000+ en programas de bounty
  de protocolos DeFi con privacidad (referencia: Immunefi pre-mainnet bounties).
- Aún sin programa formal, un hallazgo que evita un desastre de launch suele
  recibir recompensa de buena voluntad y reconocimiento público.
