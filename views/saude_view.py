# views/saude_view.py
# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
from datetime import date, timedelta

from github_db import (
    buscar_habitos, inserir_habito, atualizar_habito, deletar_habito,
    buscar_habit_logs, inserir_habit_log, atualizar_habit_log, deletar_habit_log
)

# ---------------------------------------------
#  MAPEAMENTOS DE DIAS (PT ↔ CÓDIGO INTERNACIONAL)
# ---------------------------------------------
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


# ---------------------------------------------
#  FUNÇÃO MAIS SEGURA PARA AVALIAR RECORRÊNCIA
# ---------------------------------------------
def habito_planejado_para_dia(habit: dict, dia: date) -> bool:
    """
    Retorna True se o hábito deve aparecer no dia.
    - Se não tiver 'recurrence' => hábito diário => True
    - Se recurrence for inválido ou incompleto => tratar como diário
    - Se tipo for weekly => verifica se o dia está na lista
    """

    rec = habit.get("recurrence")

    if not rec or not isinstance(rec, dict):
        return True  # diário ou dado faltando

    rtype = rec.get("type", None)
    if rtype != "weekly":
        return True  # tipos futuros tratados como diário

    dias = rec.get("days", None)
    if not dias or not isinstance(dias, list):
        return True  # tratar como diário

    weekday = dia.weekday()  # seg=0 ... dom=6
    mapa = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    return mapa[weekday] in dias


# ---------------------------------------------
#  EXIBIÇÃO AMIGÁVEL DO CAMPO recurrence
# ---------------------------------------------
def formatar_recorrencia_pt(rec: dict | None) -> str:
    if not rec or not isinstance(rec, dict):
        return "Diário"

    if rec.get("type") != "weekly":
        return "Diário"

    dias = rec.get("days", [])
    if not dias:
        return "Semanal"

    dias_pt = [_COD_TO_PT.get(code, code) for code in dias]
    dias_pt = [d.capitalize() for d in dias_pt]
    return "Semanal (" + ", ".join(dias_pt) + ")"


# ---------------------------------------------
#  WIDGET MULTISELECT PARA RECORRÊNCIA SEMANAL
# ---------------------------------------------
def multiselect_dias_semana(label: str, default_codes: list[str] | None, key: str):
    if default_codes:
        defaults_pt = [_COD_TO_PT.get(code) for code in default_codes if code in _COD_TO_PT]
    else:
        defaults_pt = []

    dias_pt = [pt for pt, _ in _DIAS_COD_PT]
    selecionados_pt = st.multiselect(label, dias_pt, default=defaults_pt, key=key)
    return [_PT_TO_COD[pt] for pt in selecionados_pt if pt in _PT_TO_COD]


