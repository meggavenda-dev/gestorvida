# app_financeiro_streamlit.py
# -*- coding: utf-8 -*-
"""
Gestor da Vida – Aba Financeiro (Fase de Testes com GitHub como “banco”)

✅ Visão Geral da Arquitetura (para a fase seguinte):
1) Frontend Mobile
   - Opção A (recomendada): React Native (Expo)
     Vantagens: push notifications nativas, acesso a calendário/lembranças, câmera, HealthKit/Google Fit (no futuro),
     offline-first robusto. Navegação em abas com expo-router ou @react-navigation.
   - Opção B: PWA (Web)
     Útil como atalho, mas web push no iOS exige PWA instalada + service worker + manifest válidos,
     e Streamlit não foi pensado para service worker (servidor/proxy custom).

   **Conclusão**: Para notificações confiáveis, background sync e integrações de saúde/calendário, RN (Expo) é superior.

2) Backend & Banco
   - Supabase (Postgres + Auth + Storage + RLS) para produção:
     Migrar autenticação de usuarios + bcrypt → Supabase Auth; usar RLS por usuário/família (household_id).
     Tabelas por domínio: financeiro, tarefas/eventos, saúde, estudos.

   - (Opcional) Microserviço Python (FastAPI) para PDF/relatórios (reaproveitando ReportLab).

3) Sincronização & Offline
   - App RN mantém cache offline (SQLite / WatermelonDB / MMKV).
   - Sincroniza com Supabase via supabase-js + realtime (se necessário).

4) Notificações & Agenda
   - Firebase Cloud Messaging (Android) e APNs (iOS) via Expo Notifications.
   - Futuro: Google Calendar / Microsoft 365 (Graph).

5) Privacidade e Multiusuário
   - Modelo “família/casa” (households): Guilherme e Alynne.
   - RLS filtra por household_id.

🗺️ Roadmap (enxuto e incremental)
- M0 – Base e Financeiro (2–3 semanas)
  Criar app Expo com abas; Supabase Auth; integrar Financeiro via WebView (rápido);
  backend (Edge Function/FASTAPI) para PDFs/Excel, se necessário.
- M1 – Tarefas/Reuniões (1–2 semanas)
  CRUD de tarefas, prazos, atribuição (Guilherme/Alynne/Ambos), lembretes (push), agenda simples.
- M2 – Saúde/Hábitos (1–2 semanas)
  Hábitos/checagens; futuro: Google Fit/HealthKit.
- M3 – Estudos (2 semanas)
  Materiais, sessões, revisão espaçada (SM-2 simplificado).
- M4 – UI/UX & PWA/Nativo
  Unificar tema; performance; portar gradualmente o Financeiro para telas nativas RN.

Este arquivo implementa a **aba Financeiro** em Streamlit, usando **GitHub JSON** como persistência.
Quando migrar para Supabase, basta substituir as funções de persistência (`buscar_*`, `inserir_*`, etc.).
"""

import streamlit as st
import pandas as pd
from datetime import date
import io
import streamlit.components.v1 as components

# === ReportLab para gerar PDF robusto (cabeçalho + paginação) ===
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm

# === GitHub DB ===
from github_db import (
    buscar_pessoas, buscar_dados, buscar_metas, buscar_fixos,
    inserir_transacao, atualizar_transacao, deletar_transacao,
    upsert_meta, inserir_fixo, atualizar_fixo, deletar_fixo
)

