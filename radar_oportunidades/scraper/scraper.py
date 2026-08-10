#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RADAR DE OPORTUNIDADES GRATUITAS - Scraper principal
====================================================
Extrae cursos, becas, empleos y concursos gratuitos de fuentes públicas,
los limpia, deduplica y guarda en datos/*.json para que la landing page
los consuma sin servidor.

Uso:
    python3 scraper.py            # ejecuta todas las fuentes
    python3 scraper.py --no-web   # sin navegador (solo fuentes seed)
    python3 scraper.py --test     # prueba rápida, escribe en /tmp

Autor: Radar Oportunidades (automático)
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import sys

try:
    import requests
except ImportError:
    requests = None

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATOS_DIR = os.path.join(BASE, "datos")
SCRAPER_DIR = os.path.dirname(os.path.abspath(__file__))
FUENTES_PATH = os.path.join(SCRAPER_DIR, "fuentes.json")
CACHE_CAPACITATE = os.path.join(SCRAPER_DIR, "capacitate_cache.json")

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

sys.path.insert(0, SCRAPER_DIR)
from seed_data import SEED_ITEMS  # noqa: E402


def hoy():
    return datetime.date.today().isoformat()


TIPO_NORMAL = {
    "cursos": "curso",
    "curso": "curso",
    "becas": "beca",
    "beca": "beca",
    "empleos": "empleo",
    "empleo": "empleo",
    "concursos": "concurso",
    "concurso": "concurso",
    "capacitaciones": "capacitacion",
    "capacitacion": "capacitacion",
}


def hace_dias(n):
    return (datetime.date.today() - datetime.timedelta(days=n)).isoformat()


def normalizar(texto):
    if not texto:
        return ""
    return re.sub(r"\s+", " ", texto).strip()


def slug(titulo):
    t = titulo.lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t[:60]


def id_item(fuente_id, titulo):
    h = hashlib.sha1(f"{fuente_id}|{normalizar(titulo)}".encode()).hexdigest()[:10]
    return f"{fuente_id}-{h}"


def fecha_determinista(item_id, rango=21):
    """Fecha de 'detección' estable entre scrape y scrape (hash del id)."""
    h = int(hashlib.sha1(item_id.encode()).hexdigest()[:8], 16)
    dias = h % (rango + 1)
    return hace_dias(dias)


def cargar_json(path, por_defecto=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return por_defecto


def guardar_json(path, datos):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def construir_item(base, fuente_id, titulo, **extra):
    titulo = normalizar(titulo)
    tipo = extra.pop("tipo", None) or base.get("tipo", "curso")
    tipo = TIPO_NORMAL.get(tipo, tipo)
    item = {
        "id": id_item(fuente_id, titulo),
        "titulo": titulo,
        "fuente_id": fuente_id,
        "tipo": tipo,
        "fuente": base.get("fuente"),
        "descripcion": normalizar(extra.pop("descripcion", "") or base.get("descripcion", "")),
        "url": extra.pop("url", "") or base.get("url", ""),
        "categoria": extra.pop("categoria", "") or base.get("categoria", ""),
        "certificado": bool(extra.pop("certificado", False)),
        "gratis": True,
        "pais": extra.pop("pais", "") or base.get("pais", ""),
        "requisitos": extra.pop("requisitos", "") or base.get("requisitos", ""),
        "duracion_h": extra.pop("duracion_h", None),
        "origen": extra.pop("origen", "scrapeado"),
        "fecha_deteccion": extra.pop("fecha_deteccion", None),
        "fecha_actualizacion": hoy(),
    }
    item.update(extra)
    return item


def cerrar_item(item):
    if not item.get("fecha_deteccion"):
        item["fecha_deteccion"] = fecha_determinista(item["id"])
    if item.get("duracion_h") is not None:
        try:
            item["duracion_h"] = int(float(item["duracion_h"]))
        except Exception:
            item["duracion_h"] = None
    if not item.get("categoria"):
        item["categoria"] = "Otros"
    if not item.get("descripcion"):
        item["descripcion"] = item.get("titulo", "")
    if item["url"] and not item["url"].startswith("http"):
        item["url"] = "https://" + item["url"].lstrip("/")
    return item


# ============================================================== ADAPTADORES
def adaptador_seed(fuente):
    items = []
    for s in SEED_ITEMS:
        if s["fuente_id"] != fuente["id"]:
            continue
        base = dict(fuente)
        base["fuente"] = fuente["nombre"]
        base["categoria"] = s.get("categoria", "")
        base["descripcion"] = s.get("descripcion", "")
        base["requisitos"] = s.get("requisitos", "")
        base["pais"] = s.get("pais", "")
        item = construir_item(base, fuente["id"], s["titulo"],
                              tipo=s.get("tipo"), url=s.get("url"),
                              certificado=s.get("certificado"),
                              duracion_h=s.get("duracion_h"),
                              origen="curado",
                              categoria=s.get("categoria", "Otros"),
                              descripcion=s.get("descripcion", ""),
                              requisitos=s.get("requisitos", ""),
                              pais=s.get("pais", ""))
        items.append(cerrar_item(item))
    return items


def adaptador_capacitate(fuente, usar_web=True):
    """Cursos de Capacítate para el Empleo (Fundación Carlos Slim)."""
    cache = cargar_json(CACHE_CAPACITATE, {}) or {}
    items = []
    titulos = []

    if usar_web:
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                b = p.chromium.launch(headless=True)
                ctx = b.new_context(user_agent=UA, locale="es-MX")
                pg = ctx.new_page()
                pg.goto(fuente["url"], timeout=60000)
                pg.wait_for_timeout(7000)
                titulos = pg.eval_on_selector_all(
                    "a[title='Ir al curso'] p",
                    "els => els.map(e => (e.textContent||'').replace(/\\s+/g,' ').trim()).filter(Boolean)")
                b.close()
        except Exception as e:
            print(f"  [capacitate] error navegador: {e}", flush=True)
            titulos = list(cache.keys())

    if not titulos:
        titulos = list(cache.keys())

    for titulo in titulos:
        info = cache.get(titulo, {}) or {}
        cid = info.get("id")
        dur = info.get("duracion_h")
        sector = info.get("sector")
        url = (f"https://capacitateparaelempleo.org/cursos/view/{cid}" if cid
               else "https://capacitateparaelempleo.org/cursos")
        base = dict(fuente)
        base["fuente"] = fuente["nombre"]
        item = construir_item(
            base, fuente["id"], titulo,
            url=url,
            duracion_h=dur,
            categoria=sector or "Otros",
            descripcion=f"Curso gratuito en línea de Capacítate para el Empleo "
                        f"(Fundación Carlos Slim).{' Duración: ' + str(dur) + ' h.' if dur else ''}",
            pais=fuente.get("pais", "México"),
            requisitos="Crear cuenta gratuita en la plataforma",
        )
        items.append(cerrar_item(item))
    return items


def adaptador_skillshop(fuente, usar_web=True):
    """Cursos gratuitos de Google (Skillshop / Google Actívate)."""
    items = []
    if not usar_web:
        return items
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        print(f"  [skillshop] sin playwright: {e}", flush=True)
        return items

    urls = [fuente["url"]]
    for cat in fuente.get("categorias_extra", []):
        urls.append(f"https://skillshop.exceedlms.com/student/catalog/list?category_ids={cat}")

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            ctx = b.new_context(user_agent=UA, locale="es-MX")
            pg = ctx.new_page()
            for url in urls:
                try:
                    pg.goto(url, timeout=60000)
                    pg.wait_for_timeout(7000)
                    tarjetas = pg.eval_on_selector_all(
                        "a.mediablock__link",
                        """els => els.map(e => {
                            const card = e.closest('article') || e.parentElement;
                            const text = (card ? card.textContent : e.textContent) || '';
                            const t = text.replace(/\\s+/g,' ').trim();
                            const dur = (t.match(/Duración\\s*([\\d.]+)\\s*h/i) || [])[1];
                            return {href: e.href, titulo: (e.textContent||'').replace(/\\s+/g,' ').trim(), dur};
                        }).filter(x => x.titulo)""")
                    for t in tarjetas:
                        base = dict(fuente)
                        base["fuente"] = fuente["nombre"]
                        item = construir_item(
                            base, fuente["id"], t["titulo"],
                            url=t["href"],
                            duracion_h=t.get("dur"),
                            categoria="Google",
                            descripcion="Curso gratuito en línea de Google con "
                                        "certificado de finalización (Skillshop / Google Actívate).",
                            pais=fuente.get("pais", "Internacional"),
                            requisitos="Crear cuenta gratuita en Skillshop",
                        )
                        items.append(cerrar_item(item))
                except Exception as e:
                    print(f"  [skillshop] error en {url}: {e}", flush=True)
            b.close()
    except Exception as e:
        print(f"  [skillshop] error general: {e}", flush=True)
    return items


def adaptador_generico(fuente, usar_web=True):
    """Sin implementación en vivo: se usa solo el catálogo curado."""
    return []


ADAPTADORES = {
    "capacitate": adaptador_capacitate,
    "skillshop": adaptador_skillshop,
    "seed": adaptador_seed,
}


# ================================================================ PIPELINE
def deduplicar(items):
    vistos = {}
    for it in items:
        clave = (it["fuente_id"], slug(it["titulo"]))
        vistos.setdefault(clave, it)
    return list(vistos.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-web", action="store_true", help="No usar navegador")
    ap.add_argument("--test", action="store_true", help="Escribir en /tmp")
    args = ap.parse_args()

    fuentes = cargar_json(FUENTES_PATH, {}).get("fuentes", [])
    todos = []
    for fuente in fuentes:
        if not fuente.get("activo", True):
            continue
        metodo = fuente.get("metodo", "seed")
        print(f"* {fuente['id']} ({fuente['nombre']}) ...", flush=True)
        try:
            if metodo == "seed":
                items = adaptador_seed(fuente)
            else:
                fn = ADAPTADORES.get(fuente["id"], adaptador_generico)
                items = fn(fuente, usar_web=not args.no_web) or []
                if not items:
                    print(f"  [aviso] sin datos en vivo; usando catálogo curado.", flush=True)
                    items = adaptador_seed(fuente)
        except Exception as e:
            print(f"  [error] {e}", flush=True)
            items = adaptador_seed(fuente)
        print(f"  -> {len(items)} oportunidades", flush=True)
        todos.extend(items)

    todos = deduplicar(todos)

    # Fechas de detección estables
    for it in todos:
        if not it.get("fecha_deteccion"):
            it["fecha_deteccion"] = fecha_determinista(it["id"])

    todos.sort(key=lambda x: x.get("fecha_deteccion", ""), reverse=True)

    por_tipo = {
        "cursos": [i for i in todos if i["tipo"] == "curso"],
        "becas": [i for i in todos if i["tipo"] == "beca"],
        "empleos": [i for i in todos if i["tipo"] == "empleo"],
        "concursos": [i for i in todos if i["tipo"] == "concurso"],
    }

    meta = {
        "actualizado": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total": len(todos),
        "por_tipo": {k: len(v) for k, v in por_tipo.items()},
        "fuentes": [f["id"] for f in fuentes if f.get("activo")],
    }

    out_dir = "/tmp/opencode/datos_test" if args.test else DATOS_DIR
    os.makedirs(out_dir, exist_ok=True)

    guardar_json(os.path.join(out_dir, "todos.json"), {"meta": meta, "items": todos})
    for tipo, lista in por_tipo.items():
        guardar_json(os.path.join(out_dir, f"{tipo}.json"), {"meta": meta, "items": lista})

    print("\nRESUMEN:", json.dumps(meta, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
