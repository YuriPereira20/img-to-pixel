---
name: pixel-art
description: Turns a reference image into 64x64 pixel art with approval gates (description -> generated image -> export) and saves HTML/PNG/SVG, with and without background, under output/. Use when the user sends a reference image and asks for pixel art ("transforma em pixel art", "pixel art 64x64", "/pixel-art").
---

# Pixel art 64x64 com aprovação

`$S` = pasta dos scripts: `${CLAUDE_PLUGIN_ROOT}/scripts` (plugin instalado no Claude). Se essa variável aparecer sem expandir, ou se você for o Codex rodando dentro do repositório, use `plugins/img-to-pixel/scripts`.
Requer Python 3.10+ com `pillow` e `numpy` (`pip install pillow numpy`) e, no Claude, o Codex CLI logado. Saída: `output/<nome>/` (nome curto em kebab-case, derivado do assunto).
Fale com o usuário em português. **Nunca avance de etapa sem aprovação explícita.**

## 1. Referência -> descrição  (modelo pequeno)
- Peça o caminho da imagem de referência se não veio. Copie-a para `output/<nome>/reference.<ext>`.
- Gere a descrição com um modelo barato:
  - **Claude:** use o agente `pixel-describer` (Haiku) passando o caminho da imagem.
  - **Codex:** se puder abrir sub-agente, use um modelo menor/rápido para isso; senão descreva você mesmo.
- A descrição é **em inglês e só do assunto** (identidade, traços, roupas, cores em hex, o que não inventar). Estilo, grid e fundo NÃO entram nela: ficam no prompt fixo de `codex_gen.py`.
- Salve em `output/<nome>/description.md`, mostre ao usuário (resuma em português) e pergunte: aprovar, editar ou refazer. Repita até aprovar.

## 2. Gerar variações  (melhor modelo)
A descrição (`description.md`) fala só do ASSUNTO, em inglês (o gerador entende melhor). O ESTILO fica no prompt fixo do script (`build_prompt` em `$S/codex_gen.py`): grid nativo 64x64, formas limpas, contorno escuro, cel shading 3 tons, fundo #FF00FF.
- Pergunte se há imagem de ESTILO; se houver, salve como `output/<nome>/style.<ext>`.
- Lição aprendida: anexar a referência do assunto que for um cartoon plano puxa o resultado para o plano. Com imagem de estilo, prefira descrever o assunto em texto e NÃO passar `--ref`; use `--ref` só se a semelhança estiver se perdendo.
- **Claude:** NÃO gere imagem você mesmo. Rode em background (1–3 min):
  `python $S/codex_gen.py output/<nome>/vN --prompt-file output/<nome>/description.md --style output/<nome>/style.<ext> --n 3`
  Gera `vN/generated_1..3.png` em paralelo e salva o prompt usado em `vN/prompt_final.txt`. Modelo padrão `gpt-6-astra`.
- **Codex:** pegue o prompt pronto com o mesmo comando + `--print-prompt` (só imprime, não gera) e gere 3 imagens com sua ferramenta nativa usando esse texto, com a imagem de estilo anexada por último. Copie os PNGs novos de `~/.codex/generated_images/` para `output/<nome>/vN/generated_1..3.png`.
- Converta cada variação (a resolução nativa é estimada e ampliada exata para 64):
  `python $S/pixelize.py preview output/<nome>/vN/generated_K.png output/<nome>/vN/K`
  Cada `vN/K/` recebe `sprite.png` (64x64, sem fundo), `sprite_bg.png`, `preview.png`.

## 3. Escolher e aprovar
- Olhe você mesmo cada `preview.png` primeiro e descarte as quebradas (fundo não removido, assunto errado, pixels irregulares). Mostre as boas lado a lado e peça para o usuário escolher uma.
- Se nenhuma servir: pergunte O QUE está ruim, ajuste `description.md` (assunto) ou o bloco STYLE de `build_prompt` (estilo), e gere `vN+1`. Nunca sobrescreva versões anteriores.
- Com a escolhida: copie `vN/K/*` para `output/<nome>/` (é dali que o export lê).

## 3b. Retoques  (direto no agente, SEM gerar imagem)
Regra: o gerador de imagem (Codex) só faz a imagem BASE. Qualquer correção depois disso (olhos, brilhos, dentes, um pixel sobrando, cor errada) é feita pelo próprio agente — no Claude, pelo Claude — editando os pixels do sprite. Detalhes minúsculos sempre se perdem ao reduzir para 64x64; regerar não resolve.
1. Mapeie a região (coordenadas do grid; x1/y1 exclusivos):
   `python $S/pixels.py dump output/<nome> <x0> <y0> <x1> <y1> > output/<nome>/retoque.txt`
   Se não souber a região, gere um recorte ampliado do `sprite_bg.png` com régua para achar as coordenadas.
2. Edite `retoque.txt`: troque letras do grid; para cor nova, acrescente `X #rrggbb` na legenda (antes do `---`); `.` = transparente. Reaproveite as cores existentes do sprite sempre que possível. Pense no desenho em pixel art: contorno escuro de 1px, 2–3 tons, simetria quando o rosto for frontal.
3. Aplique: `python $S/pixels.py apply output/<nome> output/<nome>/retoque.txt`
   Atualiza `sprite.png`/`sprite_bg.png`/`preview.png`, guarda o estado anterior em `_historico/NN/` e gera `retoque.png` (antes|depois ampliado).
4. Olhe `retoque.png` você mesmo, ajuste se preciso, e mostre ao usuário para aprovar. Para desfazer, copie de volta os arquivos de `_historico/NN/`.

## 4. Exportar
- Pergunte o tamanho de cada pixel (`--cell`, px) e o espaçamento entre pixels (`--gap`, px). Padrão se o usuário não decidir: `--cell 8 --gap 0`.
  `python $S/pixelize.py export output/<nome> --cell <c> --gap <g>`
- Gera `pixel_c<c>_g<g>_com_fundo.{html,png,svg}` e `pixel_c<c>_g<g>_sem_fundo.{html,png,svg}`. No HTML cada pixel é um elemento do grid (64x64 = 4096 células) com o gap configurado.
- Pode rodar o export de novo com outro gap sem regerar a imagem.
- Termine listando os arquivos em `output/<nome>/`.
