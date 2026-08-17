"""
audiblez_gui.py

Interface gráfica para o Audiblez (Kokoro-82M TTS) feita com Gradio.

Recursos:
  - Conversão de .epub em .m4b (com capítulos)
  - Todas as vozes do Kokoro disponíveis no misaki instalado
  - Mistura de vozes (média dos embeddings -> novos timbres)
  - Tom de narração (triste, feliz, assustado, raiva, indignado...)
    via filtros de áudio ffmpeg aplicados no resultado final
  - Controle manual de deslocamento de tom (semitons)

Uso:
    source ~/audiblez-env/bin/activate
    python audiblez_gui.py

Depois abra o link http://127.0.0.1:7860 que aparecer no terminal.
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

import gradio as gr

OUTPUT_DIR = Path.home() / "audiolivros"
OUTPUT_DIR.mkdir(exist_ok=True)

SAMPLE_RATE = 24000  # taxa nativa do Kokoro

# Vozes disponíveis (idiomas suportados pelo misaki/espeak instalado;
# japonês e mandarim precisam de misaki[ja]/[zh] e ficam de fora).
VOICES = {
    "🇧🇷 Português (BR)": ["pf_dora", "pm_alex", "pm_santa"],
    "🇺🇸 Inglês (EUA)": [
        "af_alloy", "af_aoede", "af_bella", "af_heart", "af_jessica",
        "af_kore", "af_nicole", "af_nova", "af_river", "af_sarah", "af_sky",
        "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam", "am_michael",
        "am_onyx", "am_puck", "am_santa",
    ],
    "🇬🇧 Inglês (UK)": [
        "bf_alice", "bf_emma", "bf_isabella", "bf_lily",
        "bm_daniel", "bm_fable", "bm_george", "bm_lewis",
    ],
    "🇪🇸 Espanhol": ["ef_dora", "em_alex", "em_santa"],
    "🇫🇷 Francês": ["ff_siwis"],
    "🇮🇳 Hindi": ["hf_alpha", "hf_beta", "hm_omega", "hm_psi"],
    "🇮🇹 Italiano": ["if_sara", "im_nicola"],
}

# Presets de tom. Cada preset define um deslocamento de tom (semitons),
# uma velocidade extra e filtros de áudio aplicados ao resultado final.
# Obs: o Kokoro-82M não tem controle nativo de emoção; estes presets
# simulam o tom usando pitch/velocidade/equalização/efeitos via ffmpeg.
PRESETS = {
    "Neutro": {"st": 0.0, "speed": 1.0, "filters": []},
    "Triste": {"st": -1.5, "speed": 0.95, "filters": ["lowpass=f=3200", "aecho=0.8:0.5:80:0.3"]},
    "Feliz": {"st": 2.0, "speed": 1.05, "filters": ["highpass=f=80", "treble=g=4"]},
    "Assustado": {"st": 3.0, "speed": 1.06, "filters": ["tremolo=f=4:d=0.35"]},
    "Raiva": {"st": -1.0, "speed": 1.08, "filters": ["bass=g=8", "volume=1.3"]},
    "Indignado": {"st": 1.0, "speed": 1.1, "filters": ["highpass=f=100", "treble=g=3", "volume=1.25"]},
}


def build_audio_filter(tone, pitch_st):
    """Monta a cadeia de filtros ffmpeg para o tom + pitch manual."""
    p = PRESETS[tone]
    total_st = p["st"] + float(pitch_st)
    factor = 2 ** (total_st / 12)
    chain = []
    if abs(total_st) > 0.001:
        chain.append(f"asetrate={SAMPLE_RATE}*{factor:.5f}")
        chain.append(f"aresample={SAMPLE_RATE}")
        chain.append(f"atempo={1 / factor:.5f}")
    if p["speed"] != 1.0:
        chain.append(f"atempo={p['speed']:.3f}")
    chain.extend(p["filters"])
    return ",".join(chain)


def apply_tone_filter(m4b_in, m4b_out, tone, pitch_st):
    """Re-encoda o .m4b aplicando os filtros de tom, preservando capítulos e capa."""
    chain = build_audio_filter(tone, pitch_st)
    if not chain:
        shutil.move(str(m4b_in), str(m4b_out))
        return
    tmp_out = Path(str(m4b_out) + ".tmp.m4b")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(m4b_in),
        "-map", "0:a:0", "-map", "0:v:0?",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-af", chain,
        "-movflags", "+faststart",
        "-f", "mp4",
        str(tmp_out),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        tmp_out.unlink(missing_ok=True)
        raise RuntimeError("Falha ao aplicar o tom de narração:\n" + (proc.stderr or proc.stdout)[-2000:])
    tmp_out.replace(str(m4b_out))


def convert_epub(epub_file, voice, blend_voice, speed, tone, pitch_st, progress=gr.Progress(track_tqdm=True)):
    if epub_file is None:
        return "Nenhum arquivo enviado.", None

    epub_path = Path(epub_file)
    voice_arg = f"{voice},{blend_voice}" if blend_voice else voice

    progress(0, desc="Iniciando conversão...")

    with tempfile.TemporaryDirectory() as tmpdir:
        cmd = [
            "audiblez",
            str(epub_path),
            "-v", voice_arg,
            "-s", str(speed),
            "-o", tmpdir,
        ]

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        log_lines = []
        for line in process.stdout:
            log_lines.append(line.rstrip())
            progress(0.5, desc=line.strip()[:60])

        process.wait()

        if process.returncode != 0:
            return "\n".join(log_lines[-40:]), None

        m4b_files = list(Path(tmpdir).glob("*.m4b"))
        if not m4b_files:
            return "Conversão terminou, mas nenhum .m4b foi encontrado.\n" + "\n".join(log_lines[-40:]), None

        progress(0.9, desc="Aplicando tom de narração...")
        final_path = OUTPUT_DIR / m4b_files[0].name
        apply_tone_filter(m4b_files[0], final_path, tone, pitch_st)

        progress(1.0, desc="Concluído!")
        return f"Concluído! Salvo em: {final_path}", str(final_path)


# --- Interface ---------------------------------------------------------
all_voices = [v for lang in VOICES.values() for v in lang]

with gr.Blocks(title="Audiblez GUI (Gradio)") as demo:
    gr.Markdown("# 📚 Audiblez -- EPUB para Audiolivro (Kokoro-82M)")
    gr.Markdown(
        "Envie um `.epub`, escolha a voz, o tom e a velocidade, e gere o "
        "audiolivro em `.m4b`. Em CPU isso pode levar bastante tempo para "
        "livros grandes -- acompanhe o progresso abaixo."
    )

    with gr.Row():
        with gr.Column():
            epub_input = gr.File(label="Arquivo .epub", file_types=[".epub"])
            voice_input = gr.Dropdown(
                choices=all_voices, value="pf_dora", label="Voz"
            )
            blend_input = gr.Dropdown(
                choices=["Nenhuma"] + all_voices, value="Nenhuma",
                label="Misturar com (cria um novo timbre)",
                info="Média 50/50 dos embeddings das duas vozes.",
            )
            tone_input = gr.Dropdown(
                choices=list(PRESETS.keys()), value="Neutro",
                label="Tom de narração",
                info="Simula a emoção via pitch/velocidade/filtros (o Kokoro não tem emoção nativa).",
            )
            pitch_input = gr.Slider(
                minimum=-6, maximum=6, value=0, step=0.5,
                label="Deslocamento de tom extra (semitons)",
            )
            speed_input = gr.Slider(
                minimum=0.5, maximum=2.0, value=1.0, step=0.1,
                label="Velocidade",
            )
            convert_btn = gr.Button("Converter", variant="primary")

        with gr.Column():
            status_output = gr.Textbox(label="Status / Log", lines=15)
            file_output = gr.File(label="Audiolivro gerado (.m4b)")

    convert_btn.click(
        fn=convert_epub,
        inputs=[epub_input, voice_input, blend_input, speed_input, tone_input, pitch_input],
        outputs=[status_output, file_output],
    )

if __name__ == "__main__":
    demo.queue().launch()