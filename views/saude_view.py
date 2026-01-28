# views/saude_view.py
# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
from datetime import date, timedelta

from github_db import (
    # Config
    buscar_saude_config, upsert_saude_config,
    # Peso
    buscar_peso_logs, inserir_peso, atualizar_peso, deletar_peso,
    # Água
    buscar_agua_logs, inserir_agua, atualizar_agua, deletar_agua,
    # Treinos
    buscar_workout_logs, inserir_workout_log, atualizar_workout_log, deletar_workout_log,
)

from ui_helpers import confirmar_exclusao

# ----------------------------
# Utils
# ----------------------------
def _to_date(x):
    try:
        return pd.to_datetime(x, errors="coerce").date()
    except Exception:
        return None

def _ensure_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default

def _ensure_int(x, default=0):
    try:
        return int(x)
    except Exception:
        return default

def _semana_range(ref: date, dias=7):
    fim = ref
    ini = ref - timedelta(days=dias-1)
    return ini, fim

def _formata_val(n, sufixo=""):
    return f"{n:,.2f}{sufixo}".replace(",", "X").replace(".", ",").replace("X", ".")

# ----------------------------
# Ações rápidas de água
# ----------------------------
def _add_agua_quick(ml: int):
    inserir_agua({"date": date.today().isoformat(), "amount_ml": int(ml)})
    st.session_state.agua_logs = buscar_agua_logs()
    st.toast(f"+{ml} ml adicionados"); st.rerun()

