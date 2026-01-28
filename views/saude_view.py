# views/saude_view.py
# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
from datetime import date, timedelta

from github_db import (
    buscar_habitos, inserir_habito, atualizar_habito, deletar_habito,
    buscar_habit_logs, inserir_habit_log, atualizar_habit_log, deletar_habit_log
)

# -----------------------------
# Helpers de estado/carregamento
# -----------------------------
def recarregar():
    st.session_state.habitos = buscar_habitos()
    st.session_state.habit_logs = buscar_habit_logs()

# -----------------------------
# Helpers de recorrência semanal
# -----------------------------
_DIAS_COD_PT = [
    ("seg", "mon"),
    ("ter", "tue"),
    ("qua", "wed"),
    ("qui", "thu"),
    ("sex", "fri"),
    ("sab", "sat"),
    ("dom", "sun"),
]
_COD_TO_PT = {code: pt for pt, code in _DIAS_COD_PT}
_PT_TO_COD = {pt: code for pt, code in _DIAS_COD_PT}

def habito_planejado_para_dia(habit: dict, dia: date) -> bool:
    """
    Retorna True se o hábito está planejado para o 'dia' informado.
    - Sem recurrence => diário => True
    - Com recurrence.type == 'weekly' => verifica se o dia da semana está em recurrence.days
    """
    rec = habit.get("recurrence")
    if not rec:
        return True  # hábito diário tradicional
    rtype = rec.get("type")
    if rtype != "weekly":
        return True  # outros tipos (futuro) tratados como sempre visíveis
    weekday = dia.weekday()  # mon=0..sun=6
    mapa = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    dia_cod = mapa[weekday]
    return dia_cod in (rec.get("days") or [])

def formatar_recorrencia_pt(rec: dict | None) -> str:
    """Gera um texto amigável para exibir a recorrência semanal."""
    if not rec or rec.get("type") != "weekly":
        return "Diário"
    days = rec.get("days") or []
    if not days:
        return "Semanal (sem dias)"
    dias_pt = [k for code in days if (k := _COD_TO_PT.get(code))]
    # capitaliza primeira letra
    dias_pt_fmt = ", ".join(d.capitalize() for d in dias_pt)
    return f"Semanal ({dias_pt_fmt})"

def multiselect_dias_semana(label: str, default_codes: list[str] | None, key: str):
    """
    Multiselect em PT (seg..dom) que devolve lista de códigos ['mon','wed',...].
    """
    default_pt = []
    if default_codes:
        for code in default_codes:
            pt = _COD_TO_PT.get(code)
            if pt:
                default_pt.append(pt)

    dias_pt = [pt for pt, _ in _DIAS_COD_PT]
    selecionados_pt = st.multiselect(label, dias_pt, default=default_pt, key=key)
    return [_PT_TO_COD[pt] for pt in selecionados_pt if pt in _PT_TO_COD]

