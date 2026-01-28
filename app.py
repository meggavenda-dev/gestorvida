# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
from datetime import date
from supabase import create_client, Client
import io
import streamlit.components.v1 as components
import bcrypt

# Relatórios
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm

# ============================
# CONFIGURAÇÃO DA PÁGINA
# ============================
st.set_page_config(
    page_title="Life OS 360",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================
# CONEXÃO SUPABASE
# ============================
try:
    url: str = st.secrets["SUPABASE_URL"]
    key: str = st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(url, key)
except Exception:
    st.error("Erro de conexão. Verifique os Secrets.")
    st.stop()

# ============================
# FUNÇÕES DE APOIO (DB)
# ============================
def buscar_pessoas():
    try:
        res = supabase.table("vw_pessoas_ativas").select("*").execute()
        if res.data:
            nomes = [r.get('nome') for r in res.data if r.get('nome')]
            return [n for n in nomes if n.lower() != 'ambos'] + ['Ambos']
    except: pass
    return ['Guilherme', 'Alynne', 'Ambos']

def buscar_dados_financeiros():
    res = supabase.table("transacoes").select("*").execute()
    df = pd.DataFrame(res.data)
    if df.empty: return pd.DataFrame(columns=['id', 'data', 'descricao', 'valor', 'tipo', 'categoria', 'status', 'responsavel'])
    df['data'] = pd.to_datetime(df['data'], errors='coerce')
    return df

# ============================
# CSS & STYLE (UNIFICADO)
# ============================
def aplicar_estilos():
    st.markdown("""
    <style>
    :root{ --brand: #2563EB; --bg: #F3F5F9; }
    .stApp { background: var(--bg); }
    [data-testid="stMetric"] { background: white; border-radius: 12px; border: 1px solid #D6DEE8; padding: 15px; }
    .transaction-card { background: white; padding: 12px; border-radius: 12px; margin-bottom: 8px; border: 1px solid #D6DEE8; display: flex; justify-content: space-between; align-items: center;}
    .status-badge { font-size: 10px; padding: 2px 8px; border-radius: 8px; font-weight: bold; text-transform: uppercase; }
    .pago { background: #DCFCE7; color: #166534; }
    .pendente { background: #FEF3C7; color: #92400E; }
    /* Mobile Ajustes */
    @media (max-width: 480px) { .main-title { font-size: 1.5rem; } }
    </style>
    """, unsafe_allow_html=True)

# ============================
# ABA 1: FINANCEIRO (INTEGRADA)
# ============================
def aba_financeiro():
    st.markdown('<h1 style="color:#1E293B;">💰 Gestão Financeira</h1>', unsafe_allow_html=True)
    
    # Sincronização
    if 'dados' not in st.session_state: st.session_state.dados = buscar_dados_financeiros()
    if 'pessoas' not in st.session_state: st.session_state.pessoas = buscar_pessoas()
    
    meses = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    col_m, col_a = st.columns(2)
    mes_sel = col_m.selectbox("Mês Referência", meses, index=date.today().month -1)
    ano_sel = col_a.number_input("Ano Referência", value=date.today().year)
    
    mes_num = meses.index(mes_sel) + 1
    df = st.session_state.dados.copy()
    df_mes = df[(df['data'].dt.month == mes_num) & (df['data'].dt.year == ano_sel)]

    # Métricas Rápidas
    in_val = df_mes[df_mes['tipo'] == 'Entrada']['valor'].sum()
    out_val = df_mes[(df_mes['tipo'] == 'Saída') & (df_mes['status'] == 'Pago')]['valor'].sum()
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Entradas", f"R$ {in_val:,.2f}")
    c2.metric("Saídas Pagas", f"R$ {out_val:,.2f}")
    c3.metric("Saldo", f"R$ {in_val - out_val:,.2f}")

    # Sub-abas do financeiro
    tab_list, tab_add = st.tabs(["📑 Extrato", "➕ Novo Lançamento"])
    
    with tab_list:
        for _, row in df_mes.sort_values(by='data', ascending=False).iterrows():
            st.markdown(f"""
            <div class="transaction-card">
                <div>
                    <b>{row['descricao']}</b><br>
                    <small>{row['data'].strftime('%d/%m')} | {row['responsavel']}</small>
                </div>
                <div style="text-align:right">
                    <span style="color:{'#0EA5E9' if row['tipo']=='Entrada' else '#DC2626'}">
                        R$ {row['valor']:,.2f}
                    </span><br>
                    <span class="status-badge {row['status'].lower()}">{row['status']}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

    with tab_add:
        with st.form("add_fin"):
            desc = st.text_input("Descrição")
            valor = st.number_input("Valor", min_value=0.0)
            tipo = st.radio("Tipo", ["Saída", "Entrada"], horizontal=True)
            resp = st.selectbox("Quem?", st.session_state.pessoas)
            if st.form_submit_button("Salvar"):
                supabase.table("transacoes").insert({
                    "descricao": desc, "valor": valor, "tipo": tipo, 
                    "responsavel": resp, "data": str(date.today()), "status": "Pago"
                }).execute()
                st.session_state.dados = buscar_dados_financeiros()
                st.rerun()

# ============================
# ABA 2: TAREFAS
# ============================
def aba_tarefas():
    st.markdown('<h1 style="color:#1E293B;">🗓️ Tarefas & Reuniões</h1>', unsafe_allow_html=True)
    
    with st.expander("➕ Nova Tarefa/Compromisso", expanded=False):
        with st.form("form_tarefa"):
            task = st.text_input("O que precisa ser feito?")
            cat = st.selectbox("Categoria", ["Trabalho", "Casa", "Estudo", "Saúde"])
            prazo = st.date_input("Prazo")
            if st.form_submit_button("Agendar"):
                # Aqui iria o insert no supabase (tabela tarefas)
                st.success("Tarefa adicionada!")

    st.write("### Pendentes")
    st.checkbox("Finalizar fechamento do mês")
    st.checkbox("Levar o carro na revisão")

# ============================
# ABA 3: SAÚDE
# ============================
def aba_saude():
    st.markdown('<h1 style="color:#1E293B;">🍎 Saúde & Bem-estar</h1>', unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Consumo de Água", "1.8L", "Meta: 3L")
        st.button("🥤 +250ml")
    with col2:
        st.metric("Peso", "78.5 kg", "-0.2 kg")
    
    st.write("### Progresso de Peso")
    st.line_chart(pd.DataFrame([79, 78.8, 78.5, 78.7, 78.5], columns=["Peso"]))

# ============================
# ABA 4: ESTUDOS
# ============================
def aba_estudos():
    st.markdown('<h1 style="color:#1E293B;">📚 Central de Estudos</h1>', unsafe_allow_html=True)
    
    materias = {"Python para Dados": 0.75, "Inglês": 0.40, "Finanças Quantitativas": 0.15}
    
    for mat, prog in materias.items():
        st.write(f"**{mat}**")
        st.progress(prog)
    
    st.info("💡 Continue assim! Você estudou 4.5 horas esta semana.")

# ============================
# MAIN APP & LOGIN
# ============================
def main():
    aplicar_estilos()

    # Login Simples (Session State)
    if 'logado' not in st.session_state:
        st.session_state.logado = False

    if not st.session_state.logado:
        st.title("🔐 Life OS - Acesso")
        senha = st.text_input("Senha de acesso", type="password")
        if st.button("Entrar"):
            if senha == st.secrets["APP_PASSWORD"]: # Defina nos secrets
                st.session_state.logado = True
                st.rerun()
            else: st.error("Incorreto")
        return

    # Menu Lateral
    with st.sidebar:
        st.image("https://raw.githubusercontent.com/twitter/twemoji/master/assets/72x72/1f3e0.png", width=50)
        st.title("Life OS 360")
        st.divider()
        menu = st.radio("Ir para:", ["💰 Financeiro", "🗓️ Tarefas", "🍎 Saúde", "📚 Estudos"])
        st.spacer = st.container()
        if st.button("Sair"):
            st.session_state.logado = False
            st.rerun()

    # Roteamento
    if "Financeiro" in menu: aba_financeiro()
    elif "Tarefas" in menu: aba_tarefas()
    elif "Saúde" in menu: aba_saude()
    elif "Estudos" in menu: aba_estudos()

if __name__ == "__main__":
    main()
