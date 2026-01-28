# views/financeiro_view.py
# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
from datetime import date
import io

# ReportLab
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm

# GitHub DB
from github_db import (
    buscar_pessoas, buscar_dados, buscar_metas, buscar_fixos,
    inserir_transacao, atualizar_transacao, deletar_transacao,
    upsert_meta, inserir_fixo, atualizar_fixo, deletar_fixo
)

# Confirmação de exclusão (UI helper)
from ui_helpers import confirmar_exclusao

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
    if 'tipo' not in df_exp.columns:
        df_exp['tipo'] = ''
    else:
        df_exp['tipo'] = df_exp['tipo'].fillna('').astype(str)
    if 'status' not in df_exp.columns:
        df_exp['status'] = 'Pago'
    df_exp['status'] = df_exp['status'].fillna('Pago').astype(str)
    if 'responsavel' not in df_exp.columns:
        df_exp['responsavel'] = 'Ambos'
    df_exp['responsavel'] = df_exp['responsavel'].fillna('Ambos').astype(str)
    df_exp = df_exp.sort_values(by=['data', 'descricao'], na_position='last')

    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=12*mm, rightMargin=12*mm, topMargin=14*mm, bottomMargin=14*mm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleCenter', parent=styles['Heading1'], alignment=1, fontName='Helvetica-Bold', fontSize=16, leading=20, spaceAfter=6)
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

def idx_pessoa(valor: str, pessoas: list[str]) -> int:
    try:
        return pessoas.index(valor)
    except Exception:
        return pessoas.index('Ambos') if 'Ambos' in pessoas else 0

