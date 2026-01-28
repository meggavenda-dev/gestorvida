# saude_streamlit.py
# -*- coding: utf-8 -*-
"""
Gestor da Vida – Aba Saúde (Fase de Testes com GitHub como “banco”)

Recursos:
- Cadastro de hábitos (nome, meta diária, unidade).
- Registro de logs por dia (amount), botões de +1 e entrada manual.
- Visão diária com barras de progresso por hábito.
- Edição/remoção de hábitos e logs recentes.
"""

import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
import streamlit.components.v1 as components

# === GitHub DB ===
from github_db import (
    buscar_habitos, inserir_habito, atualizar_habito, deletar_habito,
    buscar_habit_logs, inserir_habit_log, atualizar_habit_log, deletar_habit_log
)

# ============================
# CONFIGURAÇÃO DA PÁGINA (MOBILE)
# ============================
st.set_page_config(
    page_title="Minha Casa - Saúde",
    page_icon="💪",
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

.habit-card{
  background: var(--card); padding: 12px; border-radius: 14px; margin-bottom: 10px; display:flex; justify-content:space-between; gap:12px;
  align-items:flex-start; border:1px solid var(--line); box-shadow: 0 1px 6px rgba(0,0,0,.05); color: var(--text);
}
.habit-left{ display:flex; align-items:flex-start; gap:12px; min-width:0; }
.habit-icon{ background: #EBF1FA; width: 42px; height: 42px; border-radius: 10px; display:flex; align-items:center; justify-content:center; font-size: 20px; color:#0F172A; flex:0 0 42px; }
.hb-info{ display:flex; flex-direction:column; gap:4px; min-width:0; }
.hb-title{ font-weight: 700; color: #0A1628; line-height: 1.15; word-break: break-word; }
.hb-meta{ font-size: 12px; color: #334155; line-height: 1.1; }

.btn-danger > div > button{ background: transparent !important; color: var(--danger) !important; border: none !important; font-size: 14px !important; font-weight: 800 !important; min-height: 42px !important; box-shadow:none !important; }

@media (max-width: 480px){ [data-testid="column"]{ width:100% !important; flex:1 1 100% !important; } .main-title{ font-size:1.65rem; } }

#MainMenu, footer, header{ visibility: hidden; }
.block-container{ padding-top: 0.9rem !important; }

@media (prefers-color-scheme: dark){
  :root{ --bg:#0F172A; --text:#E7EEF8; --muted:#C8D4EE; --card:#141C2F; --line:#24324A; --soft-line:#1F2A3E; --brand:#7AA7FF; --brand-600:#5E90FF; --ok:#34D399; --warn:#FBBF24; --danger:#F87171; }
  html, body { background: var(--bg); color: var(--text); }
  .stApp, .block-container { background: var(--bg); }
  .habit-card{ background: var(--card); border-color:#2A3952; box-shadow: 0 1px 10px rgba(0,0,0,.32); }
  .habit-icon{ background:#223049; color:#E5E7EB; }
  .slogan{ color:#B8C3D9; }
  ::placeholder{ color:#A8B5CC !important; }
}
</style>
""", unsafe_allow_html=True)

# ============================
# LOGIN SIMPLES (fase de testes)
# ============================
def login():
    st.markdown('<div class="header-container"><div class="main-title">🔐 Acesso Restrito</div><div class="slogan">Saúde</div></div>', unsafe_allow_html=True)
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
if 'habitos' not in st.session_state:
    st.session_state.habitos = buscar_habitos()
if 'habit_logs' not in st.session_state:
    st.session_state.habit_logs = buscar_habit_logs()

def recarregar():
    st.session_state.habitos = buscar_habitos()
    st.session_state.habit_logs = buscar_habit_logs()

# ============================
# HEADER + SELETOR DE DATA
# ============================
st.markdown("""
  <div class="header-container">
    <div class="main-title">💪 Saúde</div>
    <div class="slogan">Bons hábitos, todos os dias</div>
  </div>
""", unsafe_allow_html=True)

col_d1, col_d2 = st.columns([1,1])
dia_sel = col_d1.date_input("Dia", value=date.today())
mostrar_logs_rec = col_d2.selectbox("Histórico de logs", options=["7 dias", "14 dias", "30 dias"], index=1)

# ============================
# NOVO HÁBITO
# ============================
with st.expander("➕ Novo hábito", expanded=False):
    with st.form("form_habito", clear_on_submit=True):
        nome = st.text_input("Nome do hábito (ex.: Beber água)")
        meta = st.number_input("Meta por dia", min_value=0, value=8, step=1)
        unidade = st.text_input("Unidade (ex.: copos, km, min)")
        if st.form_submit_button("Salvar"):
            if not nome.strip():
                st.error("Informe o nome do hábito.")
            else:
                inserir_habito({
                    "name": nome.strip(),
                    "target_per_day": int(meta),
                    "unit": unidade.strip()
                })
                st.success("Hábito criado!")
                recarregar()
                st.rerun()

# ============================
# VISÃO DIÁRIA (PROGRESSO)
# ============================
habitos = st.session_state.habitos
logs = st.session_state.habit_logs

df_h = pd.DataFrame(habitos)
df_l = pd.DataFrame(logs)
if df_h.empty:
    st.info("Nenhum hábito cadastrado. Adicione um acima.")
else:
    # Soma do dia selecionado por hábito
    if df_l.empty:
        soma_dia = {}
    else:
        df_l['date'] = pd.to_datetime(df_l['date'], errors='coerce').dt.date
        soma_dia = df_l[df_l['date'] == dia_sel].groupby('habit_id')['amount'].sum().to_dict()

    st.markdown("### Hoje / Dia selecionado")
    for _, hb in df_h.sort_values('name').iterrows():
        hid = int(hb['id'])
        alvo = int(hb.get('target_per_day', 0) or 0)
        unit = hb.get('unit', '')
        atual = float(soma_dia.get(hid, 0.0))
        progresso = 0.0 if alvo <= 0 else min(atual / max(alvo, 1), 1.0)

        st.markdown(f"""
        <div class="habit-card">
          <div class="habit-left">
            <div class="habit-icon">🏷️</div>
            <div class="hb-info">
              <div class="hb-title">{hb.get('name','(sem nome)')}</div>
              <div class="hb-meta">Meta: <b>{alvo} {unit}</b> • Feito: <b>{atual:.2f} {unit}</b></div>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)
        st.progress(progresso)

        c1, c2, c3, c4 = st.columns([1,1,2,2])
        with c1:
            if st.button("+1", key=f"inc_{hid}"):
                inserir_habit_log({
                    "habit_id": hid,
                    "date": dia_sel.isoformat(),
                    "amount": 1
                })
                recarregar(); st.rerun()
        with c2:
            val = st.number_input("Qtd.", min_value=0.0, value=0.0, key=f"amt_{hid}")
            if st.button("Adicionar", key=f"add_{hid}"):
                if val > 0:
                    inserir_habit_log({
                        "habit_id": hid,
                        "date": dia_sel.isoformat(),
                        "amount": float(val)
                    })
                    recarregar(); st.rerun()
        with c3:
            with st.expander("Editar Hábito"):
                nn = st.text_input("Nome", value=hb.get('name',''), key=f"en_{hid}")
                nt = st.number_input("Meta por dia", min_value=0, value=int(alvo), step=1, key=f"et_{hid}")
                nu = st.text_input("Unidade", value=unit, key=f"eu_{hid}")
                if st.button("Salvar alter.", key=f"save_h_{hid}"):
                    atualizar_habito(hid, {"name": nn.strip(), "target_per_day": int(nt), "unit": nu.strip()})
                    recarregar(); st.rerun()
        with c4:
            st.markdown('<div class="btn-danger">', unsafe_allow_html=True)
            if st.button("Excluir hábito", key=f"del_h_{hid}"):
                deletar_habito(hid)
                recarregar(); st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

    st.divider()

# ============================
# HISTÓRICO DE LOGS RECENTES
# ============================
if not df_l.empty and not df_h.empty:
    janela_map = {"7 dias": 7, "14 dias": 14, "30 dias": 30}
    dias = janela_map[mostrar_logs_rec]
    inicio = date.today() - timedelta(days=dias)

    df_l['date'] = pd.to_datetime(df_l['date'], errors='coerce').dt.date
    df_recent = df_l[df_l['date'] >= inicio].copy()
    nomes = {int(h['id']): h['name'] for _, h in df_h.iterrows()}
    units = {int(h['id']): h.get('unit','') for _, h in df_h.iterrows()}
    df_recent['habit'] = df_recent['habit_id'].apply(lambda x: nomes.get(int(x), f"Hábito {x}"))
    df_recent['unit'] = df_recent['habit_id'].apply(lambda x: units.get(int(x), ''))

    st.markdown("### Logs recentes")
    for _, lg in df_recent.sort_values(by=['date'], ascending=False).iterrows():
        lid = int(lg['id'])
        st.write(f"📝 {lg['date'].strftime('%d/%m/%Y')} • **{lg['habit']}** — {lg['amount']} {lg['unit']}")
        c1, c2, c3 = st.columns([1,1,2])
        with c1:
            novo = st.number_input("Qtd.", min_value=0.0, value=float(lg['amount']), key=f"lg_amt_{lid}")
        with c2:
            if st.button("Salvar", key=f"lg_save_{lid}"):
                atualizar_habit_log(lid, {"amount": float(novo)})
                recarregar(); st.rerun()
        with c3:
            st.markdown('<div class="btn-danger">', unsafe_allow_html=True)
            if st.button("Excluir", key=f"lg_del_{lid}"):
                deletar_habit_log(lid)
                recarregar(); st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
else:
    st.caption("Sem logs para exibir.")
