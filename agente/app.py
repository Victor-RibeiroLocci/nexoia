"""NexoIA: chat em Streamlit com o Gemini (Interactions API) e a tool verificar_datas, no padrão da Fase 3.

Execução:  pip install -r requirements.txt  ->  set GOOGLE_API_KEY=sua-chave  ->  streamlit run app.py
"""
import base64, html, json, logging, os, re
from datetime import date
from pathlib import Path

import streamlit as st
from google import genai
from google.genai import types

import ferramentas

# --- CONFIGURAÇÃO ---
PASTA = Path(__file__).parent
PASTA_PROMPTS, MASCOTE = PASTA / "SystemPrompt", PASTA / "mascote.svg"
MODELO_PADRAO = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
OPCAO_MANUAL = "✏️ Digitar manualmente"
MAX_ITERACOES_POR_TURNO = 5
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def listar_prompts():
    """Arquivos .md/.txt de SystemPrompt, do maior vN.N no nome para o menor (sem versão: por data, no fim)."""
    def versao(p):
        m = re.search(r"v(\d+(?:\.\d+)*)", p.stem, re.IGNORECASE)
        return (1, tuple(map(int, m.group(1).split("."))), 0) if m else (0, (), p.stat().st_mtime)
    return sorted((p for p in PASTA_PROMPTS.glob("*") if p.suffix.lower() in (".md", ".txt")), key=versao, reverse=True)


def rotulo(texto):
    st.markdown(f'<div class="nx-label">{texto}</div>', unsafe_allow_html=True)


