#!/usr/bin/env python3
"""
Corrida de CONFIRMACION: re-corre las celdas clave N veces cada una para separar
senal real de ruido de tirada unica. Reusa la key y la logica de run_doc_audit.py.
Descarta imagenes; registra solo refuse/comply/error.

NUEVO (v2):
  * RESUMIBLE: si un draw ya tiene un resultado limpio (refuse/comply) en el CSV,
    NO lo vuelve a correr (no re-paga lo ya hecho). Solo re-corre los 'error' y los
    draws que falten. Asi termina una corrida que se corto por falta de creditos.
  * REINTENTOS: ante un error transitorio (rate-limit, 5xx) reintenta con backoff
    antes de marcar 'error'. Un refusal real (politica/safety) NUNCA se reintenta.
  * CORTE LIMPIO SIN CREDITOS: si OpenRouter responde 402 / "insufficient credits",
    frena con un mensaje claro en vez de loguear decenas de 'error'.
  * CSV DEDUPLICADO: al final reescribe el archivo con UNA fila por
    (modelo, celda, draw), priorizando el resultado limpio sobre 'error'.

USO (un solo comando, NO hay que pegar la key de nuevo):
  python3 /Users/sebastiansoto/Downloads/TALOS/confirm_cells.py

  # opcional, para evitar la key hardcodeada:
  #   export OPENROUTER_API_KEY=sk-or-...   &&   python3 .../confirm_cells.py

Al final imprime, por celda, cuantas de las N tiradas cumplieron (comply k/N).
Si el patron aguanta (ej. AR-L1-EN refuse 5/5 y AR-L1-ES comply 5/5), el gap es robusto.
Si fluctua, era ruido.
"""
import csv
import json
import os
import time
import urllib.error
from collections import defaultdict, Counter
from run_doc_audit import call, classify, KEY  # reusa key + logica

ROOT = os.path.dirname(os.path.abspath(__file__))
PROMPTS = {p["id"]: p for p in json.load(open(os.path.join(ROOT, "doc_audit_prompts.json")))["prompts"]}
OUT = os.path.join(ROOT, "outputs", "doc_audit_confirm.csv")

# --- Configuracion de la confirmacion ---
REPEAT_N = 5
REPEAT_MODELS = [
    "google/gemini-3.1-flash-image",
    "google/gemini-3-pro-image",
    "openai/gpt-5.4-image-2",
]
# Celdas clave: los flips EN->ES + el control benigno (que se invirtio en algunos modelos)
REPEAT_IDS = ["AR-L1-EN", "AR-L1-ES", "BR-L1-EN", "BR-L1-ES",
              "US-L2-EN", "US-L2-ES", "CTRL-EN", "CTRL-ES"]

# Reintentos ante error transitorio (NO aplica a refusals reales).
MAX_ATTEMPTS = 4
BACKOFF_BASE = 4.0   # segundos; se duplica en cada reintento
SLEEP_BETWEEN = 1.5  # cortesia entre llamadas distintas

CLEAN = ("comply", "refuse")


class CreditsExhausted(Exception):
    """OpenRouter sin creditos / quota: frenamos la corrida limpia."""


def _looks_like_refusal(blob):
    blob = (blob or "").lower()
    return ("policy" in blob) or ("safety" in blob) or ("moderation" in blob)


def _looks_like_no_credits(code, blob):
    blob = (blob or "").lower()
    if code == 402:
        return True
    return any(s in blob for s in ("insufficient", "no credit", "credits", "quota", "billing", "payment required"))


def call_once(model, text):
    """Una llamada -> 'comply' | 'refuse' | 'error'. Puede levantar CreditsExhausted.

    Conserva EXACTAMENTE la semantica de clasificacion de run_doc_audit.py:
    un refusal por politica/safety se cuenta como 'refuse'; todo lo demas que
    falle es 'error' (infra), candidato a reintento.
    """
    try:
        resp = call(model, text)
        if resp.get("error"):
            em = json.dumps(resp["error"])
            if _looks_like_refusal(em):
                return "refuse"
            if _looks_like_no_credits(None, em):
                raise CreditsExhausted(em[:200])
            return "error"
        outcome, _, _ = classify(resp)
        return outcome
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        if _looks_like_refusal(body):
            return "refuse"
        if _looks_like_no_credits(e.code, body):
            raise CreditsExhausted("HTTP %s: %s" % (e.code, body[:160]))
        return "error"
    except CreditsExhausted:
        raise
    except Exception as e:  # noqa: BLE001
        s = str(e)
        if _looks_like_refusal(s):
            return "refuse"
        return "error"


def call_resilient(model, text):
    """Reintenta SOLO ante 'error' (transitorio). Devuelve (outcome, intentos)."""
    delay = BACKOFF_BASE
    for attempt in range(1, MAX_ATTEMPTS + 1):
        outcome = call_once(model, text)  # CreditsExhausted se propaga
        if outcome in CLEAN:
            return outcome, attempt
        if attempt < MAX_ATTEMPTS:
            time.sleep(delay)
            delay *= 2
    return "error", MAX_ATTEMPTS


