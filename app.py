# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
from datetime import date
from supabase import create_client, Client
import io
import streamlit.components.v1 as components

# Relatórios e Exportação
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm

# ============================
# 1. CONFIGURAÇÃO DA PÁGINA
# ============================
st.set_page_config(
    page_title="Life OS 360",
    page_icon="🏡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================
# 2. CONEXÃO E FUNÇÕES DB
# ============================
@st.cache_resource
def init_connection():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception as e:
        st.error(f"Erro de conexão: {e}")
        return None

supabase = init_connection()

def buscar_dados_financeiros():
    res = supabase.table("transacoes").select("*").execute()
    df = pd.DataFrame(res.data)
    if df.empty:
        return pd.DataFrame(columns=['id', 'data', 'descricao', 'valor', 'tipo', 'categoria', 'status', 'responsavel'])
    df['data'] = pd.to_datetime(df['data'], errors='coerce')
    return df

def buscar_pessoas():
    try:
        res = supabase.table("vw_pessoas_ativas").select("*").execute()
        nomes = [r.get('nome') for r in res.data] if res.data else []
        return [n for n in nomes if n.lower() != 'ambos'] + ['Ambos']
    except:
        return ['Guilherme', 'Alynne', 'Ambos']

# ============================
# 3. RELATÓRIOS (PDF / EXCEL)
# ============================
def gerar_pdf(df, mes_nome):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()
    elements.append(Paragraph(f"Relatório Financeiro - {mes_nome}", styles['Title']))
    
    # Preparar dados para tabela
    data = [["Data", "Descrição", "Valor", "Tipo", "Responsável"]]
    for _, r in df.iterrows():
        data.append([r['data'].strftime('%d/%m/%Y'), r['descricao'], f"R$ {r['valor']:.2f}", r['tipo'], r['responsavel']])
    
    t = Table(data, colWidths=[25*mm, 60*mm, 30*mm, 25*mm, 30*mm])
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.grey),('TEXTCOLOR',(0,0),(-1,0),colors.whitesmoke)]))
    elements.append(t)
    doc.build(elements)
    return buffer.getvalue()

def gerar_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Financeiro')
    return output.getvalue()

# ============================
# 4. ESTILOS CSS
# ============================
def aplicar_estilos():
    st.markdown("""
    <style>
    .stApp { background-color: #F3F5F9; }
    [data-testid="stMetric"] { background: white; border-radius: 12px; border: 1px solid #D6DEE8; padding: 15px; box-shadow: 2px 2px 5px rgba(0,0,0,0.05); }
    .transaction-card { background: white; padding: 15px; border-radius: 12px; margin-bottom: 10px; border: 1px solid #E6ECF3; display: flex; justify-content: space-between; align-items: center; }
    .status-badge { font-size: 11px; padding: 3px 10px; border-radius: 20px; font-weight: bold; }
    .pago { background: #DCFCE7; color: #166534; }
    .pendente { background: #FEF3C7; color: #92400E; }
    </style>
    """, unsafe_allow_html=True)

# ============================
# 5. ABAS DO SISTEMA
# ============================

