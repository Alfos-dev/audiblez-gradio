#!/usr/bin/env bash
#
# install-audiblez.sh
#
# Instala o Audiblez (Kokoro-82M TTS para audiolivros) em um ambiente
# virtual Python isolado, sem alterar o Python padrão do sistema.
#
# Testado em Fedora 44 (KDE). Idempotente: pode ser rodado mais de uma
# vez sem quebrar nada.

set -euo pipefail

# --- Configuração ---------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_VERSION="3.12"
VENV_DIR="${HOME}/audiblez-env"
BOOKS_DIR="${HOME}/livros"
OUTPUT_DIR="${HOME}/audiolivros"

# Por padrão só instala o CLI (mais rápido).
# Passe --with-gui para instalar também a interface web em Gradio
# (roda no navegador, 100% Python -- não precisa compilar nada em C++).
WITH_GUI=false
for arg in "$@"; do
    if [ "$arg" == "--with-gui" ]; then
        WITH_GUI=true
    fi
done

# --- Cores para mensagens --------------------------------------------
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[AVISO]${NC} $1"; }
error() { echo -e "${RED}[ERRO]${NC} $1"; }

# --- 1. Verificar se está no Fedora -----------------------------------
if ! command -v dnf &> /dev/null; then
    error "Este script foi feito para Fedora (usa dnf). Comando 'dnf' não encontrado."
    exit 1
fi

# --- 2. Instalar dependências de sistema ------------------------------
info "Verificando dependências de sistema (ffmpeg, espeak-ng, python${PYTHON_VERSION})..."

BASE_PACKAGES=(ffmpeg espeak-ng patch "python${PYTHON_VERSION}" "python${PYTHON_VERSION}-devel")

PACKAGES_TO_INSTALL=()

for pkg in "${BASE_PACKAGES[@]}"; do
    if ! rpm -q "$pkg" &> /dev/null; then
        PACKAGES_TO_INSTALL+=("$pkg")
    fi
done

if [ "$WITH_GUI" = true ]; then
    info "Modo --with-gui ativado: a GUI em Gradio (navegador) será instalada."
fi

