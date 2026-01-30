# gestor_da_vida_app.py
# -*- coding: utf-8 -*-

import streamlit as st
import streamlit.components.v1 as components

# Importa os módulos de cada aba
from views.hoje_view import render_hoje  # ✅ NOVO
from views.financeiro_view import render_financeiro
from views.tarefas_view import render_tarefas
from views.saude_view import render_saude
from views.estudos_view import render_estudos

# ============================
# CONFIGURAÇÃO DA PÁGINA (MOBILE)
# ============================
st.set_page_config(
    page_title="Gestor da Vida",
    page_icon="🧭",
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

        // Viewport ideal para iOS (safe-area)
        [...head.querySelectorAll('meta[name="viewport"]')].forEach(m => m.remove());
        add('meta', { name:'viewport', content:'width=device-width, initial-scale=1, viewport-fit=cover, shrink-to-fit=no' });

        // PWA light no iOS
        add('meta', { name:'apple-mobile-web-app-capable', content:'yes' });
        add('meta', { name:'apple-mobile-web-app-status-bar-style', content:'black-translucent' });
        add('meta', { name:'apple-mobile-web-app-title', content:'Gestor da Vida' });

        // Evita autolink de telefone
        add('meta', { name:'format-detection', content:'telephone=no' });

        // Ícone simples (ajuste para o seu)
        const icon = 'https://raw.githubusercontent.com/twitter/twemoji/master/assets/72x72/1f9d1-200d-2696-fe0f.png';
        add('link', { rel:'icon', type:'image/png', href: icon });
      } catch (e) { console.warn('Head injection failed', e); }
    })();
    </script>
    """, height=0)

inject_head_for_ios()

# =========================================================
# CSS global: tema e componentes (Financeiro/Tarefas/Saúde/Estudos)
# =========================================================
st.markdown("""
<style>
:root{
  --bg:#F3F5F9; --text:#0A1628; --muted:#334155;
  --brand:#2563EB; --brand-600:#1D4ED8;
  --ok:#059669; --ok-600:#047857;
  --warn:#D97706; --danger:#DC2626;
  --card:#FFFFFF; --line:#D6DEE8; --soft-line:#E6ECF3;
}
html, body, [class*="css"] { font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, sans-serif; }
html, body { background: var(--bg); color: var(--text); -webkit-text-size-adjust: 100%; }
.stApp { background: var(--bg); }

/* Safe-area iOS */
@supports(padding: max(0px)) {
  .stApp, .block-container {
    padding-top: max(10px, env(safe-area-inset-top)) !important;
    padding-bottom: max(16px, env(safe-area-inset-bottom)) !important;
  }
}

/* Inputs >=16px (sem zoom no iOS) */
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