def aba_financeiro():
    st.title("💰 Gestão Financeira")
    
    # Sincronização de Estado
    if 'dados' not in st.session_state: st.session_state.dados = buscar_dados_financeiros()
    if 'pessoas' not in st.session_state: st.session_state.pessoas = buscar_pessoas()

    meses = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    c1, c2 = st.columns(2)
    mes_ref = c1.selectbox("Mês", meses, index=date.today().month - 1)
    ano_ref = c2.number_input("Ano", value=date.today().year)
    
    df_mes = st.session_state.dados[
        (st.session_state.dados['data'].dt.month == meses.index(mes_ref) + 1) & 
        (st.session_state.dados['data'].dt.year == ano_ref)
    ].copy()

    # Métricas
    ent = df_mes[df_mes['tipo'] == 'Entrada']['valor'].sum()
    sai = df_mes[(df_mes['tipo'] == 'Saída') & (df_mes['status'] == 'Pago')]['valor'].sum()
    
    m1, m2, m3 = st.columns(3)
    m1.metric("Ganhos", f"R$ {ent:,.2f}")
    m2.metric("Gastos (Pagos)", f"R$ {sai:,.2f}")
    m3.metric("Saldo Real", f"R$ {ent - sai:,.2f}")

    t1, t2, t3 = st.tabs(["📊 Extrato", "➕ Novo", "📄 Relatórios"])

    with t1:
        if df_mes.empty: st.info("Sem lançamentos.")
        for _, r in df_mes.sort_values(by='data', ascending=False).iterrows():
            cor_valor = "#0EA5E9" if r['tipo'] == "Entrada" else "#DC2626"
            st.markdown(f"""
            <div class="transaction-card">
                <div>
                    <b>{r['descricao']}</b><br><small>{r['data'].strftime('%d/%m')} | {r['responsavel']}</small>
                </div>
                <div style="text-align:right">
                    <b style="color:{cor_valor}">R$ {r['valor']:,.2f}</b><br>
                    <span class="status-badge {r['status'].lower()}">{r['status']}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

    with t2:
        with st.form("novo_fin"):
            f_desc = st.text_input("Descrição")
            f_val = st.number_input("Valor", min_value=0.0)
            f_tipo = st.radio("Tipo", ["Saída", "Entrada"], horizontal=True)
            f_resp = st.selectbox("Responsável", st.session_state.pessoas)
            if st.form_submit_button("Lançar"):
                supabase.table("transacoes").insert({
                    "data": str(date.today()), "descricao": f_desc, "valor": f_val,
                    "tipo": f_tipo, "responsavel": f_resp, "status": "Pago", "categoria": "Geral"
                }).execute()
                st.session_state.dados = buscar_dados_financeiros()
                st.success("Lançado!")
                st.rerun()

    with t3:
        st.download_button("📥 Baixar PDF", gerar_pdf(df_mes, mes_ref), f"Financeiro_{mes_ref}.pdf")
        st.download_button("📥 Baixar Excel", gerar_excel(df_mes), f"Financeiro_{mes_ref}.xlsx")

def aba_tarefas():
    st.title("🗓️ Tarefas & Reuniões")
    st.checkbox("Reunião de Alinhamento Semanal")
    st.checkbox("Pagar fatura do cartão")
    st.text_input("Nova tarefa...")

def aba_saude():
    st.title("🍎 Saúde")
    st.metric("Água Hoje", "1.2L / 3L", "+200ml")
    st.line_chart([78.5, 78.2, 77.9, 78.0])

# ============================
# 6. LOGIN E NAVEGAÇÃO
# ============================
def main():
    aplicar_estilos()

    if 'logado' not in st.session_state:
        st.session_state.logado = False

    # Tela de Login
    if not st.session_state.logado:
        st.markdown("<br><br>", unsafe_allow_html=True)
        col_l, col_r = st.columns([1, 1])
        with col_l:
            st.image("https://raw.githubusercontent.com/twitter/twemoji/master/assets/72x72/1f3e0.png", width=80)
            st.title("Life OS 360")
            st.subheader("Bem-vindo de volta!")
            
            # Tenta pegar a senha dos secrets, se não existir usa uma padrão para não quebrar
            senha_mestra = st.secrets.get("APP_PASSWORD", "1234")
            
            senha_input = st.text_input("Senha de Acesso", type="password")
            if st.button("Entrar"):
                if senha_input == senha_mestra:
                    st.session_state.logado = True
                    st.rerun()
                else:
                    st.error("Senha incorreta!")
        return

    # Menu Lateral
    with st.sidebar:
        st.title("🏠 Life OS")
        menu = st.radio("Navegação", ["💰 Financeiro", "🗓️ Tarefas", "🍎 Saúde"])
        st.divider()
        if st.button("Sair"):
            st.session_state.logado = False
            st.rerun()

    # Roteamento de Abas
    if menu == "💰 Financeiro": aba_financeiro()
    elif menu == "🗓️ Tarefas": aba_tarefas()
    elif menu == "🍎 Saúde": aba_saude()

if __name__ == "__main__":
    main()
