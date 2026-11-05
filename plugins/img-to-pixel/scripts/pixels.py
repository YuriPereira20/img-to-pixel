"""Retoque pixel a pixel de um sprite (feito direto pelo agente, sem gerar imagem).

  python pixels.py dump  <sprite_dir> <x0> <y0> <x1> <y1> > regiao.txt   (x1/y1 exclusivos)
  python pixels.py apply <sprite_dir> regiao.txt
  python pixels.py selftest

Formato (o dump já sai assim; edite as linhas do grid e/ou acrescente cores na legenda):
  @ 19 27            <- canto superior esquerdo da região
  A #190a1a          <- legenda: 1 caractere -> cor; '.' = transparente (fundo)
  B #e8dec7
  ---
  ABBA.              <- uma linha por linha de pixels
apply guarda o estado anterior em <sprite_dir>/_historico/NN/ e gera preview.png + retoque.png (antes|depois ampliado).
"""
import json, shutil, string, sys
from pathlib import Path

import numpy as np
from PIL import Image

KEYS = string.ascii_uppercase + string.ascii_lowercase + string.digits


def dump(d, x0, y0, x1, y1):
    s = np.array(Image.open(d / "sprite.png").convert("RGBA"))[y0:y1, x0:x1]
    leg, rows = {}, []
    for row in s:
        line = ""
        for r, g, b, a in row:
            if a == 0:
                line += "."
                continue
            c = "#%02x%02x%02x" % (r, g, b)
            leg.setdefault(c, KEYS[len(leg)])
            line += leg[c]
        rows.append(line)
    return "\n".join([f"@ {x0} {y0}", *(f"{k} {c}" for c, k in leg.items()), "---", *rows]) + "\n"


def parse(text):
    head, grid = text.split("---\n", 1)
    lines = [l.strip() for l in head.strip().splitlines() if l.strip()]
    x0, y0 = map(int, lines[0].lstrip("@").split())
    leg = {}
    for l in lines[1:]:
        k, c = l.split()
        assert len(k) == 1 and k != "." and len(c) == 7 and c[0] == "#", f"legenda inválida: {l}"
        leg[k] = tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))
    rows = [r.strip() for r in grid.strip().splitlines()]
    assert rows and len({len(r) for r in rows}) == 1, "todas as linhas do grid precisam ter o mesmo tamanho"
    bad = {ch for r in rows for ch in r if ch != "." and ch not in leg}
    assert not bad, f"caracteres sem cor na legenda: {bad}"
    return x0, y0, leg, rows


def apply(d, text):
    x0, y0, leg, rows = parse(text)
    s = np.array(Image.open(d / "sprite.png").convert("RGBA"))
    h, w = len(rows), len(rows[0])
    assert y0 + h <= s.shape[0] and x0 + w <= s.shape[1], "região sai do sprite"
    hist = d / "_historico"
    snap = hist / f"{len(list(hist.glob('*'))) if hist.exists() else 0:02d}"
    snap.mkdir(parents=True)
    for f in ("sprite.png", "sprite_bg.png"):
        shutil.copy2(d / f, snap / f)
    bg = tuple(json.loads((d / "meta.json").read_text())["bg"])
    before = Image.open(d / "sprite_bg.png").convert("RGB")
    sb = np.array(before)
    for dy, r in enumerate(rows):
        for dx, ch in enumerate(r):
            y, x = y0 + dy, x0 + dx
            if ch == ".":
                s[y, x] = (*bg, 0)
                sb[y, x] = bg
            else:
                s[y, x] = (*leg[ch], 255)
                sb[y, x] = leg[ch]
    Image.fromarray(s).save(d / "sprite.png")
    after = Image.fromarray(sb)
    after.save(d / "sprite_bg.png")
    n = s.shape[0]
    after.resize((n * (512 // n),) * 2, Image.NEAREST).save(d / "preview.png")
    # antes|depois da região com 4px de folga, ampliado
    box = (max(x0 - 4, 0), max(y0 - 4, 0), min(x0 + w + 4, n), min(y0 + h + 4, n))
    z = max(1, 480 // (box[2] - box[0]))
    a, b = (im.crop(box).resize(((box[2] - box[0]) * z, (box[3] - box[1]) * z), Image.NEAREST) for im in (before, after))
    cmp_ = Image.new("RGB", (a.width * 2 + 12, a.height), (255, 255, 255))
    cmp_.paste(a, (0, 0)); cmp_.paste(b, (a.width + 12, 0))
    cmp_.save(d / "retoque.png")
    print(f"ok: {h}x{w} px aplicados em ({x0},{y0}); antes salvo em {snap}; veja {d / 'retoque.png'}")


def selftest():
    import tempfile
    d = Path(tempfile.mkdtemp())
    s = np.zeros((8, 8, 4), np.uint8); s[2:6, 2:6] = (200, 30, 30, 255)
    Image.fromarray(s).save(d / "sprite.png")
    Image.fromarray(np.where(s[..., 3:] > 0, s[..., :3], 255).astype(np.uint8)).save(d / "sprite_bg.png")
    (d / "meta.json").write_text(json.dumps({"bg": [255, 255, 255]}))
    t = dump(d, 1, 1, 7, 7)
    assert t.splitlines()[0] == "@ 1 1" and "A #c81e1e" in t and t.splitlines()[-1] == "......"
    apply(d, t.replace("AAAA", "AB.A", 1).replace("---", "B #00ff00\n---"))
    r = np.array(Image.open(d / "sprite.png"))
    assert tuple(r[2, 3]) == (0, 255, 0, 255) and r[2, 4, 3] == 0 and tuple(r[2, 2, :3]) == (200, 30, 30)
    assert (d / "_historico" / "00" / "sprite.png").exists()
    assert tuple(np.array(Image.open(d / "sprite_bg.png"))[2, 4]) == (255, 255, 255)
    print("selftest ok")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["dump"] and len(a) == 6:
        sys.stdout.write(dump(Path(a[1]), *map(int, a[2:])))
    elif a[:1] == ["apply"] and len(a) == 3:
        apply(Path(a[1]), Path(a[2]).read_text(encoding="utf-8"))
    elif a == ["selftest"]:
        selftest()
    else:
        sys.exit(__doc__)