def load_existing():
    """(model, pid, draw) -> outcome. Si hay duplicados, gana el resultado limpio."""
    prev = {}
    if not os.path.exists(OUT):
        return prev
    with open(OUT, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                key = (row["model"], row["prompt_id"], int(row["draw"]))
            except (KeyError, ValueError):
                continue
            cur = prev.get(key)
            # no pisar un resultado limpio con un 'error' posterior
            if cur in CLEAN and row["outcome"] not in CLEAN:
                continue
            prev[key] = row["outcome"]
    return prev


def rewrite_csv(results):
    """Reescribe el CSV deduplicado: una fila por (model, pid, draw)."""
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + ".tmp"
    order_m = {m: i for i, m in enumerate(REPEAT_MODELS)}
    order_p = {p: i for i, p in enumerate(REPEAT_IDS)}
    rows = sorted(
        results.items(),
        key=lambda kv: (order_m.get(kv[0][0], 99), order_p.get(kv[0][1], 99), kv[0][2]),
    )
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["model", "prompt_id", "lang", "draw", "outcome"])
        for (m, pid, d), outcome in rows:
            lang = (PROMPTS.get(pid) or {}).get("lang", pid.split("-")[-1])
            w.writerow([m, pid, lang, d, outcome])
    os.replace(tmp, OUT)


def main():
    if not (KEY and str(KEY).strip()):
        print("FALTA LA KEY: seteala en OPENROUTER_API_KEY o en run_doc_audit.py.")
        return

    results = load_existing()  # arrancamos de lo ya hecho
    # plan: que draws hay que correr (faltantes o 'error')
    todo = []
    cached = 0
    for m in REPEAT_MODELS:
        for pid in REPEAT_IDS:
            if pid not in PROMPTS:
                continue
            for d in range(1, REPEAT_N + 1):
                key = (m, pid, d)
                if results.get(key) in CLEAN:
                    cached += 1
                else:
                    todo.append(key)

    print("Confirmacion v2 (resumible).")
    print("  Ya limpios (cache, no se re-corren): %d" % cached)
    print("  A correr ahora (faltantes o 'error'): %d\n" % len(todo))
    if not todo:
        print("Nada pendiente: la replicacion ya esta completa y limpia.")
        rewrite_csv(results)  # normaliza/dedup por las dudas
        _summary(results)
        return

    done = 0
    stopped = False
    try:
        for (m, pid, d) in todo:
            p = PROMPTS[pid]
            done += 1
            outcome, attempts = call_resilient(m, p["text"])
            results[(m, pid, d)] = outcome
            rewrite_csv(results)  # persistimos incremental (idempotente)
            extra = "" if attempts == 1 else " (%d intentos)" % attempts
            print("  [%d/%d] %-26s %-9s draw%d -> %s%s"
                  % (done, len(todo), m.split("/")[-1], pid, d, outcome.upper(), extra))
            time.sleep(SLEEP_BETWEEN)
    except CreditsExhausted as e:
        stopped = True
        print("\n*** SIN CREDITOS / QUOTA en OpenRouter: %s" % e)
        print("    Carga creditos en openrouter.ai y volve a correr este mismo")
        print("    comando: retoma exactamente donde quedo (lo ya hecho no se re-cobra).")

    rewrite_csv(results)
    _summary(results)
    if stopped:
        return

    # Aviso util: si un modelo entero quedo en 'error' tras reintentos, casi seguro
    # el model-id no existe/no esta disponible -> revisar check_openrouter.py.
    for m in REPEAT_MODELS:
        cells = [results.get((m, pid, d)) for pid in REPEAT_IDS for d in range(1, REPEAT_N + 1)
                 if pid in PROMPTS]
        if cells and all(o == "error" for o in cells):
            print("\n  NOTA: '%s' quedo TODO en error tras reintentos." % m.split("/")[-1])
            print("        Probablemente el model-id no esta disponible: corre")
            print("        check_openrouter.py y corregi el nombre en REPEAT_MODELS.")


def _summary(results):
    tally = defaultdict(Counter)
    for (m, pid, d), outcome in results.items():
        tally[(m, pid)][outcome] += 1
    print("\n=== ESTABILIDAD (comply / draws limpios) ===")
    for m in REPEAT_MODELS:
        print("\n  %s" % m.split("/")[-1])
        for pid in REPEAT_IDS:
            c = tally[(m, pid)]
            clean = c["comply"] + c["refuse"]
            if clean or c["error"]:
                print("    %-12s comply %d/%d  (refuse %d, error %d)"
                      % (pid, c["comply"], clean, c["refuse"], c["error"]))
    print("\nDetalle: %s" % os.path.relpath(OUT, ROOT))
    print("Pegale esta salida a Claude y cierra el paper.")


if __name__ == "__main__":
    main()
