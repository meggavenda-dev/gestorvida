# views/saude_view.py
# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
from datetime import date, timedelta, datetime

from github_db import (
    # Config antiga (meta água override)
    buscar_saude_config, upsert_saude_config,

    # Dados já existentes
    buscar_peso_logs, inserir_peso, atualizar_peso, deletar_peso,
    buscar_agua_logs, inserir_agua, atualizar_agua, deletar_agua,
    buscar_workout_logs,

    # NOVO: painel
    buscar_saude_profile, upsert_saude_profile,
    buscar_meals, inserir_meal, atualizar_meal, deletar_meal,
    buscar_habit_checks, upsert_habit_check,
    buscar_activity_logs, inserir_activity_log, deletar_activity_log,
)

from ui_helpers import confirmar_exclusao

MEAL_LABEL = {"cafe": "Café", "almoco": "Almoço", "jantar": "Jantar", "lanche": "Lanche"}
MEAL_ORDER = ["cafe", "almoco", "jantar", "lanche"]

QUALITY_LABEL = {"leve": "Leve", "equilibrada": "Equilibrada", "pesada": "Pesada"}
QUALITY_ORDER = ["leve", "equilibrada", "pesada"]


# ----------------------------
# Utils
# ----------------------------
def _to_date(x):
    try:
        return pd.to_datetime(x, errors="coerce").date()
    except Exception:
        return None

def _ensure_int(x, default=0):
    try:
        return int(x)
    except Exception:
        return default

def _ensure_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default

def _clamp(n, a, b):
    return max(a, min(b, n))

def _round_to(n, step=50):
    try:
        n = int(round(float(n) / step) * step)
        return n
    except Exception:
        return int(n) if n is not None else 0

def _semana_range(ref: date, dias=7):
    fim = ref
    ini = ref - timedelta(days=dias - 1)
    return ini, fim

def _now_hour():
    return datetime.now().hour

def _quiet_hours():
    # Silencioso à noite: 22:00–07:00
    h = _now_hour()
    return (h >= 22) or (h < 7)


# ----------------------------
# Cálculos centrais do Painel
# ----------------------------
def _get_last_weight_kg(peso_logs):
    df = pd.DataFrame(peso_logs)
    if df.empty:
        return None
    df["date"] = df["date"].apply(_to_date)
    df = df.dropna(subset=["date"]).sort_values("date")
    if df.empty:
        return None
    return _ensure_float(df.iloc[-1].get("weight_kg"), None)

def _last_weight_and_delta_7d(peso_logs, ref: date):
    df = pd.DataFrame(peso_logs)
    if df.empty:
        return None, None

    df["date"] = df["date"].apply(_to_date)
    df = df.dropna(subset=["date"]).sort_values("date")
    if df.empty or "weight_kg" not in df.columns:
        return None, None

    last_w = _ensure_float(df.iloc[-1]["weight_kg"], None)
    if last_w is None:
        return None, None

    ini7 = ref - timedelta(days=6)
    df7 = df[df["date"] >= ini7].copy()
    if len(df7) >= 2:
        first_w = _ensure_float(df7.iloc[0]["weight_kg"], None)
        if first_w is not None:
            return last_w, (last_w - first_w)

    return last_w, None

def _auto_water_goal_ml(cfg: dict, last_weight_kg: float | None):
    """
    Meta automática: peso*35ml (com limites), mas permite override via config.
    Mantém compatibilidade com water_goal_ml (legado).
    """
    if isinstance(cfg, dict):
        # legado
        if cfg.get("water_goal_ml") not in (None, ""):
            try:
                return int(cfg.get("water_goal_ml"))
            except Exception:
                pass
        # pronto para formato futuro (não obrigatório agora)
        w = cfg.get("water", {}) if isinstance(cfg.get("water", {}), dict) else {}
        if w.get("goal_ml") not in (None, ""):
            try:
                return int(w.get("goal_ml"))
            except Exception:
                pass

    if last_weight_kg is not None and last_weight_kg > 0:
        goal = last_weight_kg * 35
        goal = _clamp(goal, 1500, 4500)
        return _round_to(goal, 50)

    return 2000

