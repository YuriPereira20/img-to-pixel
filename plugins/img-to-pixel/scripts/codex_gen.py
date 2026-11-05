"""Gera imagem(ns) via Codex CLI (ferramenta nativa image_generation) e copia para <out_dir>.

Uso: python codex_gen.py <out_dir> --prompt-file <desc.md> [--ref <img>] [--style <img>] [--n 3] [--art 64]
Salva <out_dir>/generated_1.png .. generated_N.png (variações em paralelo).
O Codex salva em ~/.codex/generated_images/<thread>/*.png; pegamos os da thread de cada execução.
"""
import argparse, json, shutil, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

GEN_DIR = Path.home() / ".codex" / "generated_images"


def build_prompt(desc, art, has_ref, has_style):
    # Estilo primeiro: o modelo de imagem dá mais peso ao começo do prompt.
    p = [
        "Use your image generation tool to create exactly ONE image. Do not write code, do not edit files.",
        "",
        "## STYLE (highest priority)",
        f"Authentic hand-placed pixel art drawn on an exact {art}x{art} pixel grid, then upscaled with nearest-neighbor: "
        "every art pixel is a perfectly square block of the SAME size across the whole image, aligned to one grid.",
        "- Clean, readable shapes made of large flat color clusters; NO noise, NO camouflage-like speckles, NO stray single pixels, NO dithering.",
        "- 1-pixel near-black outline (#1a1220) around every shape and between major shapes.",
        "- Cel shading with 3 tones per material (shadow, base, highlight), light from the top-left; shadows as solid shapes, not texture.",
        "- Hair/beard as a few big curved locks, each lock = base + shadow + 1-2 highlight pixels.",
        "- Face with clear planes: shadow under the headwear, on one side of the face, under the nose and on the neck; warm blush blocks.",
        "- Eyes: white, 2-tone iris, dark pupil, 1 white highlight pixel, dark upper lid line.",
        "- Limited warm, saturated palette (about 16-24 colors total). No anti-aliasing, no blur, no gradients, no glow.",
        "- Bust portrait, square 1:1, subject centered, top of head ~6% from the top, shoulders cut by the bottom edge.",
        "- Background: ONE flat solid color #FF00FF filling everything around the subject (no shadow, no border, no texture).",
    ]
    if has_style:
        p.append("The LAST attached image is the STYLE reference: match its pixel size, outline weight, shading and level of detail. Do NOT copy its subject, clothes or colors.")
    if has_ref:
        p.append("The FIRST attached image is the SUBJECT reference, for identity only (who, features, outfit, colors). Redraw it completely in the pixel art style above (do NOT keep a flat cartoon rendering) and apply every change requested in the SUBJECT text, especially expression.")
    p += ["", "## SUBJECT", desc]
    return "\n".join(p)


def run_codex(cmd, prompt):
    """Roda um `codex exec --json` e devolve os PNGs da thread DELE.
    Filtrar por thread evita pegar imagens de outras sessões do Codex rodando ao mesmo tempo."""
    # shutil.which resolve codex.cmd no Windows; prompt via stdin evita limite/escape da linha de comando
    r = subprocess.run([shutil.which("codex") or "codex", *cmd, "--json", "-"], input=prompt, text=True,
                       encoding="utf-8", capture_output=True)
    for line in r.stdout.splitlines():
        if '"thread.started"' in line:
            return sorted((GEN_DIR / json.loads(line)["thread_id"]).glob("*.png"), key=lambda p: p.stat().st_mtime)
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--prompt-file", type=Path, required=True)
    ap.add_argument("--ref", type=Path, help="imagem do ASSUNTO (opcional)")
    ap.add_argument("--style", type=Path, help="imagem de referência de ESTILO (opcional)")
    ap.add_argument("--n", type=int, default=3, help="variações em paralelo")
    ap.add_argument("--art", type=int, default=64, help="grid nativo pedido ao modelo")
    # gpt-6.1-sol do config.toml não roda com conta ChatGPT; astra é o topo da lista do models_cache
    ap.add_argument("--model", default="gpt-6-astra", help="modelo do Codex")
    ap.add_argument("--print-prompt", action="store_true", help="só imprime o prompt (fluxo dentro do Codex)")
    a = ap.parse_args()
    if a.print_prompt:
        sys.stdout.reconfigure(encoding="utf-8")  # console do Windows é cp1252 e quebra com acentos/setas
        print(build_prompt(a.prompt_file.read_text(encoding="utf-8"), a.art, bool(a.ref), bool(a.style)))
        return

    cmd = ["exec", "--skip-git-repo-check", "--ephemeral", "-s", "read-only", "-m", a.model]
    for img in (a.ref, a.style):  # ordem importa: assunto primeiro, estilo por último
        if img:
            cmd += ["-i", str(img)]
    prompt = build_prompt(a.prompt_file.read_text(encoding="utf-8"), a.art, bool(a.ref), bool(a.style))
    a.out_dir.mkdir(parents=True, exist_ok=True)
    (a.out_dir / "prompt_final.txt").write_text(prompt, encoding="utf-8")

    with ThreadPoolExecutor(a.n) as ex:
        new = [p for imgs in ex.map(lambda _: run_codex(cmd, prompt), range(a.n)) for p in imgs[-1:]]
    if not new:
        sys.exit("codex não gerou imagem. Verifique `codex login` e a feature image_generation.")
    for i, p in enumerate(new, 1):
        shutil.copy2(p, a.out_dir / f"generated_{i}.png")
        print(f"ok: {a.out_dir / f'generated_{i}.png'}")
    if len(new) < a.n:
        print(f"aviso: {len(new)}/{a.n} variações geradas")

if __name__ == "__main__":
    main()