# ============================
# CONFIGURAÇÃO DA PÁGINA (MOBILE)
# ============================
st.set_page_config(
    page_title="Minha Casa",
    page_icon="🏡",
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
        add('meta', { name:'apple-mobile-web-app-title', content:'Minha Casa' });
        // Evita autolink de telefone
        add('meta', { name:'format-detection', content:'telephone=no' });
        // Ícones (troque pelas suas imagens se quiser)
        const icon180 = 'https://raw.githubusercontent.com/twitter/twemoji/master/assets/72x72/1f3e1.png';
        ['180x180','152x152','120x120','76x76'].forEach(size => {
          add('link', { rel:'apple-touch-icon', sizes:size, href: icon180 });
        });
        add('link', { rel:'icon', type:'image/png', href: icon180 });
      } catch (e) { console.warn('Head injection failed', e); }
    })();
    </script>
    """, height=0)

inject_head_for_ios()

# =========================================================
# CSS MID-CONTRAST (claro por padrão) + Dark Mode moderado
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

/* Safe-area iOS */
@supports(padding: max(0px)) {
  .stApp, .block-container {
    padding-top: max(10px, env(safe-area-inset-top)) !important;
    padding-bottom: max(12px, env(safe-area-inset-bottom)) !important;
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
.stSelectbox svg, .stNumberInput svg { color: #1F2937 !important; opacity: 1 !important; }

/* Cabeçalho */
.header-container { text-align: center; padding: 0 10px 16px 10px; }
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
.stTabs [aria-selected="true"]{ background: var(--card) !important; color: var(--brand) !important; box-shadow: 0 1px 4px rgba(0,0,0,.06); border:1px solid var(--line); }

/* Métricas */
[data-testid="stMetric"]{
  background: var(--card); border-radius: 14px; padding: 14px; border: 1px solid var(--line);
  box-shadow: 0 1px 6px rgba(0,0,0,.05); color: var(--text);
}
[data-testid="stMetric"] * { opacity: 1 !important; color: var(--text) !important; }
[data-testid="stMetricLabel"] { color: #0F172A !important; font-weight: 800 !important; }
[data-testid="stMetricValue"] { color: #0A1628 !important; font-weight: 900 !important; }

/* Botões */
.stButton>button{
  width:100%; min-height:46px; border-radius:12px; background: var(--brand);
  color:#fff; border:1px solid #1E40AF; padding:10px 14px; font-weight:800; letter-spacing:.2px;
  box-shadow: 0 1px 8px rgba(29,78,216,.18); transition: transform .12s ease, box-shadow .12s ease, background .12s ease;
}
.stButton>button:active{ transform: scale(.98); }
.stButton>button:hover{ background: var(--brand-600); }

/* Botão Excluir */
.btn-excluir > div > button{ background: transparent !important; color: var(--danger) !important; border: none !important; font-size: 14px !important; font-weight: 800 !important; min-height: 42px !important; box-shadow:none !important; }

/* Cards de transação */
.transaction-card{
  background: var(--card); padding: 12px; border-radius: 14px; margin-bottom: 10px; display:flex; justify-content:space-between; gap:12px;
  align-items:flex-start; border:1px solid var(--line); box-shadow: 0 1px 6px rgba(0,0,0,.05); color: var(--text);
}
.transaction-left{ display:flex; align-items:flex-start; gap:12px; min-width:0; }
.card-icon{ background: #EBF1FA; width: 42px; height: 42px; border-radius: 10px; display:flex; align-items:center; justify-content:center; font-size: 20px; color:#0F172A; flex:0 0 42px; }
.tc-info{ display:flex; flex-direction:column; gap:4px; min-width:0; }
.tc-title{ font-weight: 700; color: #0A1628; line-height: 1.15; word-break: break-word; }
.tc-meta{ font-size: 12px; color: #334155; line-height: 1.1; }
.status-badge{ font-size: 11px; padding: 3px 8px; border-radius: 10px; font-weight: 900; text-transform: uppercase; display:inline-block; letter-spacing:.2px; width: fit-content; }
.status-badge.pago{ background:#DCFCE7; color:#065F46; border:1px solid #86EFAC; }
.status-badge.pendente{ background:#FEF3C7; color:#92400E; border:1px solid #FCD34D; }
.status-badge.negociacao{ background:#DBEAFE; color:#1E3A8A; border:1px solid #93C5FD; }
.transaction-right{ color:#0A1628; font-weight: 800; white-space: nowrap; margin-left:auto; }
.transaction-right.entrada{ color:#0EA5A4; }
.transaction-right.saida{ color:#DC2626; }

.vencimento-alerta { color: #B91C1C; font-size: 12px; font-weight: 800; }

/* Card Patrimônio */
.reserva-card{ background: linear-gradient(135deg, #F8FAFF 0%, #E9EEF7 100%); color: #0A1628; padding: 18px; border-radius: 14px; text-align: center; box-shadow: 0 1px 8px rgba(0,0,0,.06); border:1px solid var(--line); }

/* Metas */
.meta-container{ background:#F6F9FC; border:1px solid var(--line); border-radius:10px; padding:10px; margin-bottom:8px; color:#0A1628; font-weight:600; }

/* Expanders */
[data-testid="stExpander"] > details{ border:1px solid var(--line); border-radius:14px; padding:6px 10px; background: var(--card); }
[data-testid="stExpander"] summary { padding:10px; font-weight: 800; color: var(--text); }

/* iPhone */
@media (max-width: 480px){ [data-testid="column"]{ width:100% !important; flex:1 1 100% !important; } .main-title{ font-size:1.65rem; } }

/* Limpeza */
#MainMenu, footer, header{ visibility: hidden; }
.block-container{ padding-top: 0.9rem !important; }

/* Dark Mode moderado */
@media (prefers-color-scheme: dark){
  :root{ --bg:#0F172A; --text:#E7EEF8; --muted:#C8D4EE; --card:#141C2F; --line:#24324A; --soft-line:#1F2A3E; --brand:#7AA7FF; --brand-600:#5E90FF; --ok:#34D399; --warn:#FBBF24; --danger:#F87171; }
  html, body { background: var(--bg); color: var(--text); }
  .stApp, .block-container { background: var(--bg); }
  .stTabs [data-baseweb="tab-list"]{ background:#18223A; border-color:#25314A; }
  .stTabs [aria-selected="true"]{ border-color:#2E3C59; box-shadow: 0 1px 6px rgba(0,0,0,.35); }
  .transaction-card, [data-testid="stMetric"], [data-testid="stExpander"] > details{ background: var(--card); border-color:#2A3952; box-shadow: 0 1px 10px rgba(0,0,0,.32); }
  .card-icon{ background:#223049; color:#E5E7EB; }
  .slogan{ color:#B8C3D9; }
  ::placeholder{ color:#A8B5CC !important; }
}
</style>
""", unsafe_allow_html=True)