/* Cabeçalho */
.header-container { text-align: center; padding: 0 10px 14px 10px; }
.main-title {
  background: linear-gradient(90deg, #1E293B, var(--brand));
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  font-weight: 800; font-size: 1.9rem; margin: 0;
}
.slogan { color: var(--muted); font-size: .95rem; font-weight: 600; }

/* Abas */
.stTabs [data-baseweb="tab-list"]{
  display:flex; gap:6px; width:100%; background:#E9EEF5; border:1px solid var(--line); border-radius:16px; padding:4px;
}
.stTabs [data-baseweb="tab"]{
  flex:1 1 auto; text-align:center; background:transparent; border-radius:12px;
  padding:12px 6px !important; color: var(--muted); font-size:14px; font-weight:800; border:none !important;
}
.stTabs [aria-selected="true"]{
  background: var(--card) !important; color: var(--brand) !important; box-shadow: 0 1px 4px rgba(0,0,0,.06); border:1px solid var(--line);
}

/* Métricas */
[data-testid="stMetric"]{
  background: var(--card); border-radius: 14px; padding: 14px; border: 1px solid var(--line);
  box-shadow: 0 1px 6px rgba(0,0,0,.05); color: var(--text);
}
[data-testid="stMetric"] * { opacity: 1 !important; color: var(--text) !important; }
[data-testid="stMetricLabel"] { color: #0F172A !important; font-weight: 800 !important; }
[data-testid="stMetricValue"] { color: #0A1628 !important; font-weight: 900 !important; }

/* Botões padrão (primário) */
.stButton>button{
  width:100%; min-height:46px; border-radius:12px; background: var(--brand);
  color:#fff; border:1px solid #1E40AF; padding:10px 14px; font-weight:800; letter-spacing:.2px;
  box-shadow: 0 1px 8px rgba(29,78,216,.18); transition: transform .12s ease, box-shadow .12s ease, background .12s ease;
}
.stButton>button:active{ transform: scale(.98); }
.stButton>button:hover{ background: var(--brand-600); }

/* Variantes por container */
.btn-neutral > div > button{
  background:#EEF2F7 !important; color:#0A1628 !important; border:1px solid var(--line) !important; box-shadow:none !important;
}
.btn-success > div > button{
  background: var(--ok) !important; color:#fff !important; border:1px solid #065F46 !important;
}
.btn-danger > div > button,
.btn-excluir > div > button{
  background: #FEE2E2 !important; color: var(--danger) !important; border:1px solid #FCA5A5 !important;
  font-size: 14px !important; font-weight: 800 !important; min-height: 42px !important; box-shadow:none !important;
}

/* Cards */
.transaction-card, .task-card, .habit-card, .card{
  background: var(--card); padding: 12px; border-radius: 14px; margin-bottom: 10px;
  border:1px solid var(--line); box-shadow: 0 1px 6px rgba(0,0,0,.05); color: var(--text);
}

/* Responsivo */
@media (max-width: 480px){
  [data-testid="column"]{ width:100% !important; flex:1 1 100% !important; }
  .main-title{ font-size:1.65rem; }
}

#MainMenu, footer, header{ visibility: hidden; }
.block-container{ padding-top: 0.9rem !important; }

/* Dark Mode */
@media (prefers-color-scheme: dark){
  :root{
    --bg:#0F172A; --text:#E7EEF8; --muted:#C8D4EE;
    --card:#141C2F; --line:#24324A; --soft-line:#1F2A3E;
    --brand:#7AA7FF; --brand-600:#5E90FF;
    --ok:#34D399; --warn:#FBBF24; --danger:#F87171;
  }
  html, body { background: var(--bg); color: var(--text); }
  .stApp, .block-container { background: var(--bg); }
  .transaction-card, .task-card, .habit-card, .card{ background: var(--card); border-color:#2A3952; box-shadow: 0 1px 10px rgba(0,0,0,.32); }
  .slogan{ color:#B8C3D9; }
  ::placeholder{ color:#A8B5CC !important; }
}
</style>
""", unsafe_allow_html=True)

# ============================
# LOGIN CENTRAL (fase de testes)
# ============================
def login():
    st.markdown('<div class="header-container"><div class="main-title">🔐 Gestor da Vida</div><div class="slogan">Acesso Restrito</div></div>', unsafe_allow_html=True)
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

# Botão de Logout (sidebar)
if st.sidebar.button("Sair"):
    st.session_state.logged_in = False
    st.rerun()

# ============================
# HEADER APP
# ============================
st.markdown("""
  <div class="header-container">
    <div class="main-title">🧭 Gestor da Vida</div>
    <div class="slogan">Tudo o que importa no seu dia a dia: Finanças, Tarefas, Saúde e Estudos</div>
  </div>
""", unsafe_allow_html=True)

# ============================
# ABAS PRINCIPAIS
# ============================
aba_hoje, aba_fin, aba_tar, aba_sau, aba_est = st.tabs(
    ["🏠 Hoje", "💰 Financeiro", "🗓️ Tarefas", "💪 Saúde", "📚 Estudos"]
)

with aba_hoje:
    render_hoje()
with aba_fin:
    render_financeiro()
with aba_tar:
    render_tarefas()
with aba_sau:
    render_saude()
with aba_est:
    render_estudos()