# ---------------------------------------------
#  FUNÇÃO PRINCIPAL: RENDERIZAÇÃO DA ABA SAÚDE
# ---------------------------------------------
def render_saude():

    # HEADER
    st.markdown("""
      <div class="header-container">
        <div class="main-title">💪 Saúde</div>
        <div class="slogan">Bons hábitos, todos os dias</div>
      </div>
    """, unsafe_allow_html=True)

    # -----------------------------
    # Carregamento inicial
    # -----------------------------
    if 'habitos' not in st.session_state:
        st.session_state.habitos = buscar_habitos()

    if 'habit_logs' not in st.session_state:
        st.session_state.habit_logs = buscar_habit_logs()

    # -----------------------------
    # FILTROS SUPERIORES
    # -----------------------------
    col_d1, col_d2, col_d3 = st.columns([1,1,1])
    dia_sel = col_d1.date_input("Dia", value=date.today(), key="saude_dia")
    mostrar_logs_rec = col_d2.selectbox("Histórico", ["7 dias", "14 dias", "30 dias"], index=1)
    mostrar_todos = col_d3.checkbox("Mostrar hábitos não planejados para o dia", value=False)

    # -----------------------------
    # FORM: ADICIONAR NOVO HÁBITO
    # -----------------------------
    with st.expander("➕ Novo hábito", expanded=False):
        with st.form("form_novo_habito", clear_on_submit=True):

            nome = st.text_input("Nome")
            modo = st.radio("Tipo", ["Diário", "Semanal (recorrente)"], horizontal=True)

            if modo == "Diário":
                meta = st.number_input("Meta por dia", min_value=0, value=1)
                unidade = st.text_input("Unidade", value="")
                recurrence = None
            else:
                dias = multiselect_dias_semana("Dias da semana", ["mon","wed","fri"], key="dias_semana_new")
                unidade = st.text_input("Unidade (ex.: vezes)", value="vezes")
                meta = 0
                recurrence = {"type": "weekly", "days": dias}

            if st.form_submit_button("Salvar"):
                if not nome.strip():
                    st.error("Informe o nome.")
                else:
                    inserir_habito({
                        "name": nome.strip(),
                        "unit": unidade.strip(),
                        "target_per_day": int(meta),
                        "recurrence": recurrence
                    })
                    st.success("Hábito criado!")
                    st.session_state.habitos = buscar_habitos()
                    st.rerun()

    # -----------------------------
    # DADOS EM DATAFRAME
    # -----------------------------
    df_h = pd.DataFrame(st.session_state.habitos)
    df_l = pd.DataFrame(st.session_state.habit_logs)

    # Garantir colunas
    for c in ["id","name","unit","target_per_day","recurrence"]:
        if c not in df_h.columns:
            df_h[c] = None

    # Logs do dia
    if df_l.empty:
        soma_dia = {}
    else:
        df_l["date"] = pd.to_datetime(df_l["date"], errors="coerce").dt.date
        soma_dia = df_l[df_l["date"] == dia_sel].groupby("habit_id")["amount"].sum().to_dict()

    # Ordenar hábitos por nome
    if "name" in df_h.columns:
        df_h = df_h.sort_values("name", na_position="last")

    st.markdown("### Hoje / Dia selecionado")

    algum = False

    # -----------------------------
    # LISTAGEM DOS HÁBITOS
    # -----------------------------
    for _, hb in df_h.iterrows():

        hid = hb.get("id")
        if hid is None or pd.isna(hid):
            continue

        hid = int(hid)

        # Verificar recorrência
        if not mostrar_todos and not habito_planejado_para_dia(hb, dia_sel):
            continue

        algum = True

        nome = hb.get("name") or "(sem nome)"
        unit = hb.get("unit") or ""
        rec = hb.get("recurrence")
        alvo = int(hb.get("target_per_day", 0) or 0)

        atual = float(soma_dia.get(hid, 0.0))

        is_semanal = (isinstance(rec, dict) and rec.get("type") == "weekly")

        # Progresso
        if is_semanal:
            progresso = 1.0 if atual > 0 else 0.0
            meta_txt = formatar_recorrencia_pt(rec)
            feito_txt = "Feito hoje" if atual > 0 else "Não feito"
        else:
            progresso = min(atual / alvo, 1.0) if alvo > 0 else 0.0
            meta_txt = f"Meta: {alvo} {unit}".strip()
            feito_txt = f"Feito: {atual:g} {unit}".strip()

        rec_txt = formatar_recorrencia_pt(rec)

        # Card
        st.markdown(f"""
        <div class="habit-card">
            <div class="habit-left">
                <div class="habit-icon">🏷️</div>
                <div class="hb-info">
                    <div class="hb-title">{nome}</div>
                    <div class="hb-meta">{meta_txt} • {feito_txt} • <i>{rec_txt}</i></div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.progress(progresso)

        # Ações
        c1, c2, c3, c4 = st.columns([1,1,2,2])

        with c1:
            if st.button("+1", key=f"hb_{hid}_plus1"):
                inserir_habit_log({"habit_id": hid, "date": dia_sel.isoformat(), "amount": 1})
                st.session_state.habit_logs = buscar_habit_logs()
                st.rerun()

        with c2:
            qtd = st.number_input("Qtd", min_value=0.0, value=0.0, key=f"hb_{hid}_qtd")
            if st.button("Adicionar", key=f"hb_{hid}_add"):
                if qtd > 0:
                    inserir_habit_log({"habit_id": hid, "date": dia_sel.isoformat(), "amount": float(qtd)})
                    st.session_state.habit_logs = buscar_habit_logs()
                    st.rerun()

        with c3:
            with st.expander("Editar"):
                novo_nome = st.text_input("Nome", value=nome, key=f"hb_{hid}_nome")
                tipo_edit = st.radio("Tipo", ["Diário", "Semanal (recorrente)"],
                                     index=0 if not is_semanal else 1,
                                     key=f"hb_{hid}_tipo")

                if tipo_edit == "Diário":
                    novo_alvo = st.number_input("Meta por dia", min_value=0, value=alvo, step=1, key=f"hb_{hid}_meta")
                    novo_unit = st.text_input("Unidade", value=unit, key=f"hb_{hid}_unit")
                    novo_recurrence = None
                else:
                    dias_default = rec["days"] if is_semanal else []
                    new_days = multiselect_dias_semana("Dias da semana", dias_default, key=f"hb_{hid}_days")
                    novo_unit = st.text_input("Unidade", value=unit or "vezes", key=f"hb_{hid}_unit2")
                    novo_alvo = 0
                    novo_recurrence = {"type": "weekly", "days": new_days}

                if st.button("Salvar", key=f"hb_{hid}_save"):
                    atualizar_habito(hid, {
                        "name": novo_nome.strip(),
                        "unit": novo_unit.strip(),
                        "target_per_day": novo_alvo,
                        "recurrence": novo_recurrence
                    })
                    st.session_state.habitos = buscar_habitos()
                    st.rerun()

        with c4:
            if st.button("Excluir", key=f"hb_{hid}_del"):
                deletar_habito(hid)
                st.session_state.habitos = buscar_habitos()
                st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)

    if not algum:
        st.info("Nenhum hábito para exibir (com os filtros atuais).")

    # -----------------------------
    # HISTÓRICO DE LOGS
    # -----------------------------
    st.divider()

    df_l = pd.DataFrame(st.session_state.habit_logs)

    if df_l.empty:
        st.caption("Sem logs registrados.")
        return

    dias_map = {"7 dias": 7, "14 dias": 14, "30 dias": 30}
    dias = dias_map[mostrar_logs_rec]
    inicio = date.today() - timedelta(days=dias)

    df_l["date"] = pd.to_datetime(df_l["date"], errors="coerce").dt.date
    df_recent = df_l[df_l["date"] >= inicio].copy()

    if df_recent.empty:
        st.caption("Sem logs nesse período.")
        return

    # Mapa de nomes
    df_h2 = pd.DataFrame(st.session_state.habitos)
    nomes = {int(r["id"]): r["name"] for _, r in df_h2.dropna(subset=["id"]).iterrows()}

    st.markdown("### Logs recentes")

    for _, lg in df_recent.sort_values("date", ascending=False).iterrows():

        lid = int(lg["id"])
        hid = int(lg["habit_id"])
        nome_h = nomes.get(hid, f"Hábito {hid}")
        data_txt = lg["date"].strftime("%d/%m/%Y")
        amount = lg["amount"]

        st.write(f"📝 {data_txt} — **{nome_h}** — {amount:g}")

        c1, c2, c3 = st.columns([1,1,2])
        with c1:
            novo = st.number_input("Qtd", min_value=0.0, value=float(amount), key=f"lg_{lid}_qtd")
        with c2:
            if st.button("Salvar", key=f"lg_{lid}_save"):
                atualizar_habit_log(lid, {"amount": float(novo)})
                st.session_state.habit_logs = buscar_habit_logs()
                st.rerun()
        with c3:
            if st.button("Excluir", key=f"lg_{lid}_del"):
                deletar_habit_log(lid)
                st.session_state.habit_logs = buscar_habit_logs()
                st.rerun()
