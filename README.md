#  Audiblez Gradio — Audiolivros com Kokoro-82M em português

Converte `.epub` em `.m4b` (com capítulos) usando o modelo de TTS
[Kokoro-82M](https://github.com/hexgrad/kokoro), com uma **interface web
(Gradio)** e melhorias em relação ao `audiblez` original.

## Recursos

- **GUI web (Gradio)** em http://127.0.0.1:7860 — 100% Python, sem compilar nada
- **Todas as vozes** dos idiomas suportados pelo `misaki` instalado
- **Mistura de vozes** (média 50/50 dos embeddings) — cria novos timbres
- **Tom de narração**: triste, feliz, assustado, raiva, indignado (simulado
  via filtros de áudio ffmpeg — o Kokoro não tem emoção nativa) + slider de
  **deslocamento de tom** (semitons)
- **Fix do áudio mono**: o `audiblez` original gerava `.m4b` em PCM mono (só
  tocava no fone esquerdo e ocupava ~10x mais disco). Este repositório corrige
  para **AAC estéreo 192k** via [patch](patches/audiblez-core.patch).
- **Leitura multidioma com a mesma voz**: nomes de pessoas, lugares e citações
  em inglês (ou es, fr, it, hi) são lidos com a **mesma voz** mas com a
  **fonética correta de cada idioma** — o idioma é detectado por frase
  ([`langdetect`](https://pypi.org/project/langdetect/)). Todas as pipelines
  compartilham o mesmo modelo, então o timbre fica consistente do início ao fim.
- **Prévia da voz** na GUI: ouça um trecho curto com a voz, mistura, tom e
  pitch escolhidos antes de converter o livro inteiro.

## Instalação (Fedora)

```bash
git clone https://github.com/Alfos-dev/audiblez-gradio
cd audiblez-gradio

./install-audiblez.sh              # CLI
./install-audiblez.sh --with-gui   # + GUI web (Gradio)
```

O script:
1. Instala `ffmpeg`, `espeak-ng`, `patch`, `python3.12` (+devel)
2. Cria o venv em `~/audiblez-env` e instala o `audiblez` via pip (+`langdetect`)
3. **Aplica o patch** de áudio estéreo e leitura multidioma no `core.py` instalado
4. Cria `~/livros` (entrada) e `~/audiolivros` (saída)
5. Gera os atalhos `audiblez-run` (CLI) e `audiblez-gui` (GUI web)

> O patch é reaplicado automaticamente a cada execução; se você der
> `pip install --upgrade audiblez`, basta rodar o script de novo.

## Uso

```bash
# CLI
audiblez-run livro.epub -v pf_dora -o ~/audiolivros

# GUI web
audiblez-gui
# abre em http://127.0.0.1:7860
```

Vozes PT-BR: `pf_dora` (F), `pm_alex` (M), `pm_santa` (M).

## Correções aplicadas ao audiblez (fork)

O fork [Alfos-dev/audiblez](https://github.com/Alfos-dev/audiblez) (base
`v0.4.9`) contém 3 commits:

1. `concat_wavs_with_ffmpeg` re-encoda para **AAC estéreo 192k** (antes: cópia
   de PCM mono). Usa o encoder nativo `aac` (portável), não `libfdk_aac`.
2. `create_m4b` remove o `-map 0:a` redundante que **duplicava o stream de
   áudio** quando havia capa no livro.
3. `make_lang_pipelines` + `detect_lang_code`: **detecção de idioma por
   frase** (pt/en/es/fr/it/hi via `langdetect`). Cada idioma ganha uma
   `KPipeline` própria que compartilha o mesmo `KModel`, então a mesma voz lê
   o livro inteiro com o timbre consistente e a fonética certa em cada idioma.
   Sem `langdetect` instalado, o comportamento volta ao original (a voz só lê
   o idioma dela).

> Idioma x voz: as vozes do Kokoro têm um idioma "nativo" (o prefixo), mas são
> embeddings de estilo sobre um modelo compartilhado — por isso podem ser
> usadas em qualquer pipeline. Não existem "vozes multidiomas" oficiais; o
> resultado é a mesma voz com a pronúncia correta de cada língua detectada.

## Atribuições e licenças

| Componente | Licença | Detalhes |
|---|---|---|
| [Audiblez](https://github.com/santinic/audiblez) | MIT | © Claudio Santini 2025 — fork/modificações preservam a licença |
| [Kokoro-82M](https://github.com/hexgrad/kokoro) | Apache 2.0 | Modelo TTS; pesos baixados do Hugging Face na 1ª execução |
| [Gradio](https://gradio.app) | Apache 2.0 | Framework da interface web (dependência pip) |
| Este repositório (`audiblez_gui.py`, script, docs) | MIT | © 2026 Alfos-dev |

O `patches/audiblez-core.patch` é derivado do código MIT do audiblez — a
licença MIT do upstream é preservada no fork.

## Hardware recomendado

CPU é suficiente (o Kokoro é leve, 82M parâmetros). Em uma CPU moderna espere
~50-60 caracteres/s. GPUs AMD (ex.: RX 6600M) não são suportadas pelo ROCm;
GPUs NVIDIA com CUDA funcionam com `-c`.

---

_Status de desenvolvimento: em uso pessoal. Bugs e PRs são bem-vindos._
