# estudos_streamlit.py
# -*- coding: utf-8 -*-
"""
Gestor da Vida – Aba Estudos (Fase de Testes com GitHub como “banco”)

Recursos:
- Assuntos & Materiais: CRUD de assuntos e materiais (URLs).
- Flashcards: CRUD + revisão com SM-2 simplificado (easiness, interval_days, due_date).
- Sessões de estudo: registro de sessões (assunto, duração, notas) e listagem recente.

Observação: O algoritmo de revisão (SM-2 simplificado) aqui ajusta apenas 'easiness', 'interval_days' e 'due_date'.
"""

import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import streamlit.components.v1 as components

# === GitHub DB ===
from github_db import (
    buscar_subjects, inserir_subject, atualizar_subject, deletar_subject,
    buscar_materials, inserir_material, atualizar_material, deletar_material,
    buscar_flashcards, inserir_flashcard, atualizar_flashcard, deletar_flashcard,
    buscar_sessions, inserir_session, atualizar_session, deletar_session
)

# ============================
# CONFIGURAÇÃO DA PÁGINA (MOBILE)
# ============================
st.set_page_config(
    page_title="Minha Casa - Estudos",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# =========================================================
# INJEÇÃO DE METATAGS E ÍCONES NO <HEAD> (iOS e PWA)
# =========================================================
def inject_head_for_ios():
    components.html("""
    <script>
    (function(){
      try {
        const head = document.head;
        function add(tag, attrs){
          const el = document.createElement(tag);
          for (const [k,v] of Object.entries(attrs)) el.setAttribute(k, v);
          head.appendChild(el);
        }
        add('link', { rel:'manifest', href:'./manifest.json' });
        [...head.querySelectorAll('meta[name="viewport"]')].forEach(m => m.remove());
        add('meta', { name:'viewport', content:'width=device-width, initial-scale=1, viewport-fit=cover, shrink-to-fit=no' });
        add('meta', { name:'apple-mobile-web-app-capable', content:'yes' });
        add('meta', { name:'apple-mobile-web-app-status-bar-style', content:'black-translucent' });
        add('meta', { name:'apple-mobile-web-app-title', content:'Minha Casa' });
        add('meta', { name:'format-detection', content:'telephone=no' });
      } catch (e) { console.warn('Head injection failed', e); }
    })();
    </script>
    """, height=0)

inject_head_for_ios()

# =========================================================
# CSS (mesmo tema do Financeiro)
# =========================================================
st.markdown("""
<style>
:root{
  --bg:#F3F5F9; --text:#0A1628; --muted:#334155;
  --brand:#2563EB; --brand-600:#1D4ED8;
  --ok:#0EA5A4; --warn:#D97706; --danger:#DC2626;
  --card:#FFFFFF; --line:#D6DEE8; --soft-line:#E6ECF3;
}
html, body, [class*="css"] { font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, sans-serif; }
html, body { background: var(--bg); color: var(--text); -webkit-text-size-adjust: 100%; }
.stApp { background: var(--bg); }

@supports(padding: max(0px)) {
  .stApp, .block-container {
    padding-top: max(10px, env(safe-area-inset-top)) !important;
    padding-bottom: max(12px, env(safe-area-inset-bottom)) !important;
  }
}

input, select, textarea,
.stTextInput input, .stNumberInput input, .stDateInput input,
.stSelectbox div[data-baseweb="select"] {
  font-size: 16px !important; color: var(--text) !important;
}
.stTextInput input, .stNumberInput input, .stDateInput input {
  background: var(--card) !important; border: 1px solid var(--line) !important; border-radius: 12px !important;
}
.stSelectbox > div[data-baseweb="select"]{ background: var(--card) !important; border: 1px solid var(--line) !important; border-radius: 12px !important; }
::placeholder { color: #475569 !important; opacity: 1 !important; }

.header-container { text-align: center; padding: 0 10px 16px 10px; }
.main-title {
  background: linear-gradient(90deg, #1E293B, var(--brand));
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  font-weight: 800; font-size: 1.9rem; margin: 0;
}
.slogan { color: var(--muted); font-size: .95rem; font-weight: 600; }

.card{
  background: var(--card); padding: 12px; border-radius: 14px; margin-bottom: 10px; display:block;
  align-items:flex-start; border:1px solid var(--line); box-shadow: 0 1px 6px rgba(0,0,0,.05); color: var(--text);
}

.btn-danger > div > button{ background: transparent !important; color: var(--danger) !important; border: none !important; font-size: 14px !important; font-weight: 800 !important; min-height: 42px !important; box-shadow:none !important; }

@media (max-width: 480px){ [data-testid="column"]{ width:100% !important; flex:1 1 100% !important; } .main-title{ font-size:1.65rem; } }

#MainMenu, footer, header{ visibility: hidden; }
.block-container{ padding-top: 0.9rem !important; }

@media (prefers-color-scheme: dark){
  :root{ --bg:#0F172A; --text:#E7EEF8; --muted:#C8D4EE; --card:#141C2F; --line:#24324A; --soft-line:#1F2A3E; --brand:#7AA7FF; --brand-600:#5E90FF; --ok:#34D399; --warn:#FBBF24; --danger:#F87171; }
  html, body { background: var(--bg); color: var(--text); }
  .stApp, .block-container { background: var(--bg); }
  .card{ background: var(--card); border-color:#2A3952; box-shadow: 0 1px 10px rgba(0,0,0,.32); }
  .slogan{ color:#B8C3D9; }
  ::placeholder{ color:#A8B5CC !important; }
}
</style>
""", unsafe_allow_html=True)

# ============================
# LOGIN SIMPLES (fase de testes)
# ============================
def login():
    st.markdown('<div class="header-container"><div class="main-title">🔐 Acesso Restrito</div><div class="slogan">Estudos</div></div>', unsafe_allow_html=True)
    with st.container():
        user_input = st.text_input("Usuário")
        pass_input = st.text_input("Senha", type="password")
        if st.button("Entrar"):
            user_ok = st.secrets.get("APP_USER", "")
            pass_ok = st.secrets.get("APP_PASSWORD", "")
            if user_input.strip() == user_ok and pass_input.strip() == pass_ok:
                st.session_state.logged_in = True
                st.session_state.user_name = user_ok
                st.rerun()
            else:
                st.error("Usuário ou senha inválidos.")

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if not st.session_state.logged_in:
    login()
    st.stop()
if st.sidebar.button("Sair"):
    st.session_state.logged_in = False
    st.rerun()

# ============================
# CARGA INICIAL
# ============================
def recarregar():
    st.session_state.subjects = buscar_subjects()
    st.session_state.materials = buscar_materials()
    st.session_state.flashcards = buscar_flashcards()
    st.session_state.sessions = buscar_sessions()

if 'subjects' not in st.session_state: st.session_state.subjects = buscar_subjects()
if 'materials' not in st.session_state: st.session_state.materials = buscar_materials()
if 'flashcards' not in st.session_state: st.session_state.flashcards = buscar_flashcards()
if 'sessions' not in st.session_state: st.session_state.sessions = buscar_sessions()

# ============================
# HEADER
# ============================
st.markdown("""
  <div class="header-container">
    <div class="main-title">📚 Estudos</div>
    <div class="slogan">Consistência e foco</div>
  </div>
""", unsafe_allow_html=True)

# ============================
# ABAS
# ============================
aba_assuntos, aba_flash, aba_sessoes = st.tabs(["📂 Assuntos & Materiais", "🧠 Flashcards", "⏱️ Sessões"])

# ----------------------------
# Assuntos & Materiais
# ----------------------------
with aba_assuntos:
    st.markdown("### Assuntos")
    with st.expander("➕ Novo assunto", expanded=False):
        with st.form("form_subject", clear_on_submit=True):
            nome = st.text_input("Nome do assunto")
            if st.form_submit_button("Salvar"):
                if not nome.strip():
                    st.error("Informe o nome do assunto.")
                else:
                    inserir_subject({"name": nome.strip()})
                    st.success("Assunto criado!")
                    recarregar(); st.rerun()

    subs = st.session_state.subjects
    mats = st.session_state.materials
    df_s = pd.DataFrame(subs)
    df_m = pd.DataFrame(mats)

    if df_s.empty:
        st.info("Nenhum assunto cadastrado.")
    else:
        for _, s in df_s.sort_values('name').iterrows():
            sid = int(s['id'])
            st.markdown(f"<div class='card'><b>📁 {s.get('name','(sem nome)')}</b></div>", unsafe_allow_html=True)

            # Materiais do assunto
            mlist = df_m[df_m['subject_id'] == sid] if not df_m.empty else pd.DataFrame(columns=['id','title','url'])
            st.markdown("**Materiais**")
            if mlist.empty:
                st.caption("Nenhum material.")
            else:
                for _, mt in mlist.iterrows():
                    mid = int(mt['id'])
                    st.write(f"🔗 **{mt.get('title','(sem título)')}** — {mt.get('url','')}")
                    c1, c2, c3 = st.columns([2,1,1])
                    with c1:
                        with st.expander("Editar material"):
                            nt = st.text_input("Título", value=mt.get('title',''), key=f"mt_t_{mid}")
                            nu = st.text_input("URL", value=mt.get('url',''), key=f"mt_u_{mid}")
                            if st.button("Salvar", key=f"mt_sv_{mid}"):
                                atualizar_material(mid, {"title": nt.strip(), "url": nu.strip()})
                                recarregar(); st.rerun()
                    with c3:
                        st.markdown('<div class="btn-danger">', unsafe_allow_html=True)
                        if st.button("Excluir", key=f"mt_del_{mid}"):
                            deletar_material(mid); recarregar(); st.rerun()
                        st.markdown('</div>', unsafe_allow_html=True)

            with st.expander("➕ Adicionar material", expanded=False):
                with st.form(f"form_mat_{sid}", clear_on_submit=True):
                    t = st.text_input("Título")
                    u = st.text_input("URL")
                    if st.form_submit_button("Adicionar"):
                        if not t.strip():
                            st.error("Informe o título do material.")
                        else:
                            inserir_material({"subject_id": sid, "title": t.strip(), "url": u.strip()})
                            st.success("Material adicionado!"); recarregar(); st.rerun()

            # Editar/Excluir assunto
            col_a1, col_a2 = st.columns([2,1])
            with col_a1:
                with st.expander("Editar assunto"):
                    nn = st.text_input("Nome", value=s.get('name',''), key=f"sb_n_{sid}")
                    if st.button("Salvar assunto", key=f"sb_sv_{sid}"):
                        atualizar_subject(sid, {"name": nn.strip()}); recarregar(); st.rerun()
            with col_a2:
                st.markdown('<div class="btn-danger">', unsafe_allow_html=True)
                if st.button("Excluir assunto", key=f"sb_del_{sid}"):
                    deletar_subject(sid); recarregar(); st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

# ----------------------------
# Flashcards
# ----------------------------
with aba_flash:
    st.markdown("### Flashcards")
    subs = st.session_state.subjects
    cards = st.session_state.flashcards
    df_s = pd.DataFrame(subs)
    df_c = pd.DataFrame(cards)

    sid_options = [("Todos", None)]
    for _, s in df_s.sort_values('name').iterrows():
        sid_options.append((s.get('name',''), int(s['id'])))
    nomes_to_id = {n:i for n,i in sid_options}

    col_f1, col_f2, col_f3 = st.columns([2,1,1])
    sid_name = col_f1.selectbox("Assunto", options=[n for n,_ in sid_options], index=0)
    filtro = col_f2.selectbox("Mostrar", options=["A vencer hoje", "Todos"], index=0)
    ordem = col_f3.selectbox("Ordem", options=["Mais urgentes", "Mais novos"], index=0)

    sel_sid = nomes_to_id[sid_name]

    if df_c.empty:
        st.info("Nenhum flashcard cadastrado.")
    else:
        df_c['due_date'] = pd.to_datetime(df_c.get('due_date', None), errors='coerce').dt.date
        hoje = date.today()
        if sel_sid is not None:
            df_c = df_c[df_c['subject_id'] == sel_sid]
        if filtro == "A vencer hoje":
            df_c = df_c[df_c['due_date'].isna() | (df_c['due_date'] <= hoje)]
        if ordem == "Mais urgentes":
            df_c = df_c.sort_values(by=['due_date'], na_position='first')
        else:
            df_c = df_c.sort_values(by=['id'], ascending=False)

        st.caption(f"Cartões nesta visão: **{len(df_c)}**")

        # Sessão de revisão simples
        with st.expander("➕ Novo flashcard", expanded=False):
            with st.form("form_card", clear_on_submit=True):
                sb = st.selectbox("Assunto", options=[n for n,_ in sid_options if _ is not None], index=0, key="new_card_subj")
                subj_id = nomes_to_id[sb]
                front = st.text_area("Frente", height=80)
                back = st.text_area("Verso", height=80)
                if st.form_submit_button("Salvar"):
                    if not front.strip() or not back.strip():
                        st.error("Preencha frente e verso.")
                    else:
                        inserir_flashcard({
                            "subject_id": subj_id,
                            "front": front.strip(),
                            "back": back.strip(),
                            # easiness, interval_days, due_date defaultam no backend
                        })
                        st.success("Flashcard criado!")
                        recarregar(); st.rerun()

        # Função SM-2 simplificada
        def sm2_update(card, quality: int):
            """
            quality: 0..5 (0=errou feio, 3=ok, 5=fácil)
            """
            e = float(card.get('easiness', 2.5))
            interval = int(card.get('interval_days', 1))
            # Ajuste de easiness
            e = e + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
            if e < 1.3: e = 1.3

            if quality < 3:
                interval = 1
            else:
                if interval == 1:
                    interval = 2
                else:
                    interval = int(round(interval * e))

            due = date.today() + timedelta(days=interval)
            return e, interval, due

        # UI de revisão
        for _, c in df_c.iterrows():
            cid = int(c['id'])
            st.markdown(f"<div class='card'><b>Frente:</b> {c.get('front','')}</div>", unsafe_allow_html=True)
            with st.expander("Mostrar resposta"):
                st.write(c.get('back',''))

            col_b1, col_b2, col_b3, col_b4, col_b5, col_b6 = st.columns(6)
            if col_b1.button("0", key=f"q0_{cid}"):
                e,i,d = sm2_update(c, 0); atualizar_flashcard(cid, {"easiness": e, "interval_days": i, "due_date": d.isoformat()}); recarregar(); st.rerun()
            if col_b2.button("1", key=f"q1_{cid}"):
                e,i,d = sm2_update(c, 1); atualizar_flashcard(cid, {"easiness": e, "interval_days": i, "due_date": d.isoformat()}); recarregar(); st.rerun()
            if col_b3.button("2", key=f"q2_{cid}"):
                e,i,d = sm2_update(c, 2); atualizar_flashcard(cid, {"easiness": e, "interval_days": i, "due_date": d.isoformat()}); recarregar(); st.rerun()
            if col_b4.button("3", key=f"q3_{cid}"):
                e,i,d = sm2_update(c, 3); atualizar_flashcard(cid, {"easiness": e, "interval_days": i, "due_date": d.isoformat()}); recarregar(); st.rerun()
            if col_b5.button("4", key=f"q4_{cid}"):
                e,i,d = sm2_update(c, 4); atualizar_flashcard(cid, {"easiness": e, "interval_days": i, "due_date": d.isoformat()}); recarregar(); st.rerun()
            if col_b6.button("5", key=f"q5_{cid}"):
                e,i,d = sm2_update(c, 5); atualizar_flashcard(cid, {"easiness": e, "interval_days": i, "due_date": d.isoformat()}); recarregar(); st.rerun()

            # Edição/Exclusão
            c1, c2 = st.columns([3,1])
            with c1:
                with st.expander("Editar cartão"):
                    nf = st.text_area("Frente", value=c.get('front',''), key=f"cf_{cid}")
                    nb = st.text_area("Verso", value=c.get('back',''), key=f"cb_{cid}")
                    if st.button("Salvar", key=f"c_save_{cid}"):
                        atualizar_flashcard(cid, {"front": nf.strip(), "back": nb.strip()})
                        recarregar(); st.rerun()
            with c2:
                st.markdown('<div class="btn-danger">', unsafe_allow_html=True)
                if st.button("Excluir", key=f"c_del_{cid}"):
                    deletar_flashcard(cid); recarregar(); st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

# ----------------------------
# Sessões
# ----------------------------
with aba_sessoes:
    st.markdown("### Sessões de estudo")
    subs = st.session_state.subjects
    df_s = pd.DataFrame(subs)
    sid_options = []
    for _, s in df_s.sort_values('name').iterrows():
        sid_options.append((s.get('name',''), int(s['id'])))
    nomes_to_id = {n:i for n,i in sid_options} if sid_options else {}

    with st.expander("➕ Nova sessão", expanded=False):
        with st.form("form_session", clear_on_submit=True):
            if sid_options:
                sb = st.selectbox("Assunto", options=[n for n,_ in sid_options], index=0, key="new_session_subj")
                subj_id = nomes_to_id[sb]
            else:
                st.warning("Cadastre um assunto primeiro.")
                subj_id = None
            dur = st.number_input("Duração (minutos)", min_value=1, value=30, step=1)
            notes = st.text_area("Notas (opcional)", height=80)
            if st.form_submit_button("Salvar"):
                if subj_id is None:
                    st.error("Selecione um assunto.")
                else:
                    inserir_session({
                        "subject_id": subj_id,
                        "started_at": datetime.utcnow().isoformat(),
                        "duration_min": int(dur),
                        "notes": notes.strip()
                    })
                    st.success("Sessão registrada!"); recarregar(); st.rerun()

    # Listagem recente
    sessions = st.session_state.sessions
    df_se = pd.DataFrame(sessions)
    if df_se.empty:
        st.info("Nenhuma sessão registrada.")
    else:
        df_se['started_at_dt'] = pd.to_datetime(df_se['started_at'], errors='coerce')
        nomes = {int(s['id']): s['name'] for _, s in df_s.iterrows()} if not df_s.empty else {}
        st.caption(f"Total de sessões: {len(df_se)}")
        for _, se in df_se.sort_values(by='started_at_dt', ascending=False).head(30).iterrows():
            sid = int(se['subject_id'])
            nome = nomes.get(sid, f"Assunto {sid}")
            dt_txt = se['started_at_dt'].strftime('%d/%m/%Y %H:%M') if pd.notnull(se['started_at_dt']) else se.get('started_at','')
            st.markdown(f"<div class='card'>📌 <b>{nome}</b> • {dt_txt} • {int(se.get('duration_min',0))} min<br>{se.get('notes','')}</div>", unsafe_allow_html=True)

            c1, c2, c3 = st.columns([2,1,1])
            with c1:
                with st.expander("Editar sessão"):
                    ndur = st.number_input("Duração (min)", min_value=1, value=int(se.get('duration_min',1)), step=1, key=f"se_dur_{se['id']}")
                    nnotes = st.text_area("Notas", value=se.get('notes',''), key=f"se_nt_{se['id']}")
                    if st.button("Salvar", key=f"se_sv_{se['id']}"):
                        atualizar_session(int(se['id']), {"duration_min": int(ndur), "notes": nnotes.strip()})
                        recarregar(); st.rerun()
            with c3:
                st.markdown('<div class="btn-danger">', unsafe_allow_html=True)
                if st.button("Excluir", key=f"se_del_{se['id']}"):
                    deletar_session(int(se['id']))
                    recarregar(); st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)