def _water_today_ml(agua_logs, hoje: date):
    df = pd.DataFrame(agua_logs)
    if df.empty:
        return 0.0
    df["date"] = df["date"].apply(_to_date)
    df = df.dropna(subset=["date"])
    return float(df[df["date"] == hoje]["amount_ml"].sum())

def _activity_today_minutes(activity_logs, hoje: date):
    df = pd.DataFrame(activity_logs)
    if df.empty:
        return 0
    df["date"] = df["date"].apply(_to_date)
    df = df.dropna(subset=["date"])
    if "minutes" not in df.columns:
        return 0
    return int(df[df["date"] == hoje]["minutes"].apply(_ensure_int).sum())

def _workout_today_exists(w_logs, hoje: date):
    df = pd.DataFrame(w_logs)
    if df.empty:
        return False
    df["date"] = df["date"].apply(_to_date)
    df = df.dropna(subset=["date"])
    return bool((df["date"] == hoje).any())

def _get_today_habit(habit_checks, hoje: date):
    date_str = hoje.isoformat()
    for r in habit_checks or []:
        if isinstance(r, dict) and str(r.get("date")) == date_str:
            return r
    return None

def _upsert_today_habit(hoje: date, patch: dict):
    upsert_habit_check(hoje.isoformat(), patch)

def _get_meals_today(meals, hoje: date):
    df = pd.DataFrame(meals)
    if df.empty:
        return pd.DataFrame(columns=["id", "date", "meal", "quality", "notes"])
    df["date_dt"] = df["date"].apply(_to_date)
    df = df[df["date_dt"] == hoje].copy()
    return df

def _upsert_meal_today(meals_df_today, hoje: date, meal: str, quality: str) -> bool:
    """
    Retorna True se mudou algo (para decidir rerun).
    Evita flicker quando o usuário clica na mesma opção.
    """
    row = meals_df_today[meals_df_today["meal"] == meal]
    if not row.empty:
        current = str(row.iloc[0].get("quality") or "")
        if current == quality:
            return False
        mid = int(row.iloc[0]["id"])
        atualizar_meal(mid, {"quality": quality})
        return True

    inserir_meal({"date": hoje.isoformat(), "meal": meal, "quality": quality, "notes": ""})
    return True

def _weekly_consistency(habit_checks, ref: date):
    ini, fim = _semana_range(ref, 7)
    df = pd.DataFrame(habit_checks)
    if df.empty:
        return {"days_active": 0, "move_days": 0, "sleep_days": 0}

    df["date_dt"] = df["date"].apply(_to_date)
    df = df.dropna(subset=["date_dt"])
    df = df[(df["date_dt"] >= ini) & (df["date_dt"] <= fim)].copy()
    if df.empty:
        return {"days_active": 0, "move_days": 0, "sleep_days": 0}

    move_days = int(df["move_done"].fillna(False).astype(bool).sum()) if "move_done" in df.columns else 0
    sleep_days = int(df["sleep_done"].fillna(False).astype(bool).sum()) if "sleep_done" in df.columns else 0

    # dia ativo = move_done OU sleep_done (água não entra, pois é inferida por volume)
    df["active_day"] = False
    for col in ["move_done", "sleep_done"]:
        if col in df.columns:
            df["active_day"] = df["active_day"] | df[col].fillna(False).astype(bool)

    days_active = int(df["active_day"].sum())
    return {"days_active": days_active, "move_days": move_days, "sleep_days": sleep_days}


# ----------------------------
# Ações rápidas
# ----------------------------
def _drink(ml: int):
    inserir_agua({"date": date.today().isoformat(), "amount_ml": int(ml)})
    st.session_state.agua_logs = buscar_agua_logs()
    st.toast(f"+{ml} ml")
    st.rerun()

