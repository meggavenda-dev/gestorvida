# views/saude_view.py
# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
from datetime import date, timedelta

from github_db import (
    buscar_habitos, inserir_habito, atualizar_habito, deletar_habito,
    buscar_habit_logs, inserir_habit_log, atualizar_habit_log, deletar_habit_log
)

def recarregar():
    st.session_state.habitos = buscar_habitos()
    st.session_state.habit_logs = buscar_habit_logs()

def render_saude():
    st.markdown("""
      <div class="header-container">
        <div class="main-title">💪 Saúde</div>
        <div class="slogan">Bons hábitos, todos os dias</div>
      </div>
    """, unsafe_allow_html=True)

    if 'habitos' not in st.session_state:
        st.session_state.habitos = buscar_habitos()
    if 'habit_logs' not in st.session_state:
        st.session_state.habit_logs = buscar_habit_logs()

    col_d1, col_d2 = st.columns([1,1])
    dia_sel = col_d1.date_input("Dia", value=date.today())
    mostrar_logs_rec = col_d2.selectbox("Histórico de logs", options=["7 dias", "14 dias", "30 dias"], index=1)

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

    habitos = st.session_state.habitos
    logs = st.session_state.habit_logs

    df_h = pd.DataFrame(habitos)
    df_l = pd.DataFrame(logs)
    if df_h.empty:
        st.info("Nenhum hábito cadastrado. Adicione um acima.")
    else:
        if not df_l.empty:
            df_l['date'] = pd.to_datetime(df_l['date'], errors='coerce').dt.date
            soma_dia = df_l[df_l['date'] == dia_sel].groupby('habit_id')['amount'].sum().to_dict()
        else:
            soma_dia = {}

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
                if st.button("+1", key=f"hb_inc_{hid}"):
                    inserir_habit_log({"habit_id": hid, "date": dia_sel.isoformat(), "amount": 1})
                    recarregar(); st.rerun()
            with c2:
                val = st.number_input("Qtd.", min_value=0.0, value=0.0, key=f"hb_amt_{hid}")
                if st.button("Adicionar", key=f"hb_add_{hid}"):
                    if val > 0:
                        inserir_habit_log({"habit_id": hid, "date": dia_sel.isoformat(), "amount": float(val)})
                        recarregar(); st.rerun()
            with c3:
                with st.expander("Editar Hábito"):
                    nn = st.text_input("Nome", value=hb.get('name',''), key=f"hb_en_{hid}")
                    nt = st.number_input("Meta por dia", min_value=0, value=int(alvo), step=1, key=f"hb_et_{hid}")
                    nu = st.text_input("Unidade", value=unit, key=f"hb_eu_{hid}")
                    if st.button("Salvar alter.", key=f"hb_save_{hid}"):
                        atualizar_habito(hid, {"name": nn.strip(), "target_per_day": int(nt), "unit": nu.strip()})
                        recarregar(); st.rerun()
            with c4:
                st.markdown('<div class="btn-danger">', unsafe_allow_html=True)
                if st.button("Excluir hábito", key=f"hb_del_{hid}"):
                    deletar_habito(hid)
                    recarregar(); st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

        st.divider()

    # Histórico de logs
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
                novo = st.number_input("Qtd.", min_value=0.0, value=float(lg['amount']), key=f"hb_lg_amt_{lid}")
            with c2:
                if st.button("Salvar", key=f"hb_lg_save_{lid}"):
                    atualizar_habit_log(lid, {"amount": float(novo)})
                    recarregar(); st.rerun()
            with c3:
                st.markdown('<div class="btn-danger">', unsafe_allow_html=True)
                if st.button("Excluir", key=f"hb_lg_del_{lid}"):
                    deletar_habit_log(lid)
                    recarregar(); st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.caption("Sem logs para exibir.")