def render_financeiro():
    # Header (local da aba)
    st.markdown("""
      <div class="header-container">
        <div class="main-title">💰 Financeiro</div>
        <div class="slogan">Gestão inteligente para o seu lar</div>
      </div>
    """, unsafe_allow_html=True)

    # Sincronização inicial em sessão
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

    # Navegação de Mês/Ano com +/-
    hoje = date.today()
    if 'fin_mes' not in st.session_state:
        st.session_state.fin_mes = hoje.month
    if 'fin_ano' not in st.session_state:
        st.session_state.fin_ano = hoje.year

    c_nav1, c_nav2, c_nav3, c_nav4 = st.columns([0.6, 2.4, 1, 0.6])
    prev = c_nav1.button("◀", key="fin_prev_m", help="Mês anterior")
    mes_nome = c_nav2.selectbox("Mês", meses, index=st.session_state.fin_mes - 1)
    ano_ref = c_nav3.number_input("Ano", value=st.session_state.fin_ano, step=1)
    nxt = c_nav4.button("▶", key="fin_next_m", help="Próximo mês")

    st.session_state.fin_mes = meses.index(mes_nome) + 1
    st.session_state.fin_ano = int(ano_ref)

    if prev:
        if st.session_state.fin_mes == 1:
            st.session_state.fin_mes = 12
            st.session_state.fin_ano -= 1
        else:
            st.session_state.fin_mes -= 1
        st.rerun()
    if nxt:
        if st.session_state.fin_mes == 12:
            st.session_state.fin_mes = 1
            st.session_state.fin_ano += 1
        else:
            st.session_state.fin_mes += 1
        st.rerun()

    mes_num = st.session_state.fin_mes
    ano_ref = st.session_state.fin_ano

    # Processamento
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

    # Abas internas do Financeiro
    aba_resumo, aba_novo, aba_reserva, aba_negociacao, aba_metas, aba_sonhos = st.tabs(
        ["📊 Mês", "➕ Novo", "🏦 Caixa", "🤝 Negociação", "🎯 Metas", "🚀 Sonhos"]
    )

    with aba_resumo:
        if not df_atrasados_passado.empty:
            total_atrasado = df_atrasados_passado['valor'].sum()
            with st.expander(f"⚠️ CONTAS PENDENTES DE MESES ANTERIORES: R$ {total_atrasado:,.2f}", expanded=True):
                for _, row in df_atrasados_passado.iterrows():
                    col_at1, col_at2 = st.columns([3, 1])
                    dt_txt = row['data'].strftime('%d/%m/%y') if pd.notnull(row['data']) else '--/--/--'
                    col_at1.write(f"**{row['descricao']}** ({dt_txt}) — **Resp.: {row.get('responsavel','Ambos')}**")
                    if col_at2.button("✔ Pagar", key=f"fin_pay_at_{row['id']}"):
                        atualizar_transacao(int(row['id']), {"status": "Pago"})
                        st.toast("Pagamento registrado.")
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
                    dias_diff = (row['data'].date() - date.today()).days
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
                    if s_text != "Pago" and st.button("✔ Pagar", key=f"fin_pay_{row['id']}"):
                        atualizar_transacao(int(row['id']), {"status": "Pago"})
                        st.toast("Pagamento registrado.")
                        st.session_state.dados = buscar_dados(); st.rerun()
                with cd:
                    st.markdown('<div class="btn-danger">', unsafe_allow_html=True)
                    if st.button("Excluir", key=f"fin_del_{row['id']}"):
                        confirmar_exclusao(f"dlg_fin_{row['id']}", "Confirmar exclusão", lambda: deletar_transacao(int(row['id'])))
                    st.markdown('</div>', unsafe_allow_html=True)

                st.markdown("<br>", unsafe_allow_html=True)
        else:
            st.info("Toque em 'Novo' para começar!")

    with aba_novo:
        aba_unit, aba_fixo = st.tabs(["Lançamento Único", "🗓️ Gerenciar Fixos"])
        with aba_unit:
            with st.form("form_fin_novo", clear_on_submit=True):
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
                        if st.button("Lançar neste mês", key=f"fin_launch_{row['id']}"):
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
                        new_desc = st.text_input("Editar Descrição", value=row['descricao'], key=f"fin_ed_d_{row['id']}")
                        new_val = st.number_input("Editar Valor", value=float(row['valor']), key=f"fin_ed_v_{row['id']}")
                        new_resp = st.selectbox("Responsável", PESSOAS, index=idx_pessoa(row.get('responsavel', 'Ambos'), PESSOAS), key=f"fin_ed_r_{row['id']}")
                        col_ed1, col_ed2 = st.columns(2)
                        if col_ed1.button("Salvar Alterações", key=f"fin_save_fix_{row['id']}"):
                            atualizar_fixo(int(row['id']), {"descricao": new_desc, "valor": float(new_val), "responsavel": new_resp})
                            st.session_state.fixos = buscar_fixos(); st.rerun()
                        if col_ed2.button("❌ Remover Fixo", key=f"fin_del_fix_{row['id']}"):
                            confirmar_exclusao(f"dlg_fix_{row['id']}", "Confirmar exclusão", lambda: deletar_fixo(int(row['id'])))
            else:
                st.caption("Sem fixos configurados.")

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

            st.caption(f"🧾 {len(df_para_relatorio)} lançamentos em **{mes_nome}/{ano_ref}**")

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
                        if st.button("Marcar Pendente", key=f"fin_neg_to_pen_{row['id']}"):
                            atualizar_transacao(int(row['id']), {"status": "Pendente"})
                            st.session_state.dados = buscar_dados(); st.rerun()
                    with cB:
                        if st.button("Marcar Pago", key=f"fin_neg_to_pago_{row['id']}"):
                            atualizar_transacao(int(row['id']), {"status": "Pago"})
                            st.session_state.dados = buscar_dados(); st.rerun()
                    with cC:
                        novo_resp = st.selectbox(
                            "Responsável",
                            PESSOAS,
                            index=idx_pessoa(row.get('responsavel', 'Ambos'), PESSOAS),
                            key=f"fin_resp_{row['id']}"
                        )
                    with cD:
                        if st.button("Salvar Resp.", key=f"fin_save_resp_{row['id']}"):
                            atualizar_transacao(int(row['id']), {"responsavel": novo_resp})
                            st.session_state.dados = buscar_dados(); st.rerun()

                    st.markdown("<br>", unsafe_allow_html=True)

    with aba_metas:
        st.info("💡 Exemplo: Defina R$ 1.000,00 para '🛒 Mercado' para controlar seus gastos essenciais.")
        for cat in CATEGORIAS:
            if cat != "💰 Salário":
                atual_m = float(st.session_state.metas.get(cat, 0))
                nova_meta = st.number_input(f"Meta {cat}", min_value=0.0, value=atual_m, key=f"fin_meta_{cat}")
                if st.button(f"Atualizar {cat}", key=f"fin_btn_meta_{cat}"):
                    upsert_meta(cat, nova_meta)
                    st.session_state.metas = buscar_metas(); st.rerun()

    with aba_sonhos:
        st.markdown("### 🎯 Calculadora de Sonhos")
        st.info("💡 Exemplo: 'Viagem de Férias' ou 'Troca de Carro'.")
        v_sonho = st.number_input("Custo do Objetivo (R$)", min_value=0.0, key="fin_custo_sonho")
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