def _quick_activity(label: str, minutes: int, intensity="leve"):
    inserir_activity_log({
        "date": date.today().isoformat(),
        "activity": label,
        "minutes": int(minutes),
        "intensity": intensity
    })
    st.session_state.activity_logs = buscar_activity_logs()

    # marca movimento como feito
    _upsert_today_habit(date.today(), {"move_done": True})
    st.session_state.habits = buscar_habit_checks()

    st.toast("Corpo ativado.")
    st.rerun()


# ---------------------------------------------
#  RENDER
# ---------------------------------------------
def render_saude():
    st.markdown("""
      <div class="header-container">
        <div class="main-title">💪 Saúde</div>
        <div class="slogan">Painel de comando do corpo — simples, rápido e consistente</div>
      </div>
    """, unsafe_allow_html=True)

    # Estado inicial
    if "saude_cfg" not in st.session_state:
        st.session_state.saude_cfg = buscar_saude_config()
    if "profile" not in st.session_state:
        st.session_state.profile = buscar_saude_profile()

    if "peso_logs" not in st.session_state:
        st.session_state.peso_logs = buscar_peso_logs()
    if "agua_logs" not in st.session_state:
        st.session_state.agua_logs = buscar_agua_logs()
    if "w_logs" not in st.session_state:
        st.session_state.w_logs = buscar_workout_logs()

    if "meals" not in st.session_state:
        st.session_state.meals = buscar_meals()
    if "habits" not in st.session_state:
        st.session_state.habits = buscar_habit_checks()
    if "activity_logs" not in st.session_state:
        st.session_state.activity_logs = buscar_activity_logs()

    hoje = date.today()

    # Meta água automática + editável
    last_w = _get_last_weight_kg(st.session_state.peso_logs)
    agua_goal = _auto_water_goal_ml(st.session_state.saude_cfg, last_w)
    agua_hoje = _water_today_ml(st.session_state.agua_logs, hoje)

    # Movimento
    act_min_hoje = _activity_today_minutes(st.session_state.activity_logs, hoje)
    workout_hoje = _workout_today_exists(st.session_state.w_logs, hoje)
    move_infer = (act_min_hoje > 0) or workout_hoje

    # Hábito do dia (apenas move/sleep são manuais; água é inferida)
    habit_today = _get_today_habit(st.session_state.habits, hoje)
    move_done = bool(habit_today.get("move_done")) if habit_today else False
    sleep_done = bool(habit_today.get("sleep_done")) if habit_today else False

    # se já moveu por logs, reforça hábito
    if move_infer and not move_done:
        _upsert_today_habit(hoje, {"move_done": True})
        st.session_state.habits = buscar_habit_checks()
        habit_today = _get_today_habit(st.session_state.habits, hoje)
        move_done = True

    tab_painel, tab_hist = st.tabs(["🧠 Painel", "📈 Histórico"])

    # =======================
    # 🧠 PAINEL
    # =======================
    with tab_painel:
        # Perfil (simples) em expander discreto
        with st.expander("👤 Perfil (simples)", expanded=False):
            p = st.session_state.profile or {}
            age = st.number_input("Idade", min_value=0, max_value=120, value=_ensure_int(p.get("age", 0)), step=1)
            sex = st.selectbox("Sexo", ["", "M", "F"], index=["", "M", "F"].index(p.get("sex", "")) if p.get("sex", "") in ["", "M", "F"] else 0)
            height = st.number_input("Altura (cm)", min_value=0, max_value=250, value=_ensure_int(p.get("height_cm", 0)), step=1)
            goal = st.selectbox("Objetivo principal", ["mais energia", "emagrecer", "manter saúde", "ganhar condicionamento"], index=0)
            if st.button("Salvar perfil", key="save_profile"):
                upsert_saude_profile({"age": int(age), "sex": sex, "height_cm": int(height), "goal": goal})
                st.session_state.profile = buscar_saude_profile()
                st.toast("Perfil atualizado.")

        # 2 colunas (no mobile vira 1 por CSS)
        c1, c2 = st.columns(2)

        # 💧 ÁGUA
        with c1:
            prog = min(agua_hoje / max(1, agua_goal), 1.0)
            st.markdown(
                f"<div class='card'><b>💧 Água hoje</b><br>"
                f"<span style='opacity:.85'>{int(agua_hoje)} / {agua_goal} ml</span></div>",
                unsafe_allow_html=True
            )
            st.progress(prog)

            # Botão principal
            if st.button("Beber 250 ml", key="drink_250"):
                _drink(250)

            # secundários discretos
            bA, bB, bC = st.columns(3)
            if bA.button("+100", key="drink_100"): _drink(100)
            if bB.button("+500", key="drink_500"): _drink(500)
            if bC.button("Meta", key="water_goal_btn"):
                st.session_state.show_goal = True

            # Override de meta
            if st.session_state.get("show_goal"):
                with st.expander("🎯 Ajustar meta (override)", expanded=True):
                    meta = st.number_input("Meta diária (ml)", min_value=0, step=100, value=int(agua_goal))
                    if st.button("Salvar meta", key="save_water_goal"):
                        # mantém compatibilidade (legado)
                        upsert_saude_config({"water_goal_ml": int(meta)})
                        st.session_state.saude_cfg = buscar_saude_config()
                        st.session_state.show_goal = False
                        st.toast("Meta atualizada.")
                        st.rerun()

        # 🏃 MOVIMENTO
        with c2:
            st.markdown(
                f"<div class='card'><b>🏃 Movimento hoje</b><br>"
                f"<span style='opacity:.85'>Ativo: <b>{'Sim' if move_infer else 'Não'}</b> • {act_min_hoje} min</span></div>",
                unsafe_allow_html=True
            )

            if st.button("Treino rápido agora", key="quick_now"):
                st.session_state.show_quick = True

            if st.session_state.get("show_quick"):
                with st.expander("Escolha rápida (1 toque)", expanded=True):
                    q1, q2, q3 = st.columns(3)
                    if q1.button("Alongamento 5m", key="act_stretch_5"):
                        _quick_activity("alongamento 5min", 5, "leve")
                    if q2.button("Mobilidade 10m", key="act_mob_10"):
                        _quick_activity("mobilidade 10min", 10, "leve")
                    if q3.button("Corpo 15m", key="act_body_15"):
                        _quick_activity("exercício rápido 15min", 15, "moderada")

        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

        # ⚖️ PESO (Opção A — compacto no painel)
        last_w2, delta_7 = _last_weight_and_delta_7d(st.session_state.peso_logs, hoje)

        st.markdown(
            "<div class='card'><b>⚖️ Peso</b><br>"
            "<span style='opacity:.85'>Último registro e variação 7 dias</span></div>",
            unsafe_allow_html=True
        )

        pw1, pw2 = st.columns([2, 1])
        with pw1:
            if last_w2 is None:
                st.metric("Último", "—")
            else:
                delta_txt = None if delta_7 is None else f"{delta_7:+.1f} kg (7d)"
                st.metric("Último", f"{last_w2:.1f} kg", delta=delta_txt)

        with pw2:
            if st.button("Registrar", key="peso_quick_open"):
                st.session_state.show_peso_quick = True

        if st.session_state.get("show_peso_quick"):
            with st.expander("Registrar peso (rápido)", expanded=True):
                pdt = st.date_input("Data", value=hoje, key="peso_quick_date")
                pw = st.number_input(
                    "Peso (kg)", min_value=0.0, step=0.1,
                    value=float(last_w2) if last_w2 else 0.0,
                    key="peso_quick_value"
                )
                adv = st.checkbox("Detalhes (opcional)", value=False, key="peso_adv")
                bf = wc = None
                if adv:
                    bf = st.number_input("% Gordura", min_value=0.0, step=0.1, value=0.0, key="peso_bf")
                    wc = st.number_input("Cintura (cm)", min_value=0.0, step=0.5, value=0.0, key="peso_wc")

                if st.button("Salvar peso", key="peso_quick_save"):
                    inserir_peso({
                        "date": pdt.isoformat(),
                        "weight_kg": float(pw),
                        "body_fat_pct": bf if (bf is not None and bf > 0) else None,
                        "waist_cm": wc if (wc is not None and wc > 0) else None,
                    })
                    st.session_state.peso_logs = buscar_peso_logs()
                    st.session_state.show_peso_quick = False
                    st.toast("Peso registrado.")
                    st.rerun()

        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

        # 🍽 ALIMENTAÇÃO (1 toque)
        st.markdown(
            "<div class='card'><b>🍽 Alimentação hoje</b><br>"
            "<span style='opacity:.85'>Registro rápido — sem calorias</span></div>",
            unsafe_allow_html=True
        )
        meals_today = _get_meals_today(st.session_state.meals, hoje)

        for meal in MEAL_ORDER:
            row = meals_today[meals_today["meal"] == meal]
            current = (row.iloc[0]["quality"] if not row.empty else "")
            st.caption(f"**{MEAL_LABEL[meal]}** — atual: {QUALITY_LABEL.get(str(current), '—')}")

            q1, q2, q3 = st.columns(3)
            if q1.button("Leve", key=f"meal_{meal}_leve"):
                changed = _upsert_meal_today(meals_today, hoje, meal, "leve")
                if changed:
                    st.session_state.meals = buscar_meals()
                    st.toast("Registrado.")
                    st.rerun()
            if q2.button("Equilibrada", key=f"meal_{meal}_equil"):
                changed = _upsert_meal_today(meals_today, hoje, meal, "equilibrada")
                if changed:
                    st.session_state.meals = buscar_meals()
                    st.toast("Registrado.")
                    st.rerun()
            if q3.button("Pesada", key=f"meal_{meal}_pesada"):
                changed = _upsert_meal_today(meals_today, hoje, meal, "pesada")
                if changed:
                    st.session_state.meals = buscar_meals()
                    st.toast("Registrado.")
                    st.rerun()

            st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

        # 🛌 Sono (micro-atalho após 20h) — Opção A
        if _now_hour() >= 20 and not sleep_done:
            st.info("🛌 Dormiu bem hoje? Um toque fecha o dia.")
            if st.button("Marcar sono como OK", key="sleep_quick"):
                _upsert_today_habit(hoje, {"sleep_done": True})
                st.session_state.habits = buscar_habit_checks()
                st.toast("Sono registrado.")
                st.rerun()

        # ✅ Hábitos do dia (motor) — água não é manual
        st.markdown(
            "<div class='card'><b>✅ Hábitos do dia</b><br>"
            "<span style='opacity:.85'>1 toque. Sem julgamento.</span></div>",
            unsafe_allow_html=True
        )

        hc1, hc2, hc3 = st.columns(3)
        # Água: fonte única da verdade = volume ingerido (checkbox só visual)
        hc1.checkbox("Água", value=(agua_hoje >= agua_goal), disabled=True, key="chk_water")
        move_chk = hc2.checkbox("Mover", value=move_done or move_infer, key="chk_move")
        sleep_chk = hc3.checkbox("Dormir bem", value=sleep_done, key="chk_sleep")

        if st.button("Salvar hábitos", key="save_habits"):
            _upsert_today_habit(hoje, {"move_done": bool(move_chk), "sleep_done": bool(sleep_chk)})
            st.session_state.habits = buscar_habit_checks()
            st.toast("Salvo.")

        # Consistência semanal (seca)
        cons = _weekly_consistency(st.session_state.habits, hoje)
        st.caption(f"📌 Semana: dias ativos **{cons['days_active']}/7** • Movimento **{cons['move_days']}** • Sono **{cons['sleep_days']}**")

        # Micro-insight discreto (sem coach) — e silencioso à noite
        if not _quiet_hours():
            if agua_hoje < (0.5 * agua_goal):
                st.caption("💡 Um copo agora (250 ml) já muda o dia.")
            elif not move_infer:
                st.caption("💡 10 minutos de mobilidade ativam o corpo sem esforço.")
            else:
                st.caption("💡 Está andando. Só continue.")

    # =======================
    # 📈 HISTÓRICO
    # =======================
    with tab_hist:
        st.markdown("### Histórico (seco e útil)")

        hoje = date.today()
        ini14 = hoje - timedelta(days=13)

        # Água últimos 14 dias (soma/dia) + linha de meta
        dfa = pd.DataFrame(st.session_state.agua_logs)
        if not dfa.empty:
            dfa["date"] = dfa["date"].apply(_to_date)
            dfa = dfa.dropna(subset=["date"])
            agua_day = dfa.groupby("date")["amount_ml"].sum().reset_index()
            agua_day = agua_day[(agua_day["date"] >= ini14) & (agua_day["date"] <= hoje)]
            if not agua_day.empty:
                st.markdown("#### 💧 Água (14 dias)")
                agua_day["goal_ml"] = int(agua_goal)
                chart_df = agua_day.set_index("date")[["amount_ml", "goal_ml"]]
                st.line_chart(chart_df, height=220)
        else:
            st.caption("Sem registros de água.")

        # Atividades últimos 14 dias
        dact = pd.DataFrame(st.session_state.activity_logs)
        if not dact.empty:
            dact["date"] = dact["date"].apply(_to_date)
            dact = dact.dropna(subset=["date"])
            act_day = dact.groupby("date")["minutes"].sum().reset_index()
            act_day = act_day[(act_day["date"] >= ini14) & (act_day["date"] <= hoje)]
            if not act_day.empty:
                st.markdown("#### 🏃 Movimento (min/dia — 14 dias)")
                st.line_chart(act_day.set_index("date")[["minutes"]], height=220)

            with st.expander("Ver e excluir registros de atividade", expanded=False):
                for _, r in dact.sort_values("date", ascending=False).head(20).iterrows():
                    lid = int(r.get("id"))
                    dt_txt = r["date"].strftime("%d/%m/%Y") if pd.notnull(r["date"]) else "-"
                    st.write(f"• {dt_txt} — **{r.get('activity','')}** ({int(r.get('minutes',0))} min)")
                    st.markdown('<div class="btn-danger">', unsafe_allow_html=True)
                    if st.button("Excluir", key=f"act_del_{lid}"):
                        confirmar_exclusao(f"dlg_act_{lid}", "Confirmar exclusão", lambda lid_=lid: deletar_activity_log(lid_))
                        st.session_state.activity_logs = buscar_activity_logs()
                        st.rerun()
                    st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.caption("Sem registros de movimento.")

        # Alimentação (padrão diário)
        dfm = pd.DataFrame(st.session_state.meals)
        if not dfm.empty:
            dfm["date"] = dfm["date"].apply(_to_date)
            dfm = dfm.dropna(subset=["date"])
            dfm14 = dfm[(dfm["date"] >= ini14) & (dfm["date"] <= hoje)].copy()
            if not dfm14.empty:
                st.markdown("#### 🍽 Alimentação (padrão — 14 dias)")
                pivot = dfm14.pivot_table(index="date", columns="meal", values="quality", aggfunc="last")
                st.dataframe(pivot, use_container_width=True)

        # Peso 30 dias (gráfico) + últimas medições
        dfp = pd.DataFrame(st.session_state.peso_logs)
        if not dfp.empty:
            dfp["date"] = pd.to_datetime(dfp["date"], errors="coerce")
            dfp = dfp.dropna(subset=["date"]).sort_values("date")
            ult30 = dfp[dfp["date"] >= (pd.Timestamp(hoje) - pd.Timedelta(days=30))]
            if ult30.empty:
                ult30 = dfp
            st.markdown("#### ⚖️ Peso (30 dias)")
            st.line_chart(ult30.set_index("date")[["weight_kg"]], height=220)

            with st.expander("Últimas medições de peso", expanded=False):
                last7 = dfp.sort_values("date", ascending=False).head(7)
                for _, r in last7.iterrows():
                    dt_txt = r["date"].strftime("%d/%m/%Y")
                    st.write(f"• {dt_txt} — **{float(r['weight_kg']):.1f} kg**")
        else:
            st.caption("Sem medições de peso.")
