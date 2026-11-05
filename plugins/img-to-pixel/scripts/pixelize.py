"""Converte uma imagem (ex.: pixel art gerada por IA) num grid exato NxN e exporta.

Uso:
  python pixelize.py preview <img> <out_dir> [--grid 64] [--colors 32] [--art 64]
  python pixelize.py export  <out_dir> [--cell 8] [--gap 0]
  python pixelize.py selftest

preview: gera <out_dir>/sprite.png (NxN exato, sem fundo) + sprite_bg.png + preview.png (~512px)
export:  a partir de sprite.png/sprite_bg.png gera html/png/svg com e sem fundo.
"""
import argparse, json, sys
from pathlib import Path

import numpy as np
from PIL import Image


def estimate_art(img, grid):
    """Pixel art de IA não tem grid uniforme; o tamanho de pixel mais comum (moda das sequências
    de mesma cor) dá a resolução nativa. Arredonda para um divisor de `grid` (escala log)."""
    a = np.array(img.convert("RGB")).astype(int)
    runs = []
    for line in list(a[::7]) + list(a.transpose(1, 0, 2)[::7]):
        runs += list(np.diff(np.flatnonzero(np.abs(np.diff(line, axis=0)).sum(1) > 40)))
    r = np.array(runs)
    r = r[(r >= 3) & (r <= a.shape[1] // 8)]
    if not len(r):
        return grid
    native = a.shape[1] / np.bincount(r).argmax()
    divs = [d for d in (16, 32, 64, 128, 256) if grid % d == 0 and d <= grid] or [grid]
    return min(divs, key=lambda d: abs(np.log(d / native)))


def to_grid(img, grid, colors, art=None):
    """Amostra a arte na resolução nativa `art` e amplia (nearest) para `grid`.
    Octree preserva cores de área pequena (brilhos brancos; mediancut as perdia).
    Cada célula usa só o miolo (4x4 de 8x8): as bordas misturam pixels vizinhos e geram serrilhado."""
    art = art or estimate_art(img, grid)
    q = img.convert("RGB").quantize(colors=colors, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE)
    up = np.array(q.resize((art * 8, art * 8), Image.NEAREST)).reshape(art, 8, art, 8)[:, 2:6, :, 2:6]
    blocks = up.transpose(0, 2, 1, 3).reshape(art, art, 16)
    idx = np.array([[np.bincount(b).argmax() for b in row] for row in blocks], dtype=np.uint8)
    pal = np.array(q.getpalette()[: 3 * 256] + [0] * max(0, 768 - len(q.getpalette())), dtype=np.uint8).reshape(-1, 3)
    rgb = pal[idx]
    if art != grid:
        rgb = np.array(Image.fromarray(rgb).resize((grid, grid), Image.NEAREST))
    return rgb, art  # (grid, grid, 3)


def remove_bg(rgb, tol=64):  # IA gera 2-3 tons do fundo; fundo é cor exclusiva, então folga é segura
    """Cor de fundo (cantos de cima) -> alpha 0 em todo pixel dessa cor.
    O prompt exige fundo de cor que não existe no assunto, então não precisa de flood fill
    (que deixava pixels de fundo presos entre contornos)."""
    h, w, _ = rgb.shape
    # só cantos de cima: em retrato de busto os ombros encostam nos cantos de baixo
    corners = [tuple(rgb[0, 0]), tuple(rgb[0, w - 1])]
    bg = np.array(max(set(corners), key=lambda c: int(c[0]) + int(c[2]) - int(c[1])), dtype=int)  # empate: mais magenta
    match = np.abs(rgb.astype(int) - bg).sum(axis=2) <= tol
    return np.where(match, 0, 255).astype(np.uint8), tuple(int(c) for c in bg)


def preview(src, out, grid, colors, art=None):
    out.mkdir(parents=True, exist_ok=True)
    rgb, art = to_grid(Image.open(src), grid, colors, art)
    alpha, bg = remove_bg(rgb)
    Image.fromarray(np.dstack([rgb, alpha])).save(out / "sprite.png")
    Image.fromarray(rgb).save(out / "sprite_bg.png")
    Image.fromarray(rgb).resize((grid * (512 // grid),) * 2, Image.NEAREST).save(out / "preview.png")
    (out / "meta.json").write_text(json.dumps({"grid": grid, "art": art, "colors": colors, "bg": bg}))
    print(f"ok: {out/'sprite.png'} arte nativa={art}x{art} -> grid {grid} bg={bg} cores={len(np.unique(rgb.reshape(-1, 3), axis=0))}")


def hexc(c):
    return "#%02x%02x%02x" % tuple(c[:3])


def export(out, cell, gap):
    rgba = np.array(Image.open(out / "sprite.png").convert("RGBA"))
    bg = tuple(json.loads((out / "meta.json").read_text())["bg"])
    h, w, _ = rgba.shape
    step = cell + gap
    W, H = w * step - gap, h * step - gap
    tag = f"c{cell}_g{gap}"
    for with_bg in (False, True):
        suf = f"{tag}_{'com_fundo' if with_bg else 'sem_fundo'}"
        # PNG: cada pixel vira um bloco cell x cell, separado por gap
        canvas = np.zeros((H, W, 4), np.uint8)
        if with_bg:
            canvas[:] = (*bg, 255)
        svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" shape-rendering="crispEdges">']
        if with_bg:
            svg.append(f'<rect width="{W}" height="{H}" fill="{hexc(bg)}"/>')
        cells = []
        for y in range(h):
            for x in range(w):
                r, g, b, a = rgba[y, x]
                if a == 0:
                    cells.append("<i></i>")
                    continue
                canvas[y * step:y * step + cell, x * step:x * step + cell] = (r, g, b, 255)
                svg.append(f'<rect x="{x*step}" y="{y*step}" width="{cell}" height="{cell}" fill="{hexc((r, g, b))}"/>')
                cells.append(f'<i style="background:{hexc((r, g, b))}"></i>')
        svg.append("</svg>")
        Image.fromarray(canvas).save(out / f"pixel_{suf}.png")
        (out / f"pixel_{suf}.svg").write_text("\n".join(svg), encoding="utf-8")
        page_bg = hexc(bg) if with_bg else "transparent"
        (out / f"pixel_{suf}.html").write_text(
            f"""<!doctype html><html><head><meta charset="utf-8"><title>pixel {w}x{h}</title><style>
body{{margin:0;min-height:100vh;display:grid;place-items:center;background:{page_bg}}}
.grid{{display:grid;grid-template-columns:repeat({w},{cell}px);grid-auto-rows:{cell}px;gap:{gap}px;background:{page_bg}}}
.grid i{{display:block}}
</style></head><body><div class="grid">{''.join(cells)}</div></body></html>""",
            encoding="utf-8",
        )
    print(f"ok: {out} pixel_{tag}_(com|sem)_fundo.(html|png|svg)  {W}x{H}px")


def selftest():
    import tempfile
    d = Path(tempfile.mkdtemp())
    img = np.full((256, 256, 3), 255, np.uint8)  # fundo branco
    img[64:192, 64:192] = (200, 30, 30)            # quadrado vermelho = 64x64 células no grid 128
    Image.fromarray(img).save(d / "in.png")
    preview(d / "in.png", d, 128, 8, art=128)
    s = np.array(Image.open(d / "sprite.png"))
    assert s.shape == (128, 128, 4)
    assert s[0, 0, 3] == 0 and s[64, 64, 3] == 255 and tuple(s[64, 64, :3]) == (200, 30, 30)
    assert (s[..., 3] == 255).sum() == 64 * 64
    export(d, 4, 1)
    p = np.array(Image.open(d / "pixel_c4_g1_sem_fundo.png"))
    assert p.shape == (128 * 5 - 1, 128 * 5 - 1, 4)
    assert p[32 * 5 + 4, 32 * 5, 3] == 0  # gap transparente entre pixels
    assert np.array(Image.open(d / "pixel_c4_g1_com_fundo.png"))[0, 0, 3] == 255
    print("selftest ok")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("preview"); p.add_argument("src", type=Path); p.add_argument("out", type=Path)
    p.add_argument("--grid", type=int, default=64); p.add_argument("--colors", type=int, default=32)
    p.add_argument("--art", type=int, default=None, help="resolução nativa da arte (padrão: estimada)")
    e = sub.add_parser("export"); e.add_argument("out", type=Path)
    e.add_argument("--cell", type=int, default=8); e.add_argument("--gap", type=int, default=0)
    sub.add_parser("selftest")
    a = ap.parse_args()
    if a.cmd == "preview":
        preview(a.src, a.out, a.grid, a.colors, a.art)
    elif a.cmd == "export":
        if a.cell < 1 or a.gap < 0:
            sys.exit("cell >= 1 e gap >= 0")
        export(a.out, a.cell, a.gap)
    else:
        selftest()