if [ ${#PACKAGES_TO_INSTALL[@]} -gt 0 ]; then
    info "Instalando pacotes ausentes: ${PACKAGES_TO_INSTALL[*]}"
    sudo dnf install -y "${PACKAGES_TO_INSTALL[@]}"
else
    info "Todos os pacotes de sistema já estão instalados."
fi

# --- 3. Confirmar que o binário do Python existe ----------------------
PYTHON_BIN="python${PYTHON_VERSION}"

if ! command -v "$PYTHON_BIN" &> /dev/null; then
    error "O binário $PYTHON_BIN não foi encontrado mesmo após a instalação."
    error "Verifique se o pacote python${PYTHON_VERSION} existe na sua versão do Fedora."
    exit 1
fi

info "Usando $($PYTHON_BIN --version)"

# --- 4. Criar o ambiente virtual --------------------------------------
if [ -d "$VENV_DIR" ]; then
    warn "Ambiente virtual já existe em $VENV_DIR. Pulando criação."
else
    info "Criando ambiente virtual em $VENV_DIR..."
    "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# --- 5. Ativar o venv e instalar o Audiblez ---------------------------
info "Ativando ambiente virtual e instalando audiblez + dependências..."
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

pip install --upgrade pip
pip install audiblez
pip install langdetect

if [ "$WITH_GUI" = true ]; then
    info "Instalando gradio para a GUI web (navegador)..."
    if pip install gradio; then
        info "GUI (Gradio) instalada com sucesso."
    else
        error "Falha ao instalar gradio. O CLI continua funcionando normalmente."
        error "Você pode usar 'audiblez-run livro.epub -v af_sky' sem a GUI."
    fi
else
    info "Pulando instalação da GUI (use --with-gui para instalá-la depois)."
fi

# Copia a GUI Gradio para o home (referenciada pelos atalhos em scripts/)
if [ -f "${SCRIPT_DIR}/audiblez_gui.py" ]; then
    cp "${SCRIPT_DIR}/audiblez_gui.py" "${HOME}/audiblez_gui.py"
    info "GUI copiada para ${HOME}/audiblez_gui.py"
fi

deactivate

# --- 6. Aplicar patches do fork no audiblez instalado ------------------
# O audiblez (PyPI 0.4.9) gera áudio MONO (só toca no fone esquerdo) e
# arquivos PCM gigantes. Este patch re-encoda para AAC estéreo 192k e
# adiciona detecção de idioma por frase (a mesma voz lê trechos em
# pt/en/es/fr/it/hi com a fonética correta de cada idioma).
PATCH_FILE="${SCRIPT_DIR}/patches/audiblez-core.patch"
SITE_PACKAGES="$(find "$VENV_DIR" -maxdepth 4 -type d -name site-packages 2>/dev/null | head -1)"

if [ -n "$SITE_PACKAGES" ] && [ -f "$PATCH_FILE" ]; then
    if command -v patch &> /dev/null; then
        if (cd "$SITE_PACKAGES" && patch -p1 --forward --dry-run < "$PATCH_FILE" >/dev/null 2>&1); then
            (cd "$SITE_PACKAGES" && patch -p1 --forward < "$PATCH_FILE")
            info "Patch aplicado: áudio estéreo AAC + leitura multidioma com a mesma voz."
        else
            warn "Patch não aplicado (já estava aplicado ou versão incompatível). Pulando."
        fi
    else
        warn "'patch' não encontrado. Instale o pacote 'patch' e rode o script de novo."
    fi
else
    warn "Patch ou site-packages não encontrado; instalação seguiu sem os fixes."
fi

# --- 8. Criar pastas de trabalho --------------------------------------
mkdir -p "$BOOKS_DIR" "$OUTPUT_DIR"
info "Pasta para colocar seus .epub: $BOOKS_DIR"
info "Pasta onde os audiolivros (.m4b) vão aparecer: $OUTPUT_DIR"

# --- 9. Criar scripts de atalho -----------------------------------------
mkdir -p "${HOME}/.local/bin"

if [ -d "${SCRIPT_DIR}/scripts" ]; then
    cp "${SCRIPT_DIR}/scripts/audiblez-run" "${HOME}/.local/bin/audiblez-run"
    cp "${SCRIPT_DIR}/scripts/audiblez-gui" "${HOME}/.local/bin/audiblez-gui"
    chmod +x "${HOME}/.local/bin/audiblez-run" "${HOME}/.local/bin/audiblez-gui"
    info "Atalhos copiados de scripts/ para ~/.local/bin"
else
    LAUNCHER="${HOME}/.local/bin/audiblez-run"
    cat > "$LAUNCHER" << EOF
#!/usr/bin/env bash
# Atalho gerado automaticamente por install-audiblez.sh
source "${VENV_DIR}/bin/activate"

if [ "\$1" == "gui" ]; then
    shift
    audiblez-ui "\$@"
else
    audiblez "\$@"
fi
EOF
    chmod +x "$LAUNCHER"
    info "Atalho criado em $LAUNCHER"
fi

if [[ ":$PATH:" != *":${HOME}/.local/bin:"* ]]; then
    warn "~/.local/bin não está no seu PATH."
    warn "Adicione esta linha ao final do seu ~/.bashrc e reabra o terminal:"
    echo '    export PATH="$HOME/.local/bin:$PATH"'
fi

# --- 10. Resumo final ----------------------------------------------------
echo ""
info "Instalação concluída!"
echo ""
echo "Como usar (via terminal, sem GUI):"
echo "  audiblez-run livro.epub -v pf_dora -o \"$OUTPUT_DIR\""
echo ""
if [ "$WITH_GUI" = true ]; then
echo "Se a GUI foi instalada com sucesso:"
echo "  audiblez-gui"
echo "  # abre a interface em http://127.0.0.1:7860"
echo ""
else
echo "GUI não instalada (rode com --with-gui se quiser instalá-la depois)."
echo ""
fi
echo "Coloque seus arquivos .epub em: $BOOKS_DIR"
echo "Os audiolivros prontos (.m4b) vão para: $OUTPUT_DIR"
