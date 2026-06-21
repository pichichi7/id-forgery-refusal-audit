#!/usr/bin/env python3
"""
Chequeo benigno de OpenRouter: (1) lista tus modelos de imagen, (2) prueba generar
una imagen inofensiva (una manzana). NO toca documentos ni nada sensible.

COMO USARLO:
  1. Set your key as an environment variable:  export OPENROUTER_API_KEY=sk-or-...
  2. Run:  python3 check_openrouter.py
  3. Rotate/revoke the key on openrouter.ai when you are done.
"""

import json
import os
import urllib.request
import urllib.error

# API key: set the OPENROUTER_API_KEY environment variable (never hard-code it).
#   export OPENROUTER_API_KEY=sk-or-...
KEY = os.environ.get("OPENROUTER_API_KEY", "")

BASE = "https://openrouter.ai/api/v1"


def _post(path, payload):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def _get(path):
    req = urllib.request.Request(BASE + path, headers={"Authorization": "Bearer " + KEY})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    if not KEY.strip():
        print("FALTA LA KEY: pega tu API key en la linea KEY = \"\" arriba y volve a correr.")
        return

    print("== 1) Modelos de imagen disponibles + PRECIO (USD) ==")
    try:
        data = _get("/models").get("data", [])
        img_full = [m for m in data
                    if "image" in (m.get("architecture", {}).get("output_modalities") or [])]
        img_models = [m["id"] for m in img_full]
        if img_full:
            for m in img_full:
                p = m.get("pricing", {})
                print("  -", m["id"])
                print("      imagen:", p.get("image", "?"),
                      "| request:", p.get("request", "?"),
                      "| prompt/token:", p.get("prompt", "?"),
                      "| completion/token:", p.get("completion", "?"))
        else:
            print("  (no aparecen modelos con salida de imagen; quiza tu cuenta no tiene acceso)")
    except urllib.error.HTTPError as e:
        print("  ERROR listando modelos:", e.code, e.read().decode("utf-8", "replace")[:300])
        return
    except Exception as e:  # noqa: BLE001
        print("  ERROR de conexion:", e)
        return

    print("\n== 2) Prueba benigna de generacion (una manzana roja) ==")
    # Elegir un modelo de imagen que EXISTA en tu cuenta (evita el 404).
    preferidos = ["google/gemini-2.5-flash-image", "google/gemini-3.1-flash-image",
                  "google/gemini-3-pro-image", "openai/gpt-5-image-mini", "openai/gpt-5-image"]
    test_model = next((m for m in preferidos if m in img_models),
                      next((m for m in img_models if m != "openrouter/auto"), None))
    if not test_model:
        print("  No hay un modelo de imagen utilizable para la prueba.")
        return
    try:
        body = {
            "model": test_model,
            "modalities": ["image", "text"],
            "messages": [{"role": "user",
                          "content": "A simple friendly illustration of a red apple on a white table."}],
        }
        resp = _post("/chat/completions", body)
        if resp.get("error"):
            print("  Respuesta con error:", json.dumps(resp["error"])[:300])
            return
        msg = (resp.get("choices") or [{}])[0].get("message", {})
        has_image = bool(msg.get("images"))
        print("  Modelo probado:", test_model)
        print("  RESULTADO:", "IMAGE OK -> tu key genera imagenes." if has_image
              else "el modelo respondio pero sin campo de imagen (revisa el modelo o el plan).")
    except urllib.error.HTTPError as e:
        print("  ERROR en la generacion:", e.code, e.read().decode("utf-8", "replace")[:300])
    except Exception as e:  # noqa: BLE001
        print("  ERROR de conexion:", e)


if __name__ == "__main__":
    main()
