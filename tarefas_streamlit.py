# tarefas_streamlit.py
# -*- coding: utf-8 -*-
"""
Gestor da Vida – Aba Tarefas (Fase de Testes com GitHub como “banco”)

Recursos:
- Cadastro de tarefas (título, descrição, data de vencimento, responsável, status).
- Filtros por responsável, status e janela de vencimento.
- Cards com ações rápidas: marcar como feito, alterar status, editar e excluir.
- Métricas: total, abertas, vencendo hoje/atrasadas.
"""

import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import streamlit.components.v1 as components

# === GitHub DB ===
from github_db import (
    buscar_tasks, inserir_task, atualizar_task, deletar_task,
    buscar_pessoas
)

# ============================
# CONFIGURAÇÃO DA PÁGINA (MOBILE)
# ============================
st.set_page_config(
    page_title="Minha Casa - Tarefas",
    page_icon="🗓️",
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

/* Cards de tarefa */
.task-card{
  background: var(--card); padding: 12px; border-radius: 14px; margin-bottom: 10px; display:flex; justify-content:space-between; gap:12px;
  align-items:flex-start; border:1px solid var(--line); box-shadow: 0 1px 6px rgba(0,0,0,.05); color: var(--text);
}
.task-left{ display:flex; align-items:flex-start; gap:12px; min-width:0; }
.task-icon{ background: #EBF1FA; width: 42px; height: 42px; border-radius: 10px; display:flex; align-items:center; justify-content:center; font-size: 20px; color:#0F172A; flex:0 0 42px; }
.tk-info{ display:flex; flex-direction:column; gap:4px; min-width:0; }
.tk-title{ font-weight: 700; color: #0A1628; line-height: 1.15; word-break: break-word; }
.tk-meta{ font-size: 12px; color: #334155; line-height: 1.1; }
.status-badge{ font-size: 11px; padding: 3px 8px; border-radius: 10px; font-weight: 900; text-transform: uppercase; display:inline-block; letter-spacing:.2px; width: fit-content; }
.status-badge.todo{ background:#FEF3C7; color:#92400E; border:1px solid #FCD34D; }
.status-badge.doing{ background:#DBEAFE; color:#1E3A8A; border:1px solid #93C5FD; }
.status-badge.done{ background:#DCFCE7; color:#065F46; border:1px solid #86EFAC; }
.status-badge.cancelled{ background:#FEE2E2; color:#991B1B; border:1px solid #FCA5A5; }

.btn-danger > div > button{ background: transparent !important; color: var(--danger) !important; border: none !important; font-size: 14px !important; font-weight: 800 !important; min-height: 42px !important; box-shadow:none !important; }

@media (max-width: 480px){ [data-testid="column"]{ width:100% !important; flex:1 1 100% !important; } .main-title{ font-size:1.65rem; } }

#MainMenu, footer, header{ visibility: hidden; }
.block-container{ padding-top: 0.9rem !important; }

@media (prefers-color-scheme: dark){
  :root{ --bg:#0F172A; --text:#E7EEF8; --muted:#C8D4EE; --card:#141C2F; --line:#24324A; --soft-line:#1F2A3E; --brand:#7AA7FF; --brand-600:#5E90FF; --ok:#34D399; --warn:#FBBF24; --danger:#F87171; }
  html, body { background: var(--bg); color: var(--text); }
  .stApp, .block-container { background: var(--bg); }
  .task-card{ background: var(--card); border-color:#2A3952; box-shadow: 0 1px 10px rgba(0,0,0,.32); }
  .task-icon{ background:#223049; color:#E5E7EB; }
  .slogan{ color:#B8C3D9; }
  ::placeholder{ color:#A8B5CC !important; }
}
</style>
""", unsafe_allow_html=True)

# ============================
# LOGIN SIMPLES (fase de testes)
# ============================
def login():
    st.markdown('<div class="header-container"><div class="main-title">🔐 Acesso Restrito</div><div class="slogan">Tarefas</div></div>', unsafe_allow_html=True)
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
if 'tasks' not in st.session_state:
    st.session_state.tasks = buscar_tasks()
if 'pessoas' not in st.session_state or not st.session_state.pessoas:
    st.session_state.pessoas = buscar_pessoas()

PESSOAS = st.session_state.pessoas
STATUS_OPCOES = ['todo', 'doing', 'done', 'cancelled']

# ============================
# HEADER
# ============================
st.markdown("""
  <div class="header-container">
    <div class="main-title">🗓️ Tarefas</div>
    <div class="slogan">Organize, priorize e conclua</div>
  </div>
""", unsafe_allow_html=True)

# ============================
# FILTROS
# ============================
col_f1, col_f2, col_f3 = st.columns([1.5, 1.5, 1])
status_sel = col_f1.multiselect("Status", STATUS_OPCOES, default=['todo', 'doing'])
resp_sel = col_f2.selectbox("Responsável", options=["Todos"] + PESSOAS, index=0)
janela = col_f3.selectbox("Vencimento", options=["Todos", "Hoje", "Próximos 7 dias", "Próximos 30 dias"], index=0)

def parse_due_at(x):
    try:
        return datetime.fromisoformat(x).date() if x else None
    except Exception:
        return None

def filtrar_tasks(tasks):
    df = pd.DataFrame(tasks)
    if df.empty:
        return df
    df['due_date'] = df.get('due_at', None)
    df['due_date'] = df['due_date'].apply(parse_due_at)
    # filtros
    if status_sel:
        df = df[df['status'].isin(status_sel)]
    if resp_sel != "Todos":
        df = df[df['assignee'] == resp_sel]
    hoje = date.today()
    if janela == "Hoje":
        df = df[df['due_date'] == hoje]
    elif janela == "Próximos 7 dias":
        limite = hoje + timedelta(days=7)
        df = df[(df['due_date'].notna()) & (df['due_date'] >= hoje) & (df['due_date'] <= limite)]
    elif janela == "Próximos 30 dias":
        limite = hoje + timedelta(days=30)
        df = df[(df['due_date'].notna()) & (df['due_date'] >= hoje) & (df['due_date'] <= limite)]
    # ordenação
    df = df.sort_values(by=['due_date', 'status', 'title'], na_position='last')
    return df

# ============================
# MÉTRICAS
# ============================
tasks_raw = st.session_state.tasks
df_all = pd.DataFrame(tasks_raw)
if df_all.empty:
    total = 0
    abertas = 0
    hoje_qtd = 0
    atrasadas = 0
else:
    df_all['due_date'] = df_all.get('due_at', None).apply(parse_due_at)
    total = len(df_all)
    abertas = int((df_all['status'].isin(['todo','doing'])).sum())
    hoje_qtd = int(((df_all['due_date'] == date.today()) & df_all['status'].isin(['todo','doing'])).sum())
    atrasadas = int(((df_all['due_date'].notna()) & (df_all['due_date'] < date.today()) & df_all['status'].isin(['todo','doing'])).sum())

m1, m2, m3, m4 = st.columns(4)
m1.metric("Total", str(total))
m2.metric("Abertas", str(abertas))
m3.metric("Para Hoje", str(hoje_qtd))
m4.metric("Atrasadas", str(atrasadas))

st.divider()

# ============================
# NOVA TAREFA
# ============================
with st.expander("➕ Nova tarefa", expanded=False):
    with st.form("form_task", clear_on_submit=True):
        title = st.text_input("Título")
        desc = st.text_area("Descrição", height=80)
        due = st.date_input("Vencimento (opcional)", value=None)
        assignee = st.selectbox("Responsável", options=PESSOAS, index=0)
        status_init = st.selectbox("Status", options=STATUS_OPCOES, index=0)
        if st.form_submit_button("Salvar"):
            if not title.strip():
                st.error("Informe o título.")
            else:
                inserir_task({
                    "title": title.strip(),
                    "description": desc.strip(),
                    "due_at": due.isoformat() if due else None,
                    "status": status_init,
                    "assignee": assignee,
                    "created_at": datetime.utcnow().isoformat()
                })
                st.success("Tarefa criada!")
                st.session_state.tasks = buscar_tasks()
                st.rerun()

st.markdown("### Lista de Tarefas")
df_view = filtrar_tasks(st.session_state.tasks)

if df_view.empty:
    st.info("Nenhuma tarefa com os filtros atuais.")
else:
    for _, row in df_view.iterrows():
        s = row['status']
        s_class = s if s in ['todo','doing','done','cancelled'] else 'todo'
        due_txt = row['due_date'].strftime('%d/%m/%Y') if pd.notnull(row['due_date']) else '—'
        overdue_flag = ""
        if row['due_date'] and row['status'] in ['todo','doing']:
            diff = (row['due_date'] - date.today()).days
            if diff < 0:
                overdue_flag = f" • 🔴 Atrasada há {-diff}d"
            elif diff == 0:
                overdue_flag = " • 🟡 Vence hoje"

        st.markdown(f"""
        <div class="task-card">
          <div class="task-left">
            <div class="task-icon">🗒️</div>
            <div class="tk-info">
              <div class="tk-title">{row.get('title','(sem título)')}</div>
              <div class="tk-meta">Resp.: <b>{row.get('assignee','Ambos')}</b> • Venc.: <b>{due_txt}</b>{overdue_flag}</div>
              <div class="status-badge {s_class}">{s.upper()}</div>
              <div class="tk-meta">{(row.get('description') or '').strip()}</div>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        c1, c2, c3, c4 = st.columns([1,1,2,1])
        with c1:
            if s != 'done' and st.button("✔ Concluir", key=f"done_{row['id']}"):
                atualizar_task(int(row['id']), {"status": "done"})
                st.session_state.tasks = buscar_tasks(); st.rerun()
        with c2:
            novo_status = st.selectbox("Status", STATUS_OPCOES, index=STATUS_OPCOES.index(s), key=f"st_{row['id']}")
            if st.button("Salvar Status", key=f"save_st_{row['id']}"):
                atualizar_task(int(row['id']), {"status": novo_status})
                st.session_state.tasks = buscar_tasks(); st.rerun()
        with c3:
            with st.expander("Editar"):
                nt = st.text_input("Título", value=row.get('title',''), key=f"et_{row['id']}")
                nd = st.text_area("Descrição", value=row.get('description',''), key=f"ed_{row['id']}")
                ndue = st.date_input("Vencimento", value=row['due_date'] if pd.notnull(row['due_date']) else None, key=f"ev_{row['id']}")
                nass = st.selectbox("Responsável", options=PESSOAS, index=PESSOAS.index(row.get('assignee','Ambos')) if row.get('assignee','Ambos') in PESSOAS else 0, key=f"ea_{row['id']}")
                if st.button("Salvar Alterações", key=f"save_ed_{row['id']}"):
                    atualizar_task(int(row['id']), {
                        "title": nt.strip(),
                        "description": nd.strip(),
                        "due_at": ndue.isoformat() if ndue else None,
                        "assignee": nass
                    })
                    st.session_state.tasks = buscar_tasks(); st.rerun()
        with c4:
            st.markdown('<div class="btn-danger">', unsafe_allow_html=True)
            if st.button("Excluir", key=f"del_{row['id']}"):
                deletar_task(int(row['id']))
                st.session_state.tasks = buscar_tasks(); st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