# -----------------------------
# Render principal da aba Saúde
# -----------------------------
def render_saude():
    st.markdown("""
      <div class="header-container">
        <div class="main-title">💪 Saúde</div>
        <div class="slogan">Bons hábitos, todos os dias</div>
      </div>
    """, unsafe_allow_html=True)

    # Carrega sessão
    if 'habitos' not in st.session_state:
        st.session_state.habitos = buscar_habitos()
    if 'habit_logs' not in st.session_state:
        st.session_state.habit_logs = buscar_habit_logs()

    # Controles superiores
    col_d1, col_d2, col_d3 = st.columns([1,1,1])
    dia_sel = col_d1.date_input("Dia", value=date.today(), key="hb_dia_sel")
    mostrar_logs_rec = col_d2.selectbox("Histórico de logs", options=["7 dias", "14 dias", "30 dias"], index=1, key="hb_hist_range")
    mostrar_nao_planejados = col_d3.checkbox("Mostrar hábitos não planejados para o dia", value=False, key="hb_show_all")

    # -----------------------------
    # Novo hábito (Diário ou Semanal)
    # -----------------------------
    with st.expander("➕ Novo hábito", expanded=False):
        with st.form("form_habito", clear_on_submit=True):
            nome = st.text_input("Nome do hábito (ex.: Beber água / Ir à academia)", key="hb_new_nome")
            modo = st.radio("Tipo de hábito", ["Diário", "Semanal (recorrência)"], horizontal=True, key="hb_new_tipo")
            if modo == "Diário":
                meta = st.number_input("Meta por dia", min_value=0, value=1, step=1, key="hb_new_meta")
                unidade = st.text_input("Unidade (ex.: copos, km, min)", key="hb_new_unit", value="")
                recurrence = None
            else:
                st.caption("Selecione os dias da semana para este hábito:")
                dias_codes = multiselect_dias_semana("Dias da semana", default_codes=["mon","wed","fri"], key="hb_new_days")
                unidade = st.text_input("Unidade (ex.: vezes, km, min)", key="hb_new_unit2", value="vezes")
                meta = 0  # desnecessário para semanal
                recurrence = {"type": "weekly", "days": dias_codes}

            if st.form_submit_button("Salvar"):
                if not nome.strip():
                    st.error("Informe o nome do hábito.")
                else:
                    inserir_habito({
                        "name": nome.strip(),
                        "target_per_day": int(meta),
                        "unit": unidade.strip(),
                        "recurrence": recurrence  # pode ser None
                    })
                    st.success("Hábito criado!")
                    recarregar()
                    st.rerun()

    # -----------------------------
    # Visão diária com progresso
    # -----------------------------
    habitos = st.session_state.habitos or []
    logs = st.session_state.habit_logs or []

    df_h = pd.DataFrame(habitos)
    df_l = pd.DataFrame(logs)

    if df_h.empty:
        # Garante colunas ao menos para evitar KeyError adiante
        df_h = pd.DataFrame(columns=['id','name','target_per_day','unit','recurrence'])

    # Normaliza colunas esperadas
    for c, default in [('id', None), ('name', None), ('target_per_day', 0), ('unit', ''), ('recurrence', None)]:
        if c not in df_h.columns:
            df_h[c] = default

    if df_l.empty:
        soma_dia = {}
    else:
        df_l['date'] = pd.to_datetime(df_l['date'], errors='coerce').dt.date
        soma_dia = df_l[df_l['date'] == dia_sel].groupby('habit_id')['amount'].sum().to_dict()

    st.markdown("### Hoje / Dia selecionado")

    # Ordena por nome (se houver)
    if 'name' in df_h.columns:
        df_h = df_h.sort_values('name', na_position='last')

    algum_mostrado = False
    for _, hb in df_h.iterrows():
        hid = hb.get('id')
        if pd.isna(hid):
            continue
        hid = int(hid)

        # Filtro de recorrência planejada
        if not mostrar_nao_planejados and not habito_planejado_para_dia(hb, dia_sel):
            continue

        algum_mostrado = True

        alvo = int(hb.get('target_per_day', 0) or 0)
        unit = hb.get('unit', '') or ''
        rec = hb.get('recurrence')
        atual = float(soma_dia.get(hid, 0.0))
        is_semanal = bool(rec and rec.get("type") == "weekly")

        # Progresso
        if is_semanal:
            # Para hábitos semanais, a métrica do dia é binária (feito hoje? amount > 0)
            progresso = 1.0 if atual > 0 else 0.0
            meta_txt = formatar_recorrencia_pt(rec)
            feito_txt = "Feito hoje ✅" if atual > 0 else "Não feito hoje"
        else:
            # Diário: progresso = atual / meta (se meta > 0)
            progresso = 0.0 if alvo <= 0 else min(atual / max(alvo, 1), 1.0)
            meta_txt = f"Meta diária: {alvo} {unit}".strip()
            feito_txt = f"Feito: {atual:.2f} {unit}".strip()

        nome_hab = hb.get('name') or "(sem nome)"
        rec_txt = formatar_recorrencia_pt(rec)

        st.markdown(f"""
        <div class="habit-card">
          <div class="habit-left">
            <div class="habit-icon">🏷️</div>
            <div class="hb-info">
              <div class="hb-title">{nome_hab}</div>
              <div class="hb-meta">{meta_txt} • {feito_txt} • <i>{rec_txt}</i></div>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)
        st.progress(progresso)

        # Ações rápidas
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
            # Editor completo do hábito, incluindo recorrência
            with st.expander("Editar Hábito"):
                nn = st.text_input("Nome", value=nome_hab, key=f"hb_en_{hid}")
                tipo_atual = "Semanal (recorrência)" if is_semanal else "Diário"
                tipo_edit = st.radio("Tipo de hábito", ["Diário", "Semanal (recorrência)"], index=0 if not is_semanal else 1, key=f"hb_tipo_{hid}", horizontal=True)

                if tipo_edit == "Diário":
                    nt = st.number_input("Meta por dia", min_value=0, value=int(alvo), step=1, key=f"hb_et_{hid}")
                    nu = st.text_input("Unidade", value=unit, key=f"hb_eu_{hid}")
                    new_recurrence = None
                    new_target = int(nt)
                    new_unit = nu.strip()
                else:
                    # semanal
                    dias_default = rec.get("days") if is_semanal else []
                    ndays = multiselect_dias_semana("Dias da semana", default_codes=dias_default, key=f"hb_days_{hid}")
                    nu = st.text_input("Unidade", value=unit or "vezes", key=f"hb_eu2_{hid}")
                    new_recurrence = {"type": "weekly", "days": ndays}
                    new_target = 0
                    new_unit = (nu or "vezes").strip()

                if st.button("Salvar alter.", key=f"hb_save_{hid}"):
                    atualizar_habito(hid, {
                        "name": nn.strip(),
                        "target_per_day": new_target,
                        "unit": new_unit,
                        "recurrence": new_recurrence
                    })
                    recarregar(); st.rerun()
        with c4:
            st.markdown('<div class="btn-danger">', unsafe_allow_html=True)
            if st.button("Excluir hábito", key=f"hb_del_{hid}"):
                deletar_habito(hid)
                recarregar(); st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

    if not algum_mostrado:
        st.info("Nenhum hábito para exibir com os filtros atuais.")

    st.divider()

    # -----------------------------
    # Histórico de logs recentes
    # -----------------------------
    if not df_l.empty and not df_h.empty:
        janela_map = {"7 dias": 7, "14 dias": 14, "30 dias": 30}
        dias = janela_map[mostrar_logs_rec]
        inicio = date.today() - timedelta(days=dias)

        df_l['date'] = pd.to_datetime(df_l['date'], errors='coerce').dt.date
        df_recent = df_l[df_l['date'] >= inicio].copy()

        # Mapa de nomes/unidades por habit_id
        nomes = {}
        units = {}
        for _, h in df_h.iterrows():
            hid = h.get('id')
            if pd.isna(hid): 
                continue
            hid = int(hid)
            nomes[hid] = h.get('name') or f"Hábito {hid}"
            units[hid] = h.get('unit') or ''

        st.markdown("### Logs recentes")
        if df_recent.empty:
            st.caption("Sem logs nesse período.")
        else:
            for _, lg in df_recent.sort_values(by=['date'], ascending=False).iterrows():
                lid_raw = lg.get('id')
                if pd.isna(lid_raw):
                    continue
                lid = int(lid_raw)
                h_id = int(lg.get('habit_id')) if pd.notnull(lg.get('habit_id')) else None
                nome_h = nomes.get(h_id, f"Hábito {h_id}") if h_id is not None else "(sem hábito)"
                unit_h = units.get(h_id, '')
                data_txt = lg['date'].strftime('%d/%m/%Y') if pd.notnull(lg['date']) else '—'
                amount = float(lg.get('amount', 0) or 0)

                st.write(f"📝 {data_txt} • **{nome_h}** — {amount:g} {unit_h}".rstrip())
                c1, c2, c3 = st.columns([1,1,2])
                with c1:
                    novo = st.number_input("Qtd.", min_value=0.0, value=float(amount), key=f"hb_lg_amt_{lid}")
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
