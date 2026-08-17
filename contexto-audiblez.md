# Contexto: Configuração do Kokoro-82M / Audiblez para Audiolivros

## Objetivo
Rodar o **Kokoro-82M** (modelo de TTS leve, 82M parâmetros) com interface gráfica,
para **narração de livros médios e grandes em audiolivros**.

## Hardware / Ambiente
- **CPU:** Ryzen 7 5700X
- **GPU:** RX 6600M (AMD, `gfx1032` — não suportada oficialmente pelo ROCm)
- **RAM:** 16 GB DDR4
- **SO:** Fedora 44 (KDE Plasma)

---

## 1. Ferramenta escolhida: Audiblez

Depois de avaliar opções (Kokoro-FastAPI, Kokoro-TTS-Local, ttsforge, pdf-narrator),
o **[Audiblez](https://github.com/santinic/audiblez)** foi escolhido por:
- Converter `.epub` direto em `.m4b` com capítulos
- Ter CLI **e** GUI (wxPython)
- Permitir escolher/pular capítulos (`--pick`)
- Ser mantido, com WAVs intermediários por capítulo (retomada parcial em caso de falha)

**Licença:** MIT — fork e modificação são permitidos livremente.

### Sobre a GPU
A RX 6600M (`gfx1032`) não é suportada oficialmente pelo ROCm. Há relatos de
instabilidade (SIGSEGV) mesmo forçando `HSA_OVERRIDE_GFX_VERSION=10.3.0`. Como o
Kokoro-82M é pequeno, decidiu-se rodar em **CPU** — mais lento, porém confiável.
Referência de velocidade: ~60 caractere/s em CPU (M2), ~600 carac./s em GPU CUDA (T4).

---

## 2. Problema: incompatibilidade de versão do Python

O Fedora 44 vem com Python 3.13/3.14 por padrão, mas o `audiblez` (via dependência
`misaki`) exige `Python <3.13`. Duas soluções foram avaliadas:

| Opção | Prós | Contras |
|---|---|---|
| **Instalar Python 3.12 via `dnf` + venv** (escolhida) | Segura, oficial, reversível | Precisa manter o venv sempre ativo |
| Fork do repositório + relaxar `requires-python` | Evita instalar Python extra | Depende de versão mais antiga/não testada do `misaki`; ainda precisa de venv |

O Fedora empacota várias versões do Python em paralelo sem conflito com a padrão do
sistema — `sudo dnf install python3.12 python3.12-devel` não substitui nada.

---

## 3. Containerização (avaliada, não usada por fim)

Foi montado um `Dockerfile` alternativo com Python 3.12-slim + `audiblez` via pip,
para isolar totalmente do sistema host. Viável, mas a instalação nativa em venv foi
o caminho seguido na prática.

---

## 4. Script de instalação final

Criado `install-audiblez.sh`, idempotente, que:
1. Instala dependências de sistema (`ffmpeg`, `espeak-ng`, `python3.12`, `python3.12-devel`)
2. Cria venv em `~/audiblez-env`
3. Instala o `audiblez` (CLI sempre; GUI opcional via flag `--with-gui`)
4. Cria pastas `~/livros` (entrada) e `~/audiolivros` (saída)
5. Gera atalho `~/.local/bin/audiblez-run`

### Uso
```bash
./install-audiblez.sh              # CLI apenas
./install-audiblez.sh --with-gui   # tenta compilar também a GUI (wxPython)
```

---

## 5. Problema: falha ao compilar wxPython (1ª tentativa)

Sem `--with-gui`, a primeira tentativa de instalar `wxpython` falhou:
```
checking for gcc... no
configure: error: no acceptable C compiler found in $PATH
```
**Causa:** não existe wheel pré-compilado do wxPython para Fedora 44 (distro recente
demais); o pip tentou compilar o wxWidgets (C++) do zero e faltava o compilador.

**Solução:** o script foi ajustado para tornar a GUI **opcional** (`--with-gui`),
instalando `gcc`, `gcc-c++`, `make` e ~15 pacotes `-devel` (GTK, WebKit, SDL2, etc.)
somente quando solicitado. O CLI, que não depende de compilação C++, já funcionava
normalmente sem esses pacotes.

### Alternativa de GUI preparada como backup
Foi criado `audiblez_gui.py`, uma interface alternativa em **Gradio** (100% Python,
sem compilação), que chama o `audiblez` via `subprocess` e roda no navegador —
pronta para uso caso a compilação do wxPython falhasse ou fosse indesejada.

---

## 6. Segunda tentativa: `--with-gui` funcionou

Rodando `./install-audiblez.sh --with-gui`, todos os pacotes de build foram
instalados e o **wxPython compilou com sucesso** (`Successfully installed
pillow-12.3.0 wxpython-4.3.1`), sem nenhum pacote adicional faltando.

**Observação:** o `pip install audiblez` puxou a versão **CUDA** do `torch`
(bibliotecas Nvidia, ~3-4 GB) por ser o padrão do pip em Linux — irrelevante
numa GPU AMD, apenas ocupa espaço em disco à toa. Opcional trocar por CPU-only:
```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu --force-reinstall
```

---

## 7. Problema: GUI compilada, mas crasha ao abrir (SIGSEGV)

Ao rodar `audiblez-ui`, o processo morre com **Signal 11 (SEGV)**, 2 vezes seguidas.
A stack trace do coredump apontou a causa:

```
_gtk_css_color_value_resolve (libgtk-3.so.0)
gtk_css_node_validate_internal (repetido em loop)
...
Module libcolorreload-gtk-module.so from rpm kde-gtk-config
Module libwindow-decorations-gtk-module.so from rpm kde-gtk-config
```

**Diagnóstico:** o `kde-gtk-config` (componente do Plasma que injeta o tema Breeze
dinamicamente em apps GTK3) está causando um loop/erro na resolução de cor CSS —
um problema conhecido de integração KDE Plasma ↔ GTK3, não um bug do Audiblez.

### Correção aplicada
O launcher `audiblez-run` foi atualizado para forçar um tema GTK estático e
desabilitar a injeção de módulos do Plasma antes de abrir a GUI:

```bash
export GTK_THEME=Adwaita
unset GTK_MODULES
```

### Teste rápido (sem reinstalar)
```bash
source ~/audiblez-env/bin/activate
GTK_THEME=Adwaita GTK_MODULES= audiblez-ui
```

### Se persistir
Testar forçar X11 em vez de Wayland:
```bash
GTK_THEME=Adwaita GTK_MODULES= GDK_BACKEND=x11 audiblez-ui
```
Se nada resolver, usar o backup em Gradio (`audiblez_gui.py`), imune a esse tipo
de problema por rodar no navegador.

**Status atual:** a GUI wxPython foi **abandonada** (SIGSEGV persistiu). A
**interface Gradio foi adotada como solução definitiva** e está funcionando.

---

## 8. Arquivos gerados nesta conversa

| Arquivo | Descrição |
|---|---|
| `install-audiblez.sh` | Script principal de instalação (Python 3.12 + venv + audiblez + GUI opcional + fix de tema GTK) |
| `audiblez_gui.py` | GUI em Gradio (em `~/audiblez_gui.py`), **solução definitiva** — vozes, mistura de vozes, tom de narração e pitch |
| `audiblez-gui` | Atalho em `~/.local/bin/audiblez-gui` para iniciar a GUI Gradio |
| `Dockerfile` | Imagem Docker alternativa (avaliada, não usada na prática) |

---

## 9. Comandos de uso do dia a dia

```bash
# Via CLI
audiblez-run livro.epub -v af_sky -s 1.0 -o ~/audiolivros

# Via GUI Gradio (solução atual)
audiblez-gui
# abre em http://127.0.0.1:7860
```

Vozes em português brasileiro disponíveis no Kokoro: `pf_dora`, `pm_alex`, `pm_santa`.

---

## 10. Fix: áudio mono (só no lado esquerdo) + arquivos gigantes

O `audiblez` gravava cada capítulo em WAV **mono** (Kokoro gera mono) e o
`ffmpeg` copiava o PCM sem compactar. Resultado: `.m4b` em `pcm_s16le` mono
(~105 MB para um livro), que muitos players reproduzem só no fone esquerdo.

**Correção aplicada em `audiblez/core.py`** (função `concat_wavs_with_ffmpeg`):
re-encodificar para **AAC estéreo** duplicando o canal mono:
```python
subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', wav_list_txt,
                '-c:a', 'aac', '-b:a', '192k', '-ac', '2', concat_file_path])
```
Resultado: áudio nos dois fones, estéreo (canal duplicado), e arquivo final
~10x menor. Obs.: é um patch no pacote instalado no venv — reaplicar após
`pip install --upgrade audiblez`. A GUI e a CLI usam o mesmo `core.py`, então
ambas são corrigidas.

### Correções posteriores (filtro de tom + bugs do m4b)
1. **Áudio duplicado no m4b com capa** — `create_m4b` usava `-map 0` + `-map 0:a`
   (da capa), gerando **2 streams de áudio** no mesmo arquivo. Removido o
   `-map 0:a` redundante em `core.py`.
2. **Filtro de tom (`apply_tone_filter` da GUI)** — falhava com erro 183 por
   dois motivos: (a) `-map 0` tentava copiar o track `bin_data` (capítulos)
   que o ffmpeg rejeita → agora mapeia só `0:a:0` e `0:v:0?` (capítulos são
   preservados como metadados); (b) o arquivo temporário `.m4b.tmp` não era
   reconhecido pelo ffmpeg → agora `.tmp.m4b` + `-f mp4`. Escrita passou a
   ser atômica (`replace`), sem deixar arquivo de 0 bytes em caso de falha.

---

## 11. Tom de narração (emoções) e vozes

### Controle de emoção
O **Kokoro-82M não tem controle nativo de emoção** (verificado no código:
`KPipeline.__call__` só aceita `text`, `voice`, `speed`, `split_pattern`, `model`).

Para obter tom "triste, feliz, assustado, raiva, indignado", a GUI aplica
**filtros de áudio via ffmpeg no resultado final** (pitch, velocidade, EQ,
reverb/tremolo), simulando a emoção:

| Preset | Efeito aproximado |
|---|---|
| Triste | tom -1.5 st, mais lento, lowpass 3.2 kHz, eco sutil |
| Feliz | tom +2 st, mais rápido, agudos realçados |
| Assustado | tom +3 st, mais rápido, tremolo |
| Raiva | tom -1 st, mais rápido, graves reforçados, mais alto |
| Indignado | tom +1 st, mais rápido, agudos e volume |

Há também um **slider de deslocamento de tom** (semitons, -6 a +6) que se
combina com o preset. Limitação: é aproximação de áudio, não expressão real
do modelo.

### Vozes em PT-BR
O modelo só tem **3 vozes PT-BR** (`pf_dora` F, `pm_alex` M, `pm_santa` M) —
confirmado na `VOICES.md` oficial. Não há outras vozes PT-BR no Kokoro.

**Mistura de vozes:** o Kokoro permite **misturar vozes** (média dos embeddings
via `voice="voz1,voz2"`). A GUI expõe isso: escolha uma voz e "misturar com",
gerando um **novo timbre** (ex.: `pf_dora,pm_alex`). Isso amplia as opções
sem treinar nada. (Japonês/mandarim não aparecem na GUI: exigem
`misaki[ja]`/`misaki[zh]`.)