# ---------------------------------------------
#  RENDER
# ---------------------------------------------
def render_saude():

    # Header
    st.markdown("""
      <div class="header-container">
        <div class="main-title">💪 Saúde</div>
        <div class="slogan">Peso, água e treinos — simples e prático</div>
      </div>
    """, unsafe_allow_html=True)

    # Estado inicial
    if "saude_cfg" not in st.session_state:
        st.session_state.saude_cfg = buscar_saude_config()
    if "peso_logs" not in st.session_state:
        st.session_state.peso_logs = buscar_peso_logs()
    if "agua_logs" not in st.session_state:
        st.session_state.agua_logs = buscar_agua_logs()
    if "w_logs" not in st.session_state:
        st.session_state.w_logs = buscar_workout_logs()

    agua_goal = int(st.session_state.saude_cfg.get("water_goal_ml", 2000))

    aba_painel, aba_peso, aba_agua, aba_treinos = st.tabs(["📊 Painel", "⚖️ Peso", "💧 Água", "🏋️ Treinos"])

    # =======================
    # 📊 Painel
    # =======================
    with aba_painel:
        hoje = date.today()
        ini7, fim7 = _semana_range(hoje, dias=7)

        # Peso
        dfp = pd.DataFrame(st.session_state.peso_logs)
        if not dfp.empty:
            dfp["date"] = dfp["date"].apply(_to_date)
            dfp = dfp.dropna(subset=["date"]).sort_values("date")
            ultimo = dfp.iloc[-1]
            peso_hoje = ultimo["weight_kg"]
            # Delta 7d
            dfp7 = dfp[dfp["date"] >= ini7]
            delta_7 = None
            if len(dfp7) >= 2:
                delta_7 = peso_hoje - dfp7.iloc[0]["weight_kg"]
        else:
            peso_hoje, delta_7 = None, None

        # Água (dia)
        dfa = pd.DataFrame(st.session_state.agua_logs)
        agua_hoje = 0
        if not dfa.empty:
            dfa["date"] = dfa["date"].apply(_to_date)
            agua_hoje = float(dfa[dfa["date"] == hoje]["amount_ml"].sum())

        # Treinos (7d)
        dfw = pd.DataFrame(st.session_state.w_logs)
        sessoes_7d = 0
        volume_7d = 0.0
        if not dfw.empty:
            dfw["date"] = dfw["date"].apply(_to_date)
            dfw7 = dfw[(dfw["date"] >= ini7) & (dfw["date"] <= fim7)].copy()
            if not dfw7.empty:
                # sessão = cada dia com pelo menos 1 log
                sessoes_7d = dfw7["date"].nunique()
                dfw7["vol"] = dfw7["reps"].apply(_ensure_int) * dfw7["weight_kg"].apply(_ensure_float)
                volume_7d = float(dfw7["vol"].sum())

        c1, c2, c3 = st.columns(3)
        with c1:
            if peso_hoje is None:
                st.metric("Peso (último)", "—")
            else:
                delta_txt = None if delta_7 is None else f"{delta_7:+.1f} kg (7d)"
                st.metric("Peso (último)", f"{peso_hoje:.1f} kg", delta=delta_txt)

        with c2:
            prog = min(agua_hoje / agua_goal, 1.0) if agua_goal > 0 else 0.0
            st.metric("Água (hoje)", f"{int(agua_hoje)} / {agua_goal} ml")
            st.progress(prog)
            ca1, ca2, ca3 = st.columns(3)
            # 🔑 KEYS ÚNICAS NO PAINEL
            if ca1.button("+250 ml", key="painel_add_agua_250"): _add_agua_quick(250)
            if ca2.button("+500 ml", key="painel_add_agua_500"): _add_agua_quick(500)
            if ca3.button("+750 ml", key="painel_add_agua_750"): _add_agua_quick(750)

        with c3:
            st.metric("Treinos (7 dias)", f"{sessoes_7d} dia(s)", delta=f"Vol.: {_formata_val(volume_7d,' kg')}")
            st.caption("Volume = soma(reps × carga)")

    # =======================
    # ⚖️ Peso
    # =======================
    with aba_peso:
        st.markdown("### Registrar peso")
        with st.form("form_peso", clear_on_submit=True):
            colp1, colp2, colp3 = st.columns(3)
            dt = colp1.date_input("Data", value=date.today())
            w = colp2.number_input("Peso (kg)", min_value=0.0, step=0.1)
            bf = colp3.number_input("% Gordura (opcional)", min_value=0.0, step=0.1, value=0.0)
            wc = st.number_input("Cintura (cm, opcional)", min_value=0.0, step=0.5, value=0.0)
            if st.form_submit_button("Salvar"):
                inserir_peso({
                    "date": dt.isoformat(),
                    "weight_kg": float(w),
                    "body_fat_pct": bf if bf > 0 else None,
                    "waist_cm": wc if wc > 0 else None
                })
                st.session_state.peso_logs = buscar_peso_logs()
                st.success("Peso registrado!"); st.rerun()

        df = pd.DataFrame(st.session_state.peso_logs)
        if df.empty:
            st.info("Sem medições ainda.")
        else:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
            df = df.dropna(subset=["date"]).sort_values("date")
            col_g1, col_g2 = st.columns([2,1])
            with col_g1:
                st.markdown("#### Evolução (30 dias)")
                ult30 = df[df["date"] >= (pd.Timestamp(date.today()) - pd.Timedelta(days=30))]
                if ult30.empty: ult30 = df
                chart_df = ult30.set_index("date")[["weight_kg"]]
                st.line_chart(chart_df, height=220)

            with col_g2:
                st.markdown("#### Últimas medições")
                for _, r in df.tail(10).iloc[::-1].iterrows():
                    dt_txt = r["date"].strftime("%d/%m/%Y")
                    st.write(f"• {dt_txt} — **{r['weight_kg']:.1f} kg**")

            st.markdown("#### Editar / Excluir")
            for _, r in df.tail(10).iloc[::-1].iterrows():
                lid = int(r["id"])
                cols = st.columns([1,1,1,1])
                with cols[0]:
                    st.caption(r["date"].strftime("%d/%m/%Y"))
                with cols[1]:
                    nw = st.number_input("kg", value=float(r["weight_kg"]), step=0.1, key=f"pw_{lid}")
                with cols[2]:
                    if st.button("Salvar", key=f"psv_{lid}"):
                        atualizar_peso(lid, {"weight_kg": float(nw)})
                        st.session_state.peso_logs = buscar_peso_logs(); st.toast("Atualizado"); st.rerun()
                with cols[3]:
                    st.markdown('<div class="btn-danger">', unsafe_allow_html=True)
                    if st.button("Excluir", key=f"pdel_{lid}"):
                        confirmar_exclusao(f"dlg_p_{lid}", "Confirmar exclusão", lambda: deletar_peso(lid))
                    st.markdown('</div>', unsafe_allow_html=True)

    # =======================
    # 💧 Água
    # =======================
    with aba_agua:
        st.markdown("### Meta diária e registro")
        col_a1, col_a2 = st.columns([1,2])
        with col_a1:
            meta = st.number_input("Meta diária (ml)", min_value=0, step=100, value=int(agua_goal), key="agua_meta_input")
            if st.button("Salvar meta", key="agua_meta_save"):
                upsert_saude_config({"water_goal_ml": int(meta)})
                st.session_state.saude_cfg = buscar_saude_config()
                st.toast("Meta atualizada")
        with col_a2:
            st.caption("Toques rápidos:")
            cqa, cqb, cqc, cqd = st.columns(4)
            # 🔑 KEYS ÚNICAS NA ABA ÁGUA (primeiro bloco)
            if cqa.button("+250 ml", key="agua_add_250_top"): _add_agua_quick(250)
            if cqb.button("+500 ml", key="agua_add_500_top"): _add_agua_quick(500)
            if cqc.button("+750 ml", key="agua_add_750_top"): _add_agua_quick(750)
            if cqd.button("+1000 ml", key="agua_add_1000_top"): _add_agua_quick(1000)

        # Dia atual
        dfa = pd.DataFrame(st.session_state.agua_logs)
        hoje = date.today()
        if dfa.empty:
            total_hoje = 0
        else:
            dfa["date"] = dfa["date"].apply(_to_date)
            total_hoje = float(dfa[dfa["date"] == hoje]["amount_ml"].sum())

        st.markdown("#### Hoje")
        st.metric("Consumido", f"{int(total_hoje)} / {int(st.session_state.saude_cfg.get('water_goal_ml', 2000))} ml")
        st.progress(min(total_hoje / max(1, int(st.session_state.saude_cfg.get('water_goal_ml', 2000))), 1.0))
        with st.form("form_agua_add", clear_on_submit=True):
            amt = st.number_input("Adicionar (ml)", min_value=0, step=50, value=250, key="agua_amt_input")
            if st.form_submit_button("Adicionar"):
                inserir_agua({"date": hoje.isoformat(), "amount_ml": int(amt)})
                st.session_state.agua_logs = buscar_agua_logs()
                st.success("Água registrada!"); st.rerun()

        # Histórico simples
        st.markdown("#### Últimos 14 dias (soma/dia)")
        if not dfa.empty:
            series = (dfa.groupby("date")["amount_ml"].sum()).reset_index()
            series = series.sort_values("date")
            ult14 = series[series["date"] >= (hoje - timedelta(days=14))]
            if ult14.empty: ult14 = series
            chart_df = ult14.set_index("date")[["amount_ml"]]
            st.line_chart(chart_df, height=220)

        # Edição dos logs de hoje
        st.markdown("#### Entradas de hoje")
        if dfa.empty or dfa[dfa["date"] == hoje].empty:
            st.caption("Sem entradas hoje.")
        else:
            today_logs = dfa[dfa["date"] == hoje].sort_index()
            for _, r in today_logs.iterrows():
                lid = int(r["id"])
                colz1, colz2, colz3 = st.columns([1,1,1])
                with colz1:
                    nv = st.number_input("ml", min_value=0, value=int(r["amount_ml"]), step=50, key=f"aw_{lid}")
                with colz2:
                    if st.button("Salvar", key=f"asv_{lid}"):
                        atualizar_agua(lid, {"amount_ml": int(nv)})
                        st.session_state.agua_logs = buscar_agua_logs(); st.toast("Atualizado"); st.rerun()
                with colz3:
                    st.markdown('<div class="btn-danger">', unsafe_allow_html=True)
                    if st.button("Excluir", key=f"adel_{lid}"):
                        confirmar_exclusao(f"dlg_a_{lid}", "Confirmar exclusão", lambda: deletar_agua(lid))
                    st.markdown('</div>', unsafe_allow_html=True)

    # =======================
    # 🏋️ Treinos
    # =======================
    with aba_treinos:
        st.markdown("### Registrar série rápida")
        with st.form("form_w_quick", clear_on_submit=True):
            colw1, colw2, colw3, colw4 = st.columns([2,1,1,1])
            w_dt = colw1.date_input("Data", value=date.today(), key="w_dt")
            w_ex = colw1.text_input("Exercício", placeholder="Ex.: Supino reto", key="w_ex")
            w_reps = colw2.number_input("Reps", min_value=1, step=1, value=8, key="w_reps")
            w_kg = colw3.number_input("Carga (kg)", min_value=0.0, step=0.5, value=0.0, key="w_kg")
            w_rpe = colw4.number_input("RPE", min_value=0.0, max_value=10.0, step=0.5, value=0.0, key="w_rpe")
            w_nt = st.text_input("Notas (opcional)", value="", key="w_nt")
            if st.form_submit_button("Salvar"):
                inserir_workout_log({
                    "date": w_dt.isoformat(),
                    "exercise": w_ex.strip(),
                    "reps": int(w_reps),
                    "weight_kg": float(w_kg),
                    "rpe": float(w_rpe) if w_rpe > 0 else None,
                    "notes": w_nt.strip()
                })
                st.session_state.w_logs = buscar_workout_logs()
                st.success("Série registrada!"); st.rerun()

        dfw = pd.DataFrame(st.session_state.w_logs)
        if dfw.empty:
            st.info("Nenhum treino registrado ainda.")
        else:
            dfw["date"] = dfw["date"].apply(_to_date)
            dfw = dfw.dropna(subset=["date"]).sort_values(["date","exercise"])
            dfw["vol"] = dfw["reps"].apply(_ensure_int) * dfw["weight_kg"].apply(_ensure_float)

            # Sumário últimos 7 dias
            hoje = date.today()
            dfw7 = dfw[dfw["date"] >= (hoje - timedelta(days=7))]
            vol7 = float(dfw7["vol"].sum()) if not dfw7.empty else 0.0
            dias7 = dfw7["date"].nunique() if not dfw7.empty else 0
            c1, c2 = st.columns(2)
            c1.metric("Volume (7d)", _formata_val(vol7, " kg"))
            c2.metric("Dias treinados (7d)", f"{dias7}")

            st.markdown("#### Últimos registros")
            for _, r in dfw.sort_values("date", ascending=False).head(25).iterrows():
                lid = int(r["id"])
                dt_txt = r["date"].strftime("%d/%m/%Y")
                desc = f"**{r['exercise']}** — {int(r['reps'])} reps × {r['weight_kg']:.1f} kg"
                if r.get("rpe") not in (None, ""):
                    desc += f" • RPE {float(r['rpe']):.1f}"
                if r.get("notes"):
                    desc += f" • {r['notes']}"
                st.write(f"🏷️ {dt_txt} — {desc}")

                cwx1, cwx2, cwx3 = st.columns([2,1,1])
                with cwx1:
                    ne = st.text_input("Exercício", value=r["exercise"], key=f"we_{lid}")
                    nr = st.number_input("Reps", min_value=1, value=int(r["reps"]), step=1, key=f"wr_{lid}")
                    nk = st.number_input("Carga (kg)", min_value=0.0, value=float(r["weight_kg"]), step=0.5, key=f"wk_{lid}")
                with cwx2:
                    n_rpe = st.number_input("RPE", min_value=0.0, max_value=10.0, value=float(r["rpe"]) if r.get("rpe") not in (None,"") else 0.0, step=0.5, key=f"wp_{lid}")
                    if st.button("Salvar", key=f"wsv_{lid}"):
                        atualizar_workout_log(lid, {
                            "exercise": ne.strip(),
                            "reps": int(nr),
                            "weight_kg": float(nk),
                            "rpe": float(n_rpe) if n_rpe > 0 else None
                        })
                        st.session_state.w_logs = buscar_workout_logs(); st.toast("Atualizado"); st.rerun()
                with cwx3:
                    st.markdown('<div class="btn-danger">', unsafe_allow_html=True)
                    if st.button("Excluir", key=f"wdel_{lid}"):
                        confirmar_exclusao(f"dlg_w_{lid}", "Confirmar exclusão", lambda: deletar_workout_log(lid))
                    st.markdown('</div>', unsafe_allow_html=True)