st.set_page_config(page_title="NexoIA · Gemini", page_icon="✦", layout="centered")
if (PASTA / "estilo.css").exists():
    st.markdown(f"<style>{(PASTA / 'estilo.css').read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)
if not (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")):
    st.error("Defina a variável de ambiente GOOGLE_API_KEY (ou GEMINI_API_KEY) antes de iniciar.")
    st.stop()
# Cliente criado uma única vez. 429/5xx: nova tentativa com espera progressiva de 1s, 2s, 4s e 8s (respeitando Retry-After)
cliente = st.cache_resource(lambda: genai.Client(http_options=types.HttpOptions(
    retry_options=types.HttpRetryOptions(attempts=4, initial_delay=1, max_delay=60))))()

# --- BARRA LATERAL ---
with st.sidebar:
    st.markdown('<div class="nx-side-brand"><span>NEXO//IA</span> · controle</div>', unsafe_allow_html=True)
    rotulo("Modelo")
    modelo = st.text_input("Modelo", value=MODELO_PADRAO, label_visibility="collapsed")
    rotulo("System prompt")
    prompts = listar_prompts()
    escolha = st.selectbox("System prompt", [p.name for p in prompts] + [OPCAO_MANUAL], label_visibility="collapsed",
                           format_func=lambda n: f"{n}  (mais recente)" if prompts and n == prompts[0].name else n,
                           help=f"Arquivos lidos de: {PASTA_PROMPTS}")
    if escolha == OPCAO_MANUAL:
        if not prompts:
            st.caption(f"Nenhum arquivo .md/.txt encontrado em `{PASTA_PROMPTS}`.")
        instrucao_sistema = st.text_area("Instrução de sistema", value="Você é um assistente útil. Responda em português do Brasil.")
    else:
        instrucao_sistema = (PASTA_PROMPTS / escolha).read_text(encoding="utf-8-sig", errors="replace")
        with st.expander("Ver conteúdo do prompt"):
            st.markdown(instrucao_sistema)
    rotulo("Ferramentas")
    tools_ativas = st.toggle("verificar_datas (feriados)", value=True,
                             help="Permite ao agente consultar feriados nacionais (BrasilAPI) para validar a temporalidade.")
    rotulo("Temperatura")
    temperatura = st.slider("Temperatura", 0.0, 2.0, 0.0, 0.1, label_visibility="collapsed")
    rotulo("Ações")
    col1, col2 = st.columns(2)
    if col1.button("↻ Prompts", help="Relê a pasta SystemPrompt", use_container_width=True):
        st.rerun()
    if col2.button("＋ Nova", help="Limpa o histórico e começa outra conversa", use_container_width=True):
        st.session_state.pop("assinatura", None)
        st.rerun()

# --- ESTADO: o histórico fica no Gemini, encadeado por previous_interaction_id; trocar modelo, prompt ou tool reinicia ---
if st.session_state.get("assinatura") != (modelo, instrucao_sistema, tools_ativas):
    st.session_state.update(assinatura=(modelo, instrucao_sistema, tools_ativas), mensagens=[], sessao={"previous_interaction_id": None})


# --- CICLO DO AGENTE (Cap. 5): o LLM decide, o Python valida e executa, o resultado volta ao LLM ---
def atender(mensagem, sessao):
    hoje = date.today()  # o modelo precisa da data para converter "novembro" em 2026-11-..
    data_de_hoje = f"\n\n# DATA DE HOJE\n{hoje:%Y-%m-%d} ({ferramentas.DIAS[hoje.weekday()]}{'-feira' * (hoje.weekday() < 5)})" if tools_ativas else ""
    # system_instruction, tools e generation_config valem só para a chamada: são reenviados em todas
    config = {"model": modelo, "system_instruction": instrucao_sistema + data_de_hoje if instrucao_sistema else None,
              "generation_config": {"temperature": temperatura}, **({"tools": ferramentas.tools} if tools_ativas else {})}
    anterior, entrada, acoes = sessao["previous_interaction_id"], mensagem, []
    for _ in range(MAX_ITERACOES_POR_TURNO):
        interaction = cliente.interactions.create(input=entrada, previous_interaction_id=anterior, **config)
        anterior = interaction.id
        chamadas = [passo for passo in interaction.steps or [] if passo.type == "function_call"]
        if not chamadas:  # resposta final: só agora a conversa avança
            sessao["previous_interaction_id"] = interaction.id
            return (interaction.output_text or "").strip() or "O fluxo terminou sem uma resposta textual.", acoes
        entrada = []
        for chamada in chamadas:  # trata também chamadas em paralelo
            logging.info("Tool solicitada: %s %s", chamada.name, chamada.arguments)
            resultado = ferramentas.executar_tool(chamada.name, chamada.arguments)
            acoes.append({"ferramenta": chamada.name, "parametros": chamada.arguments, "resultado": resultado})
            entrada.append({"type": "function_result", "name": chamada.name, "call_id": chamada.id,
                            "result": [{"type": "text", "text": json.dumps(resultado, ensure_ascii=False)}]})
    logging.warning("Limite de iterações atingido.")
    return "Não foi possível concluir este turno dentro do limite de execução.", acoes


# --- CABEÇALHO ---
AVATAR = str(MASCOTE) if MASCOTE.exists() else None
html_mascote = (f'<img class="nx-mascot" src="data:image/svg+xml;base64,{base64.b64encode(MASCOTE.read_bytes()).decode()}" '
                f'alt="Nexo, mascote da NexoIA">' if AVATAR else "")
st.markdown(f'<div class="nx-hero"><div class="nx-hero-text"><div class="nx-status"><span class="nx-dot"></span>online · gemini api</div>'
            f'<div class="nx-title">NexoIA</div><div class="nx-sub"><span class="nx-chip">modelo <b>{html.escape(modelo)}</b></span>'
            f'<span class="nx-chip">prompt <b>{html.escape("manual" if escolha == OPCAO_MANUAL else Path(escolha).stem)}</b></span>'
            f'<span class="nx-chip">temp <b>{temperatura:.1f}</b></span></div></div>{html_mascote}</div>', unsafe_allow_html=True)

# --- BOAS-VINDAS: prompts da NexoIA mostram os 8 campos da intenção ---
MODO_INTENCAO = "intenção" in instrucao_sistema.lower() and "8 campos" in instrucao_sistema.lower()
CAMPOS_INTENCAO = [
    ("Nome", "Como esta intenção será identificada.", "Lançamento Cartão Premium"),
    ("Produto / tema", "Sobre o que é a comunicação.", "novo cartão Premium"),
    ("Público", "Quem precisa receber a mensagem.", "clientes atuais que já têm cartão"),
    ("Objetivo", "O que a comunicação deve fazer ou mudar no comportamento do público.", "incentivar a solicitação do novo cartão"),
    ("Contexto", "O que está acontecendo ou motivando a comunicação.", "o produto será lançado no próximo mês"),
    ("Tipo", "Formato ou canal da comunicação.", "campanha de e-mail"),
    ("Temporalidade", "Quando ou em que período ela precisa acontecer.", "primeira semana do lançamento"),
    ("Critério de sucesso", "Como você vai saber se deu certo.", "5% de solicitações entre os impactados")]
EXEMPLO_COMPLETO = (
    "Quero comunicar clientes sobre o lançamento do novo cartão Premium. O público são clientes atuais que já possuem cartão. O objetivo é "
    "apresentar o novo cartão e incentivar a solicitação. O contexto é que o produto será lançado no próximo mês. Acho que o tipo ideal é uma "
    "campanha de e-mail. A comunicação deve acontecer na primeira semana do lançamento. Como critério de sucesso, provavelmente uma taxa de "
    "solicitação de pelo menos 5% entre os clientes impactados. O nome da intenção pode ser 'Lançamento Cartão Premium'.")
cartoes = "".join(f'<div class="nx-field"><div class="nx-field-head"><span class="nx-num">{i:02d}</span>{nome}</div><div class="nx-field-desc">{desc}</div>'
                  f'<div class="nx-field-ex">ex.: {ex}</div></div>' for i, (nome, desc, ex) in enumerate(CAMPOS_INTENCAO, start=1))
dica_datas = ('<div class="nx-tip"><span>◷</span><div><b>Datas verificadas:</b> informe a temporalidade com dia, período ou mês '
              '(ex.: "primeira semana de novembro") e eu confiro feriados nacionais e fins de semana.</div></div>' if tools_ativas else "")
aviso_vazio, usar_exemplo = st.empty(), False
if not st.session_state.mensagens:
    with aviso_vazio.container():
        if MODO_INTENCAO:
            st.markdown(f"""<div class="nx-welcome"><div class="nx-welcome-kicker">Cadastro de intenção de comunicação</div>
  <h3>Oi, eu sou o NexoIA! 👋 Transformo seu pedido em uma intenção clara e avaliável.</h3>
  <p class="nx-welcome-lead">Para registrar a intenção como <b class="nx-ok">COMPLETA</b>, preciso destes <b>8 campos</b>. Pode mandar tudo em uma mensagem ou aos poucos: eu pergunto o que faltar.</p>
  <div class="nx-grid">{cartoes}</div><div class="nx-tips">
    <div class="nx-tip"><span>≈</span><div><b>Não tem certeza?</b> Escreva "acho que…" ou "provavelmente…". O campo fica como <i>hipótese</i> e eu peço confirmação depois.</div></div>{dica_datas}
    <div class="nx-tip"><span>◐</span><div><b>Cores das respostas:</b> <b class="nx-c-ok">verde</b> = tudo certo · <b class="nx-c-warn">âmbar</b> = precisa da sua atenção · <b class="nx-c-err">vermelho</b> = erro a corrigir.</div></div>
    <div class="nx-tip"><span>»</span><div><b>Com pressa?</b> Dá para registrar incompleta. O que faltar fica listado como pendência.</div></div>
    <div class="nx-tip"><span>∅</span><div><b>Fora do escopo:</b> não escrevo o texto da comunicação e não avalio jurídico, risco ou compliance. Não envie dados pessoais.</div></div>
  </div></div><div class="nx-template-label">Modelo para copiar e preencher <span>· botão de copiar no canto do bloco</span></div>""", unsafe_allow_html=True)
            st.code("\n".join(f"{nome}: " for nome, _, _ in CAMPOS_INTENCAO), language=None)
            usar_exemplo = st.button("▶ Testar com um exemplo preenchido", use_container_width=True)
        else:
            st.markdown('<div class="nx-empty"><h3>Pronto para começar</h3><p>Digite sua pergunta abaixo. O histórico da conversa é mantido '
                        'enquanto a página estiver aberta.</p></div>', unsafe_allow_html=True)


# --- CHAMADAS DE TOOL: chip verde (sem conflito), amarelo (conflito) ou vermelho (erro) + JSON completo ---
def mostrar_chamadas(acoes):
    for acao in acoes:
        r, p = acao["resultado"], acao["parametros"]
        classe, veredito = (("nx-tool-err", f"erro: {r['erro']}") if "erro" in r else
                            ("nx-tool-warn", f"{len(r['conflitos'])} conflito(s) em {r['total_datas']} data(s)") if r["tem_conflito"] else
                            ("nx-tool-ok", f"sem conflitos · {r['total_datas']} data(s) livre(s)"))
        dias = p.get("dias_semana")
        dias = f" · {', '.join(dias) if isinstance(dias, list) else dias}" if dias else ""
        chamada = html.escape(f"{acao['ferramenta']}({p.get('data_inicio', '?')} → {p.get('data_fim', '?')}{dias})")
        st.markdown(f'<div class="nx-tool {classe}"><span class="nx-tool-tag">tool</span><code>{chamada}</code>'
                    f'<span class="nx-tool-res">{html.escape(veredito)}</span></div>', unsafe_allow_html=True)
        with st.expander("Ver chamada e resposta da API"):
            st.code(json.dumps(acao, ensure_ascii=False, indent=2), language="json")


# --- CORES DA RESPOSTA: verde = tudo certo · âmbar = precisa da sua atenção · vermelho = erro a corrigir ---
STATUS = re.compile(r"^[\s>#*_-]*status\W*?(completa|incompleta)\b.*$", re.IGNORECASE | re.MULTILINE)
SECAO = re.compile(r"^[\s>#*_-]*(pend[êe]ncias|perguntas|verifica[çc][ãa]o de datas|pr[óo]ximo passo)\b[*_]*\s*:?[*_]*", re.IGNORECASE | re.MULTILINE)
NENHUMA, ATENCAO = re.compile(r"\bnenhum", re.IGNORECASE), re.compile(r"confirm|corrig|ajust|fora do escopo|área responsável|compliance|jurídic", re.IGNORECASE)


def cor_das_datas(secao, acoes):
    """Usa o resultado real da tool no turno; sem tool, olha o texto (pedido de manter/ajustar = conflito)."""
    resultados = [a["resultado"] for a in acoes]
    if resultados:
        return "err" if any("erro" in r for r in resultados) else "warn" if any(r.get("tem_conflito") for r in resultados) else "ok"
    return "err" if re.search(r"não foi possível", secao, re.IGNORECASE) else "warn" if re.search(r"\b(manter|ajustar)\b", secao, re.IGNORECASE) else "ok"


def analisar_resposta(texto, acoes):
    """Separa a resposta do NexoIA pelas seções do prompt e define a cor de cada parte (None = fora do formato)."""
    status = STATUS.search(texto)
    if not status:
        return None
    corpo = texto[:status.start()] + texto[status.end():]
    inicios = [m.start() for m in SECAO.finditer(corpo)] + [len(corpo)]
    linhas = [lin for lin in corpo[:inicios[0]].splitlines() if lin.strip()]
    tabela = [[c.strip().replace("**", "") for c in lin.strip().strip("|").split("|")] for lin in linhas if lin.strip().startswith("|")]
    cab = [c.lower() for c in (tabela or [[]])[0]]
    iv, io = (next((i for i, c in enumerate(cab) if c.startswith(nome)), padrao) for nome, padrao in (("valor", 1), ("origem", 2)))
    campos = [(c[0], c[iv], c[io].lower()) for c in tabela[1:] if len(c) > max(iv, io) and not re.fullmatch(r"[\s:-]*", "".join(c))]
    r = {"completa": status.group(1).lower() == "completa", "campos": campos, "lacunas": [c for c, _, o in campos if o.startswith("lac")],
         "hipoteses": [c for c, _, o in campos if o.startswith("hip")]}
    soltas = [lin for lin in linhas if not lin.strip().startswith("|")]
    alteracoes = [lin for lin in soltas if "→" in lin or "->" in lin]
    r["blocos"] = [("texto", "\n".join(lin for lin in soltas if lin not in alteracoes))] + (
        [("warn", "**Alteração para confirmar**\n\n" + "\n\n".join(alteracoes))] if alteracoes else [])
    for a, b in zip(inicios, inicios[1:]):
        secao = SECAO.sub(lambda m: f"**{m.group(1)}:**", corpo[a:b].strip(), count=1)  # rótulo padronizado, na cor do bloco
        nome, primeira = SECAO.match(secao).group(1).lower()[:4], secao.splitlines()[0]
        cor = {"pend": "ok" if NENHUMA.search(primeira) else "warn", "perg": "info" if NENHUMA.search(primeira) else "warn",
               "veri": cor_das_datas(secao, acoes)}.get(nome, "warn" if r["hipoteses"] or ATENCAO.search(secao) else "ok" if r["completa"] else "info")
        r["blocos"].append((cor, secao))
    return r


def mostrar_resposta(texto, acoes, chave):
    def pontos(nomes):
        return "".join(f'<span class="nx-ponto">{html.escape(n)}</span>' for n in nomes)
    if (r := analisar_resposta(texto, acoes)) is None:
        return st.markdown(texto)
    aviso = ('<b>✓ Intenção COMPLETA</b><span class="nx-banner-sub">Tudo certo: os 8 campos foram registrados.</span>' if r["completa"]
             else '<b>⚠ Intenção INCOMPLETA</b><span class="nx-banner-sub">Precisa da sua atenção nos pontos abaixo.</span>')
    aviso += (f'<div>Pendências: {pontos(r["lacunas"])}</div>' if r["lacunas"] else "") + (
        f'<div>Confirme as hipóteses: {pontos(r["hipoteses"])}</div>' if r["hipoteses"] else "")
    st.markdown(f'<div class="nx-banner nx-banner-{"ok" if r["completa"] else "warn"}">{aviso}</div>', unsafe_allow_html=True)
    if r["campos"]:
        rotulos = {"fat": "fato", "hip": "hipótese · confirmar", "lac": "lacuna · pendente"}
        linhas = "".join(f'<tr class="nx-{o[:3]}"><td>{html.escape(c)}</td><td>{html.escape(v)}</td><td><span class="nx-origem">'
                         f'{rotulos.get(o[:3], html.escape(o))}</span></td></tr>' for c, v, o in r["campos"])
        st.markdown(f'<table class="nx-tabela"><thead><tr><th>Campo</th><th>Valor</th><th>Origem</th></tr></thead><tbody>{linhas}</tbody></table>',
                    unsafe_allow_html=True)
    for i, (cor, conteudo) in enumerate(b for b in r["blocos"] if b[1].strip()):
        if cor == "texto":
            st.markdown(conteudo)
        else:
            with st.container(key=f"nx-{cor}-{chave}-{i}"):
                st.markdown(conteudo)


# --- HISTÓRICO E NOVA MENSAGEM (a mensagem nova é desenhada pelo histórico, igual às anteriores) ---
for indice, msg in enumerate(st.session_state.mensagens):
    with st.chat_message(msg["papel"], avatar=AVATAR if msg["papel"] == "assistant" else None):
        mostrar_chamadas(msg.get("tools", []))
        if msg.get("erro"):
            st.error(msg["texto"])
        elif msg["papel"] == "assistant":
            mostrar_resposta(msg["texto"], msg["tools"], indice)
        else:
            st.markdown(msg["texto"])

if pergunta := st.chat_input("Descreva a comunicação que você quer cadastrar…" if MODO_INTENCAO else "Pergunte qualquer coisa…") or (
        EXEMPLO_COMPLETO if usar_exemplo else None):
    aviso_vazio.empty()
    st.session_state.mensagens.append({"papel": "user", "texto": pergunta})
    with st.chat_message("user"):
        st.markdown(pergunta)
    with st.chat_message("assistant", avatar=AVATAR):  # bolha visível enquanto o Gemini responde
        try:
            (texto, acoes), erro = atender(pergunta, st.session_state.sessao), False
        except Exception as e:  # 429/5xx só chegam aqui depois das novas tentativas
            codigo = getattr(e, "status_code", None) or getattr(e, "code", None)
            logging.error("Falha ao chamar o Gemini: %s", e)
            texto, acoes, erro = (f"⚠️ O Gemini está temporariamente indisponível (erro {codigo}), mesmo após novas tentativas. "
                                  "Tente novamente em instantes ou troque o modelo na barra lateral." if codigo in (429, 500, 502, 503, 504)
                                  else f"⚠️ Erro ao chamar o Gemini: {e}"), [], True
    st.session_state.mensagens.append({"papel": "assistant", "texto": texto, "tools": acoes, "erro": erro})
    st.rerun()