# ============================
# LOGIN SIMPLES (fase de testes)
# ============================
def login():
    st.markdown('<div class="header-container"><div class="main-title">🔐 Acesso Restrito</div></div>', unsafe_allow_html=True)
    with st.container():
        user_input = st.text_input("Usuário")
        pass_input = st.text_input("Senha", type="password")
        if st.button("Entrar"):
            # Fase de testes: valida com secrets simples
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

# Botão de Logout
if st.sidebar.button("Sair"):
    st.session_state.logged_in = False
    st.rerun()

# ============================
# FUNÇÕES DE RELATÓRIO
# ============================
def gerar_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_exp = df.copy()
        df_exp['data'] = pd.to_datetime(df_exp['data'], errors='coerce').dt.strftime('%d/%m/%Y')
        colunas = ['data', 'descricao', 'valor', 'tipo', 'status', 'responsavel', 'categoria', 'id']
        for c in colunas:
            if c not in df_exp.columns:
                df_exp[c] = ''
        df_exp = df_exp[colunas]
        df_exp.to_excel(writer, index=False, sheet_name='Lançamentos')
    return output.getvalue()

def gerar_pdf(df, nome_mes):
    buffer = io.BytesIO()
    df_exp = df.copy()
    df_exp['data'] = pd.to_datetime(df_exp['data'], errors='coerce')
    df_exp['data_fmt'] = df_exp['data'].dt.strftime('%d/%m/%Y').fillna('')
    df_exp['descricao'] = df_exp['descricao'].fillna('').astype(str)
    df_exp['valor'] = pd.to_numeric(df_exp['valor'], errors='coerce').fillna(0.0)
    df_exp['tipo'] = (df_exp['tipo'] if 'tipo' in df_exp.columns else '').fillna('').astype(str)
    df_exp['status'] = (df_exp['status'] if 'status' in df_exp.columns else 'Pago')
    if not isinstance(df_exp['status'], pd.Series): df_exp['status'] = 'Pago'
    df_exp['status'] = df_exp['status'].fillna('Pago').astype(str)
    df_exp['responsavel'] = (df_exp['responsavel'] if 'responsavel' in df_exp.columns else 'Ambos')
    if not isinstance(df_exp['responsavel'], pd.Series): df_exp['responsavel'] = 'Ambos'
    df_exp['responsavel'] = df_exp['responsavel'].fillna('Ambos').astype(str)
    df_exp = df_exp.sort_values(by=['data', 'descricao'], na_position='last')

    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=12*mm, rightMargin=12*mm,
        topMargin=14*mm, bottomMargin=14*mm
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'TitleCenter', parent=styles['Heading1'],
        alignment=1, fontName='Helvetica-Bold',
        fontSize=16, leading=20, spaceAfter=6
    )

    elements = []
    elements.append(Paragraph(f"Relatorio Financeiro - {nome_mes}", title_style))
    elements.append(Spacer(1, 6))

    header = ["Data", "Descricao", "Valor", "Tipo", "Status", "Responsável"]
    data_rows = []
    for _, r in df_exp.iterrows():
        valor_txt = f"R$ {r['valor']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        data_rows.append([r['data_fmt'], r['descricao'], valor_txt, r['tipo'], r['status'], r['responsavel']])

    table_data = [header] + data_rows
    col_widths = [22*mm, 70*mm, 25*mm, 22*mm, 22*mm, 25*mm]

    tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(TableStyle([
        ('FONT', (0,0), (-1,0), 'Helvetica-Bold', 10),
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#E6ECF5")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.HexColor("#141A22")),
        ('ALIGN', (0,0), (-1,0), 'CENTER'),

        ('FONT', (0,1), (-1,-1), 'Helvetica', 9),
        ('TEXTCOLOR', (0,1), (-1,-1), colors.black),

        ('ALIGN', (2,1), (2,-1), 'RIGHT'),
        ('ALIGN', (0,1), (0,-1), 'CENTER'),
        ('ALIGN', (3,1), (5,-1), 'CENTER'),

        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#C8D2DC")),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#FAFBFD")]),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))

    elements.append(tbl)
    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes

# ============================
# SINCRONIZAÇÃO INICIAL
# ============================
if 'dados' not in st.session_state:
    st.session_state.dados = buscar_dados()
if 'metas' not in st.session_state:
    st.session_state.metas = buscar_metas()
if 'fixos' not in st.session_state:
    st.session_state.fixos = buscar_fixos()
if 'pessoas' not in st.session_state or not st.session_state.pessoas:
    st.session_state.pessoas = buscar_pessoas()

CATEGORIAS = ["🛒 Mercado", "🏠 Moradia", "🚗 Transporte", "🍕 Lazer", "💡 Contas", "💰 Salário", "✨ Outros"]
meses = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
PESSOAS = st.session_state.pessoas

# ============================
# HEADER
# ============================
st.markdown("""
    <div class="header-container">
        <div class="main-title">🏡 Financeiro</div>
        <div class="slogan">Gestão inteligente para o seu lar</div>
    </div>
""", unsafe_allow_html=True)

# ============================
# FILTROS DE MÊS/ANO
# ============================
hoje = date.today()
c_m, c_a = st.columns([2, 1])
mes_nome = c_m.selectbox("Mês", meses, index=hoje.month - 1)
ano_ref = c_a.number_input("Ano", value=hoje.year, step=1)
mes_num = meses.index(mes_nome) + 1

# ============================
# PROCESSAMENTO DE DADOS
# ============================
df_geral = st.session_state.dados.copy()
colunas_padrao = ['id', 'data', 'descricao', 'valor', 'tipo', 'categoria', 'status', 'responsavel']
df_mes = pd.DataFrame(columns=colunas_padrao)
df_atrasados_passado = pd.DataFrame(columns=colunas_padrao)
total_in = 0.0
total_out_pagas = 0.0
balanco = 0.0

if not df_geral.empty:
    total_in = df_geral[df_geral['tipo'] == 'Entrada']['valor'].sum()
    total_out_pagas = df_geral[(df_geral['tipo'] == 'Saída') & (df_geral['status'] == 'Pago')]['valor'].sum()
    balanco = total_in - total_out_pagas

    df_mes = df_geral[
        (df_geral['data'].dt.month == mes_num) &
        (df_geral['data'].dt.year == ano_ref)
    ].copy()

    if 'responsavel' not in df_mes.columns:
        df_mes['responsavel'] = 'Ambos'
    df_mes['responsavel'] = df_mes['responsavel'].fillna('Ambos').astype(str)

    data_inicio_mes_selecionado = pd.Timestamp(date(ano_ref, mes_num, 1))
    df_atrasados_passado = df_geral[
        (df_geral['status'] == 'Pendente') &
        (df_geral['data'] < data_inicio_mes_selecionado) &
        (df_geral['tipo'] == 'Saída')
    ].copy()

# ============================
# FUN AUX
# ============================
def idx_pessoa(valor: str, pessoas: list[str]) -> int:
    try:
        return pessoas.index(valor)
    except Exception:
        return pessoas.index('Ambos') if 'Ambos' in pessoas else 0

# ============================
# ABAS
# ============================
aba_resumo, aba_novo, aba_reserva, aba_negociacao, aba_metas, aba_sonhos = st.tabs(
    ["📊 Mês", "➕ Novo", "🏦 Caixa", "🤝 Negociação", "🎯 Metas", "🚀 Sonhos"]
)

# ============================
# ABA: MÊS (RESUMO + HISTÓRICO)
# ============================
with aba_resumo:
    # Atrasados (passado)
    if not df_atrasados_passado.empty:
        total_atrasado = df_atrasados_passado['valor'].sum()
        with st.expander(f"⚠️ CONTAS PENDENTES DE MESES ANTERIORES: R$ {total_atrasado:,.2f}", expanded=True):
            for _, row in df_atrasados_passado.iterrows():
                col_at1, col_at2 = st.columns([3, 1])
                dt_txt = row['data'].strftime('%d/%m/%y') if pd.notnull(row['data']) else '--/--/--'
                col_at1.write(f"**{row['descricao']}** ({dt_txt}) — **Resp.: {row.get('responsavel','Ambos')}**")
                if col_at2.button("✔ Pagar", key=f"pay_at_{row['id']}"):
                    atualizar_transacao(int(row['id']), {"status": "Pago"})
                    st.session_state.dados = buscar_dados(); st.rerun()

    if not df_mes.empty:
        entradas = df_mes[df_mes['tipo'] == 'Entrada']['valor'].sum()
        saidas_pagas = df_mes[(df_mes['tipo'] == 'Saída') & (df_mes['status'] == 'Pago')]['valor'].sum()
        saldo_mes = entradas - saidas_pagas

        c1, c2, c3 = st.columns(3)
        c1.metric("Ganhos", f"R$ {entradas:,.2f}")
        c2.metric("Gastos (Pagos)", f"R$ {saidas_pagas:,.2f}")
        c3.metric("Saldo Real", f"R$ {saldo_mes:,.2f}")

        if st.session_state.metas:
            with st.expander("🎯 Status das Metas"):
                gastos_cat = df_mes[(df_mes['tipo'] == 'Saída') & (df_mes['status'] == 'Pago')].groupby('categoria')['valor'].sum()
                for cat, lim in st.session_state.metas.items():
                    if lim > 0:
                        atual = gastos_cat.get(cat, 0)
                        st.markdown(f'<div class="meta-container"><b>{cat}</b> (R$ {atual:,.0f} / {lim:,.0f})</div>', unsafe_allow_html=True)
                        st.progress(min(atual/lim, 1.0))

        st.markdown("### Histórico")
        for idx, row in df_mes.sort_values(by='data', ascending=False).iterrows():
            valor_class = "entrada" if row['tipo'] == "Entrada" else "saida"
            icon = row['categoria'].split()[0] if " " in row['categoria'] else "💸"
            s_text = row.get('status', 'Pago')

            if s_text == "Pago":
                s_class = "pago"
            elif s_text == "Pendente":
                s_class = "pendente"
            else:
                s_class = "negociacao"

            txt_venc = ""
            if s_text == "Pendente" and row['tipo'] == "Saída" and pd.notnull(row['data']):
                dias_diff = (row['data'].date() - hoje).days
                if dias_diff < 0:
                    txt_venc = f" <span class='vencimento-alerta'>Atrasada há {-dias_diff} dias</span>"
                elif dias_diff == 0:
                    txt_venc = f" <span class='vencimento-alerta' style='color:#D97706'>Vence Hoje!</span>"

            resp_txt = row.get('responsavel', 'Ambos')
            dt_card = row['data'].strftime('%d %b') if pd.notnull(row['data']) else '-- ---'

            st.markdown(f"""
              <div class="transaction-card">
                <div class="transaction-left">
                  <div class="card-icon">{icon}</div>
                  <div class="tc-info">
                    <div class="tc-title">{row["descricao"]}</div>
                    <div class="tc-meta">{dt_card}{txt_venc}</div>
                    <div class="tc-meta">Responsável: <b>{resp_txt}</b></div>
                    <div class="status-badge {s_class}">{s_text}</div>
                  </div>
                </div>
                <div class="transaction-right {valor_class}">R$ {row["valor"]:,.2f}</div>
              </div>
            """, unsafe_allow_html=True)

            cp, cd = st.columns([1, 1])
            with cp:
                if s_text != "Pago" and st.button("✔ Pagar", key=f"pay_{row['id']}"):
                    atualizar_transacao(int(row['id']), {"status": "Pago"})
                    st.session_state.dados = buscar_dados(); st.rerun()
            with cd:
                st.markdown('<div class="btn-excluir">', unsafe_allow_html=True)
                if st.button("Excluir", key=f"del_{row['id']}"):
                    deletar_transacao(int(row['id']))
                    st.session_state.dados = buscar_dados(); st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)
    else:
        st.info("Toque em 'Novo' para começar!")

# ============================
# ABA: NOVO (Lançamento + Fixos)
# ============================
with aba_novo:
    aba_unit, aba_fixo = st.tabs(["Lançamento Único", "🗓️ Gerenciar Fixos"])
    with aba_unit:
        with st.form("form_novo", clear_on_submit=True):
            v = st.number_input("Valor", min_value=0.0)
            d = st.text_input("Descrição")
            t = st.radio("Tipo", ["Saída", "Entrada"], horizontal=True)
            stat = st.selectbox("Status", ["Pago", "Pendente", "Em Negociação"])
            c = st.selectbox("Categoria", CATEGORIAS)
            resp = st.selectbox("Responsável", PESSOAS, index=idx_pessoa("Ambos", PESSOAS))
            dt = st.date_input("Data/Vencimento", date.today())
            fixo_check = st.checkbox("Salvar na lista de Fixos")
            if st.form_submit_button("Salvar"):
                if v > 0:
                    inserir_transacao({
                        "data": str(dt), "descricao": d, "valor": float(v),
                        "tipo": t, "categoria": c, "status": stat,
                        "responsavel": resp
                    })
                    if fixo_check:
                        inserir_fixo({
                            "descricao": d, "valor": float(v), "categoria": c,
                            "responsavel": resp
                        })
                    st.success("Cadastrado!")
                    st.session_state.dados = buscar_dados()
                    st.session_state.fixos = buscar_fixos()
                    st.session_state.pessoas = buscar_pessoas()
                    st.rerun()
                else:
                    st.error("O valor deve ser maior que zero.")

    with aba_fixo:
        if not st.session_state.fixos.empty:
            for idx, row in st.session_state.fixos.iterrows():
                with st.expander(f"📌 {row['descricao']} - R$ {row['valor']:,.2f}"):
                    if st.button("Lançar neste mês", key=f"launch_{row['id']}"):
                        d_f = str(date(ano_ref, mes_num, 1))
                        inserir_transacao({
                            "data": d_f, "descricao": row['descricao'], "valor": float(row['valor']),
                            "tipo": "Saída", "categoria": row['categoria'], "status": "Pago",
                            "responsavel": row.get('responsavel', 'Ambos')
                        })
                        st.session_state.dados = buscar_dados()
                        st.toast("Lançado!")
                        st.rerun()
                    st.divider()
                    new_desc = st.text_input("Editar Descrição", value=row['descricao'], key=f"ed_d_{row['id']}")
                    new_val = st.number_input("Editar Valor", value=float(row['valor']), key=f"ed_v_{row['id']}")
                    new_resp = st.selectbox("Responsável", PESSOAS, index=idx_pessoa(row.get('responsavel', 'Ambos'), PESSOAS), key=f"ed_r_{row['id']}")
                    col_ed1, col_ed2 = st.columns(2)
                    if col_ed1.button("Salvar Alterações", key=f"save_fix_{row['id']}"):
                        atualizar_fixo(int(row['id']), {"descricao": new_desc, "valor": float(new_val), "responsavel": new_resp})
                        st.session_state.fixos = buscar_fixos(); st.rerun()
                    if col_ed2.button("❌ Remover Fixo", key=f"del_fix_{row['id']}"):
                        deletar_fixo(int(row['id']))
                        st.session_state.fixos = buscar_fixos(); st.rerun()
        else:
            st.caption("Sem fixos configurados.")

# ============================
# ABA: CAIXA / RELATÓRIOS
# ============================
with aba_reserva:
    st.markdown(
        f'<div class="reserva-card"><p style="margin:0;opacity:0.9;font-size:14px;">PATRIMÔNIO REAL</p><h2 style="margin:.4rem 0 0 0;">R$ {balanco:,.2f}</h2></div>',
        unsafe_allow_html=True
    )

    if not df_geral.empty:
        total_negoc = df_geral[df_geral['status'] == "Em Negociação"]['valor'].sum()
        if total_negoc > 0:
            st.warning(f"⚠️ Você possui **R$ {total_negoc:,.2f}** em dívidas em negociação (não afetando o patrimônio real).")

    st.markdown("### 📄 Relatórios")

    if not st.session_state.dados.empty:
        df_para_relatorio = st.session_state.dados.copy()
        df_para_relatorio['data'] = pd.to_datetime(df_para_relatorio['data'], errors='coerce')
        mask = (
            (df_para_relatorio['data'].dt.month == mes_num) &
            (df_para_relatorio['data'].dt.year == ano_ref)
        )
        df_para_relatorio = df_para_relatorio[mask].copy()
        df_para_relatorio = df_para_relatorio.sort_values(by=['data', 'descricao'], na_position='last')

        st.caption(f"🧾 Lançamentos no relatório: **{len(df_para_relatorio)}**")

        if not df_para_relatorio.empty:
            col_rel1, col_rel2 = st.columns(2)
            with col_rel1:
                st.download_button(
                    label="📥 Baixar Excel",
                    data=gerar_excel(df_para_relatorio),
                    file_name=f"Financeiro_{mes_nome}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            with col_rel2:
                st.download_button(
                    label="📥 Baixar PDF",
                    data=gerar_pdf(df_para_relatorio, mes_nome),
                    file_name=f"Financeiro_{mes_nome}.pdf",
                    mime="application/pdf"
                )
        else:
            st.caption("Selecione um mês com dados para gerar relatórios.")
    else:
        st.caption("Sem dados para gerar relatórios.")

# ============================
# ABA: NEGOCIAÇÃO
# ============================
with aba_negociacao:
    st.markdown("### 🤝 Contas em Negociação")
    st.info("💡 Acompanhamento de contas no status - Em negociação.")
    if st.session_state.dados.empty:
        st.info("Não há dados.")
    else:
        df_neg = st.session_state.dados.copy()
        if 'responsavel' not in df_neg.columns:
            df_neg['responsavel'] = 'Ambos'
        df_neg['responsavel'] = df_neg['responsavel'].fillna('Ambos').astype(str)
        df_neg = df_neg[df_neg['status'] == "Em Negociação"]

        col_f1, col_f2 = st.columns([2,1])
        resp_filtro = col_f1.selectbox("Responsável", ["Todos"] + PESSOAS, index=0)
        somente_mes = col_f2.checkbox("Mostrar apenas do mês selecionado", value=False)

        if resp_filtro != "Todos":
            df_neg = df_neg[df_neg['responsavel'] == resp_filtro]

        if somente_mes and 'data' in df_neg.columns:
            df_neg = df_neg[
                (df_neg['data'].dt.month == mes_num) &
                (df_neg['data'].dt.year == ano_ref)
            ]

        if df_neg.empty:
            st.caption("Sem itens em negociação com os filtros atuais.")
        else:
            total_neg = float(df_neg['valor'].sum())
            qtd_neg = int(len(df_neg))
            por_pessoa = df_neg.groupby('responsavel')['valor'].sum().sort_values(ascending=False)

            m1, m2 = st.columns(2)
            m1.metric("Total em Negociação", f"R$ {total_neg:,.2f}")
            m2.metric("Quantidade de Itens", str(qtd_neg))

            with st.expander("Ver totais por responsável", expanded=True):
                for pessoa, soma in por_pessoa.items():
                    st.write(f"**{pessoa}** — R$ {soma:,.2f}")

            st.markdown("#### Itens")
            for _, row in df_neg.sort_values(by='data', ascending=False).iterrows():
                icon = row['categoria'].split()[0] if " " in row['categoria'] else "💬"
                dt_txt = row['data'].strftime('%d/%m/%Y') if pd.notnull(row['data']) else '--/--/----'
                st.markdown(f"""
                <div class="transaction-card">
                  <div class="transaction-left">
                    <div class="card-icon">{icon}</div>
                    <div class="tc-info">
                      <div class="tc-title">{row['descricao']}</div>
                      <div class="tc-meta">{dt_txt} • <b>{row['categoria']}</b></div>
                      <div class="status-badge negociacao">Em Negociação</div>
                      <div class="tc-meta">Responsável: <b>{row.get('responsavel','Ambos')}</b></div>
                    </div>
                  </div>
                  <div class="transaction-right saida">R$ {row['valor']:,.2f}</div>
                </div>
                """, unsafe_allow_html=True)

                cA, cB, cC, cD = st.columns([1,1,2,1])
                with cA:
                    if st.button("Marcar Pendente", key=f"neg_to_pen_{row['id']}"):
                        atualizar_transacao(int(row['id']), {"status": "Pendente"})
                        st.session_state.dados = buscar_dados(); st.rerun()
                with cB:
                    if st.button("Marcar Pago", key=f"neg_to_pago_{row['id']}"):
                        atualizar_transacao(int(row['id']), {"status": "Pago"})
                        st.session_state.dados = buscar_dados(); st.rerun()
                with cC:
                    novo_resp = st.selectbox(
                        "Responsável",
                        PESSOAS,
                        index=idx_pessoa(row.get('responsavel', 'Ambos'), PESSOAS),
                        key=f"resp_{row['id']}"
                    )
                with cD:
                    if st.button("Salvar Resp.", key=f"save_resp_{row['id']}"):
                        atualizar_transacao(int(row['id']), {"responsavel": novo_resp})
                        st.session_state.dados = buscar_dados(); st.rerun()

                st.markdown("<br>", unsafe_allow_html=True)

# ============================
# ABA: METAS
# ============================
with aba_metas:
    st.info("💡 Exemplo: Defina R$ 1.000,00 para '🛒 Mercado' para controlar seus gastos essenciais.")
    for cat in CATEGORIAS:
        if cat != "💰 Salário":
            atual_m = float(st.session_state.metas.get(cat, 0))
            nova_meta = st.number_input(f"Meta {cat}", min_value=0.0, value=atual_m, key=f"meta_{cat}")
            if st.button(f"Atualizar {cat}", key=f"btn_meta_{cat}"):
                upsert_meta(cat, nova_meta)
                st.session_state.metas = buscar_metas(); st.rerun()

# ============================
# ABA: SONHOS
# ============================
with aba_sonhos:
    st.markdown("### 🎯 Calculadora de Sonhos")
    st.info("💡 Exemplo: 'Viagem de Férias' ou 'Troca de Carro'.")
    v_sonho = st.number_input("Custo do Objetivo (R$)", min_value=0.0)
    if v_sonho > 0:
        try:
            entradas_sonho = df_mes[df_mes['tipo'] == 'Entrada']['valor'].sum()
            saidas_sonho = df_mes[(df_mes['tipo'] == 'Saída') & (df_mes['status'] == 'Pago')]['valor'].sum()
            sobra_m = entradas_sonho - saidas_sonho
            if sobra_m > 0:
                m_f = int(v_sonho / sobra_m) + 1
                st.info(f"Faltam aprox. **{m_f} meses**.")
                progresso = min(max((balanco / v_sonho) if v_sonho > 0 else 0.0, 0.0), 1.0)
                st.progress(progresso)
            else:
                st.warning("Economize este mês para alimentar seu sonho!")
        except Exception:
            st.info("Projeção indisponível no momento.")
