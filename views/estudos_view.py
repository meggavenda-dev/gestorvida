# views/estudos_view.py
# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta

from github_db import (
    buscar_estudos_subjects, inserir_estudos_subject, atualizar_estudos_subject, deletar_estudos_subject,
    buscar_estudos_topics, inserir_estudos_topic, atualizar_estudos_topic, deletar_estudos_topic,
    buscar_estudos_logs, inserir_estudos_log
)


from ui_helpers import confirmar_exclusao

STATUS_LABEL = {"todo": "Não estudado", "doing": "Estudando", "done": "Estudado"}
STATUS_ORDER = ["todo", "doing", "done"]
WEEK_LABELS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]

# Ajuste simples para "data local" a partir de UTC (Brasília ~ UTC-3)
LOCAL_UTC_OFFSET_HOURS = -3

def _parse_iso_dt(s: str):
    try:
        if not s:
            return None
        # lida com "Z"
        if isinstance(s, str) and s.endswith("Z"):
            s = s[:-1]
        return datetime.fromisoformat(s)
    except Exception:
        return None

def _to_local_date(dt: datetime):
    if dt is None:
        return None
    return (dt + timedelta(hours=LOCAL_UTC_OFFSET_HOURS)).date()

def _to_date(x):
    try:
        return pd.to_datetime(x, errors="coerce").date()
    except Exception:
        return None

def _ensure_list_weekdays(x):
    if isinstance(x, list):
        out = []
        for v in x:
            try:
                iv = int(v)
                if 0 <= iv <= 6:
                    out.append(iv)
            except Exception:
                pass
        return out
    return []

def _get_state():
    if "estudos_screen" not in st.session_state:
        st.session_state.estudos_screen = "today"  # today | subjects | topics | study
    if "estudos_subject_id" not in st.session_state:
        st.session_state.estudos_subject_id = None
    if "estudos_topic_id" not in st.session_state:
        st.session_state.estudos_topic_id = None
    if "study_timer_start" not in st.session_state:
        st.session_state.study_timer_start = None  # datetime UTC
    if "study_timer_topic" not in st.session_state:
        st.session_state.study_timer_topic = None

def recarregar():
    st.session_state.est_sub = buscar_estudos_subjects()
    st.session_state.est_topics = buscar_estudos_topics()
    st.session_state.est_logs = buscar_estudos_logs()

def _df_subjects():
    df = pd.DataFrame(st.session_state.est_sub)
    if df.empty:
        df = pd.DataFrame(columns=["id", "name", "order"])
    for c in ["id", "name", "order"]:
        if c not in df.columns:
            df[c] = None
    df["id"] = pd.to_numeric(df["id"], errors="coerce").astype("Int64")
    df["order"] = pd.to_numeric(df["order"], errors="coerce").fillna(9999).astype(int)
    df["name"] = df["name"].fillna("").astype(str)
    return df.sort_values(["order", "name"], na_position="last")

def _df_topics():
    df = pd.DataFrame(st.session_state.est_topics)
    if df.empty:
        df = pd.DataFrame(columns=[
            "id","subject_id","title","order","status","planned_date","planned_weekdays","notes",
            "review","active","last_studied_at"
        ])
    for c in ["id","subject_id","title","order","status","planned_date","planned_weekdays","notes","review","active","last_studied_at"]:
        if c not in df.columns:
            df[c] = None

    df["id"] = pd.to_numeric(df["id"], errors="coerce").astype("Int64")
    df["subject_id"] = pd.to_numeric(df["subject_id"], errors="coerce").astype("Int64")
    df["order"] = pd.to_numeric(df["order"], errors="coerce").fillna(9999).astype(int)
    df["title"] = df["title"].fillna("").astype(str)
    df["status"] = df["status"].fillna("todo").astype(str)
    df["planned_date_dt"] = df["planned_date"].apply(_to_date)
    df["planned_weekdays"] = df["planned_weekdays"].apply(_ensure_list_weekdays)
    df["notes"] = df["notes"].fillna("").astype(str)
    df["review"] = df["review"].fillna(False).astype(bool)
    df["active"] = df["active"].fillna(True).astype(bool)
    return df

def _df_logs():
    df = pd.DataFrame(st.session_state.est_logs)
    if df.empty:
        df = pd.DataFrame(columns=["id","topic_id","start_at","end_at","duration_min","result"])
    for c in ["id","topic_id","start_at","end_at","duration_min","result"]:
        if c not in df.columns:
            df[c] = None
    df["topic_id"] = pd.to_numeric(df["topic_id"], errors="coerce").astype("Int64")
    df["duration_min"] = pd.to_numeric(df["duration_min"], errors="coerce").fillna(0).astype(int)
    df["start_dt"] = df["start_at"].apply(_parse_iso_dt)
    df["start_date_local"] = df["start_dt"].apply(_to_local_date)
    return df

def _progress_subject(df_topics_sub):
    if df_topics_sub.empty:
        return 0.0, 0, 0
    total = len(df_topics_sub)
    done = int((df_topics_sub["status"] == "done").sum())
    return done / max(1, total), done, total

def _week_minutes(df_logs):
    # semana (7 dias corridos incluindo hoje)
    hoje = date.today()
    ini = hoje - timedelta(days=6)
    df = df_logs.dropna(subset=["start_date_local"]).copy()
    dfw = df[(df["start_date_local"] >= ini) & (df["start_date_local"] <= hoje)]
    return int(dfw["duration_min"].sum())

def _streak_days(df_logs, min_minutes_day=10):
    """
    Streak silencioso: conta dias consecutivos (até hoje) onde soma >= min_minutes_day.
    Se falhar, zera, mas histórico permanece.
    """
    df = df_logs.dropna(subset=["start_date_local"]).copy()
    if df.empty:
        return 0

    g = df.groupby("start_date_local")["duration_min"].sum()
    if g.empty:
        return 0

    hoje = date.today()
    streak = 0
    d = hoje
    while True:
        if int(g.get(d, 0)) >= min_minutes_day:
            streak += 1
            d = d - timedelta(days=1)
        else:
            break
    return streak

def _pick_today_topics(df_s, df_t, df_logs, limit=3):
    """
    Sugestão 1–3 tópicos:
    prioridade: atrasados > hoje > dia da semana > pendentes sem plano
    desempate: menos estudado recentemente (last_studied_at / logs), depois order
    """
    hoje = date.today()
    wday = hoje.weekday()

    # apenas ativos e não concluídos
    base = df_t[(df_t["active"] == True) & (df_t["status"] != "done")].copy()
    if base.empty:
        return base

    # last studied (preferir os menos recentes)
    # 1) usa last_studied_at do tópico se tiver
    base["last_dt"] = base["last_studied_at"].apply(_parse_iso_dt)

    # 2) complementa com logs (última sessão por tópico)
    if not df_logs.empty:
        last_by_topic = df_logs.dropna(subset=["topic_id","start_dt"]).groupby("topic_id")["start_dt"].max()
        def _merge_last(row):
            try:
                tid = int(row["id"])
                from_log = last_by_topic.get(tid, None)
            except Exception:
                from_log = None
            # pega o mais recente entre os dois (para saber "quão recente foi")
            # mas para priorizar menos estudado, vamos ordenar por "mais antigo"
            candidates = [x for x in [row["last_dt"], from_log] if x is not None]
            return max(candidates) if candidates else None
        base["last_dt"] = base.apply(_merge_last, axis=1)

    # flags de planejamento
    base["is_overdue"] = base["planned_date_dt"].notna() & (base["planned_date_dt"] < hoje)
    base["is_today"] = base["planned_date_dt"].notna() & (base["planned_date_dt"] == hoje)
    base["is_weekday"] = base["planned_weekdays"].apply(lambda lst: isinstance(lst, list) and (wday in lst))
    base["has_plan"] = base["planned_date_dt"].notna() | base["planned_weekdays"].apply(lambda lst: isinstance(lst, list) and len(lst) > 0)

    # score: menor é melhor
    # 0 atrasado, 1 hoje, 2 dia semana, 3 sem plano (só entra se faltar)
    def _bucket(r):
        if r["is_overdue"]:
            return 0
        if r["is_today"]:
            return 1
        if r["is_weekday"]:
            return 2
        return 3

    base["bucket"] = base.apply(_bucket, axis=1)

    # primeiro seleciona de buckets 0,1,2
    preferred = base[base["bucket"].isin([0,1,2])].copy()
    rest = base[base["bucket"] == 3].copy()

    # ordenação: bucket, review primeiro (se marcado), last_dt mais antigo primeiro, order
    def _sort(df):
        df["last_sort"] = df["last_dt"].apply(lambda x: x.timestamp() if x else 0)
        # como queremos "menos recente", last_sort ASC (0 = nunca estudado) fica antes
        return df.sort_values(
            by=["bucket", "review", "last_sort", "order", "title"],
            ascending=[True, False, True, True, True],
            na_position="first"
        )

    out = _sort(preferred).head(limit)
    if len(out) < limit:
        add = _sort(rest).head(limit - len(out))
        out = pd.concat([out, add], ignore_index=True)

    # enrich subject name
    sub_map = {int(r["id"]): (r["name"] or "").strip() for _, r in df_s.iterrows() if pd.notnull(r["id"])}
    out["subject_name"] = out["subject_id"].apply(lambda sid: sub_map.get(int(sid), ""))
    return out

def _next_suggested(df_t, subject_id, current_topic_id=None):
    """Próximo sugerido: próximo não concluído por ordem na mesma matéria."""
    df = df_t[(df_t["subject_id"] == subject_id) & (df_t["active"] == True) & (df_t["status"] != "done")].copy()
    if df.empty:
        return None
    df = df.sort_values(["order","title"], na_position="last")
    if current_topic_id is None:
        return df.iloc[0]
    # pega o primeiro com order maior ou diferente
    cur = df_t[df_t["id"] == current_topic_id]
    cur_order = int(cur.iloc[0]["order"]) if not cur.empty and pd.notnull(cur.iloc[0]["order"]) else None
    if cur_order is not None:
        after = df[df["order"] > cur_order]
        if not after.empty:
            return after.iloc[0]
    # fallback: primeiro disponível
    return df.iloc[0]

def render_estudos():
    st.markdown("""
      <div class="header-container">
        <div class="main-title">📚 Estudos</div>
        <div class="slogan">Decide menos. Mostra avanço. Registra consistência.</div>
      </div>
    """, unsafe_allow_html=True)

    _get_state()

    if "est_sub" not in st.session_state: st.session_state.est_sub = buscar_estudos_subjects()
    if "est_topics" not in st.session_state: st.session_state.est_topics = buscar_estudos_topics()
    if "est_logs" not in st.session_state: st.session_state.est_logs = buscar_estudos_logs()

    df_s = _df_subjects()
    df_t = _df_topics()
    df_l = _df_logs()

    # Top nav (3 telas, mas "Hoje" é padrão)
    col1, col2, col3 = st.columns(3)
    if col1.button("✅ Hoje", key="nav_today"):
        st.session_state.estudos_screen = "today"
        st.rerun()
    if col2.button("📌 Matérias", key="nav_subjects"):
        st.session_state.estudos_screen = "subjects"
        st.rerun()
    if col3.button("📝 Estudo", key="nav_study"):
        st.session_state.estudos_screen = "study"
        st.rerun()

    st.divider()

    screen = st.session_state.estudos_screen

    if screen == "today":
        _screen_today(df_s, df_t, df_l)
    elif screen == "subjects":
        _screen_subjects(df_s, df_t)
    elif screen == "topics":
        _screen_topics(df_s, df_t)
    else:
        _screen_study(df_s, df_t, df_l)

def _screen_today(df_s, df_t, df_l):
    st.markdown("### Seu estudo de hoje")

    # Métricas honestas (sem circo)
    week_min = _week_minutes(df_l)
    streak = _streak_days(df_l, min_minutes_day=10)

    total_active = int(len(df_t[(df_t["active"] == True)]))
    done_active = int((df_t[(df_t["active"] == True)]["status"] == "done").sum()) if total_active else 0
    prog = done_active / max(1, total_active)

    c1, c2, c3 = st.columns(3)
    c1.metric("Progresso", f"{done_active}/{total_active}")
    c2.metric("Semana", f"{week_min} min")
    c3.metric("Streak", f"{streak} dia(s)")

    st.progress(prog)

    # Sugestões (1–3)
    sug = _pick_today_topics(df_s, df_t, df_l, limit=3)

    if sug.empty:
        st.info("Hoje está limpo. Se quiser, avance em um tópico pendente pela lista de matérias.")
        return

    for _, r in sug.iterrows():
        tid = int(r["id"])
        title = (r["title"] or "").strip() or f"Tópico {tid}"
        subj = (r.get("subject_name") or "").strip()
        status = r.get("status", "todo")
        planned = r.get("planned_date_dt")
        days = r.get("planned_weekdays", [])
        review = bool(r.get("review", False))

        # etiqueta de contexto (atrasado/hoje/semana)
        hoje = date.today()
        tag = ""
        if planned and planned < hoje:
            tag = "⚠️ Atrasado"
        elif planned and planned == hoje:
            tag = "📅 Hoje"
        elif isinstance(days, list) and (hoje.weekday() in days):
            tag = "🗓 Dia da semana"
        else:
            tag = "📌 Pendente"

        extra = []
        if subj:
            extra.append(f"Matéria: **{subj}**")
        extra.append(tag)
        if review:
            extra.append("🔁 Revisão")

        st.markdown(
            f"<div class='card'><b>{title}</b><br><span style='opacity:.85'>{' • '.join(extra)}</span>"
            f"<br><span class='status-badge {status}'>{STATUS_LABEL.get(status,status)}</span></div>",
            unsafe_allow_html=True
        )

        b1, b2 = st.columns([2,1])
        if b1.button("▶️ Começar", key=f"today_start_{tid}"):
            st.session_state.estudos_topic_id = tid
            st.session_state.estudos_screen = "study"
            st.rerun()

        with b2:
            if st.button("☑️ Estudado", key=f"today_done_{tid}"):
                atualizar_estudos_topic(tid, {"status": "done", "review": False})
                recarregar()
                st.toast("Concluído.")
                st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)

    # Lembrete mínimo (1 por dia, sem coach)
    # Regra simples: se semana < 30 min, sugerir 15 min hoje.
    if week_min < 30:
        st.caption("💡 15 minutos hoje já mantém o ritmo.")
    else:
        st.caption("💡 Um tópico pendente pode virar concluído agora.")

def _screen_subjects(df_s, df_t):
    st.markdown("### Matérias")

    with st.expander("➕ Nova matéria", expanded=False):
        with st.form("form_new_subject_simple", clear_on_submit=True):
            name = st.text_input("Nome da matéria", placeholder="Ex.: Matemática")
            if st.form_submit_button("Salvar"):
                if not name.strip():
                    st.error("Informe o nome.")
                else:
                    inserir_estudos_subject({"name": name.strip(), "order": int(len(df_s) + 1)})
                    recarregar()
                    st.toast("Matéria criada!")
                    st.rerun()

    if df_s.empty:
        st.info("Crie sua primeira matéria.")
        return

    for _, s in df_s.iterrows():
        sid = int(s["id"])
        name = (s["name"] or "").strip() or f"Matéria {sid}"

        df_sub = df_t[(df_t["subject_id"] == sid) & (df_t["active"] == True)].copy()
        prog, done, total = _progress_subject(df_sub)
        pct = int(round(prog * 100))

        st.markdown(
            f"<div class='card'><b>📌 {name}</b><br>"
            f"Progresso: <b>{pct}%</b> • <b>{done}/{total}</b> tópicos</div>",
            unsafe_allow_html=True
        )
        st.progress(prog)

        c1, c2, c3 = st.columns([1.2, 1.2, 1])
        if c1.button("Abrir", key=f"sub_open_{sid}"):
            st.session_state.estudos_subject_id = sid
            st.session_state.estudos_screen = "topics"
            st.rerun()

        with c2:
            with st.expander("Editar"):
                nn = st.text_input("Nome", value=name, key=f"sub_name_{sid}")
                if st.button("Salvar", key=f"sub_save_{sid}"):
                    atualizar_estudos_subject(sid, {"name": nn.strip()})
                    recarregar()
                    st.toast("Atualizado.")
                    st.rerun()

        with c3:
            st.markdown('<div class="btn-danger">', unsafe_allow_html=True)
            if st.button("Excluir", key=f"sub_del_{sid}"):
                confirmar_exclusao(f"dlg_sub_{sid}", "Confirmar exclusão", lambda sid_=sid: deletar_estudos_subject(sid_))
            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

def _move_topic(df_all_topics, topic_id, direction):
    row = df_all_topics[df_all_topics["id"] == topic_id]
    if row.empty:
        return
    sid = int(row.iloc[0]["subject_id"])
    order = int(row.iloc[0]["order"])

    df_sub = df_all_topics[(df_all_topics["subject_id"] == sid) & (df_all_topics["active"] == True)].copy()
    df_sub = df_sub.sort_values(["order", "title"], na_position="last")
    ids = df_sub["id"].tolist()

    try:
        idx = ids.index(topic_id)
    except ValueError:
        return

    new_idx = idx + direction
    if new_idx < 0 or new_idx >= len(ids):
        return

    other_id = int(ids[new_idx])
    other_order = int(df_sub[df_sub["id"] == other_id].iloc[0]["order"])

    atualizar_estudos_topic(int(topic_id), {"order": other_order})
    atualizar_estudos_topic(int(other_id), {"order": order})

def _screen_topics(df_s, df_t):
    sid = st.session_state.estudos_subject_id
    if sid is None:
        st.session_state.estudos_screen = "subjects"
        st.rerun()

    sub = df_s[df_s["id"] == sid]
    sub_name = (sub.iloc[0]["name"] if not sub.empty else "") or "Matéria"

    # Voltar
    if st.button("← Voltar", key="topics_back"):
        st.session_state.estudos_screen = "subjects"
        st.session_state.estudos_subject_id = None
        st.rerun()

    st.markdown(f"### 📌 {sub_name}")

    df_view = df_t[(df_t["subject_id"] == sid) & (df_t["active"] == True)].copy()
    df_view = df_view.sort_values(["order", "title"], na_position="last")

    with st.expander("➕ Novo tópico", expanded=False):
        with st.form(f"form_new_topic_{sid}", clear_on_submit=True):
            title = st.text_input("Tópico/Aula", placeholder="Ex.: Função quadrática")
            planned = st.date_input("Planejar para (opcional)", value=None)
            days = st.multiselect("Dias da semana (opcional)", options=list(range(7)), format_func=lambda i: WEEK_LABELS[i])
            if st.form_submit_button("Adicionar"):
                if not title.strip():
                    st.error("Informe o tópico.")
                else:
                    next_order = int(df_view["order"].max() + 1) if not df_view.empty else 1
                    inserir_estudos_topic({
                        "subject_id": int(sid),
                        "title": title.strip(),
                        "order": next_order,
                        "status": "todo",
                        "planned_date": planned.isoformat() if planned else None,
                        "planned_weekdays": days,
                        "notes": "",
                        "review": False
                    })
                    recarregar()
                    st.toast("Tópico criado!")
                    st.rerun()

    if df_view.empty:
        st.info("Sem tópicos. Crie o primeiro.")
        return

    # Checklist + ações
    for _, t in df_view.iterrows():
        tid = int(t["id"])
        title = (t["title"] or "").strip() or f"Tópico {tid}"
        status = t["status"] if t["status"] in STATUS_LABEL else "todo"
        planned = t["planned_date_dt"]
        days = t["planned_weekdays"] if isinstance(t["planned_weekdays"], list) else []
        review = bool(t.get("review", False))

        plan_txt = ""
        if planned:
            plan_txt += f"📅 {planned.strftime('%d/%m')}"
        if days:
            dtxt = ",".join([WEEK_LABELS[i] for i in days])
            plan_txt += (" • " if plan_txt else "") + f"🗓 {dtxt}"
        if review:
            plan_txt += (" • " if plan_txt else "") + "🔁 Revisão"

        st.markdown(
            f"<div class='card'><b>{title}</b><br>"
            f"<span style='opacity:.85'>{plan_txt}</span><br>"
            f"<span class='status-badge {status}'>{STATUS_LABEL.get(status,status)}</span></div>",
            unsafe_allow_html=True
        )

        a1, a2, a3 = st.columns([1.2, 1.2, 1])
        if a1.button("▶️ Estudar", key=f"topic_study_{tid}"):
            st.session_state.estudos_topic_id = tid
            st.session_state.estudos_screen = "study"
            st.rerun()

        if a2.button("☑️ Estudado", key=f"topic_done_{tid}"):
            atualizar_estudos_topic(tid, {"status": "done", "review": False})
            recarregar()
            st.toast("Concluído.")
            st.rerun()

        with a3:
            st.markdown('<div class="btn-danger">', unsafe_allow_html=True)
            if st.button("Excluir", key=f"topic_del_{tid}"):
                confirmar_exclusao(f"dlg_topic_{tid}", "Confirmar exclusão", lambda tid_=tid: deletar_estudos_topic(tid_))
            st.markdown("</div>", unsafe_allow_html=True)

        with st.expander("Editar / Planejar / Reordenar"):
            new_title = st.text_input("Título", value=title, key=f"t_title_{tid}")
            st_sel = st.selectbox(
                "Status",
                options=STATUS_ORDER,
                index=STATUS_ORDER.index(status),
                format_func=lambda x: STATUS_LABEL[x],
                key=f"t_status_{tid}"
            )
            new_date = st.date_input("Data planejada", value=planned, key=f"t_date_{tid}")
            new_days = st.multiselect(
                "Dias da semana",
                options=list(range(7)),
                default=days,
                format_func=lambda i: WEEK_LABELS[i],
                key=f"t_days_{tid}"
            )
            new_review = st.checkbox("Marcar como revisão", value=review, key=f"t_rev_{tid}")

            r1, r2, r3 = st.columns(3)
            if r1.button("⬆️ Subir", key=f"t_up_{tid}"):
                _move_topic(df_t, tid, direction=-1)
                recarregar()
                st.rerun()
            if r2.button("⬇️ Descer", key=f"t_down_{tid}"):
                _move_topic(df_t, tid, direction=+1)
                recarregar()
                st.rerun()
            if r3.button("Salvar", key=f"t_save_{tid}"):
                atualizar_estudos_topic(tid, {
                    "title": new_title.strip(),
                    "status": st_sel,
                    "planned_date": new_date.isoformat() if new_date else None,
                    "planned_weekdays": new_days,
                    "review": bool(new_review)
                })
                recarregar()
                st.toast("Atualizado.")
                st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)

def _screen_study(df_s, df_t, df_l):
    tid = st.session_state.estudos_topic_id
    if not tid:
        st.info("Selecione um tópico em 'Hoje' ou em 'Matérias'.")
        return

    row = df_t[df_t["id"] == tid]
    if row.empty:
        st.warning("Tópico não encontrado.")
        return

    t = row.iloc[0]
    title = (t["title"] or "").strip()
    status = t["status"] if t["status"] in STATUS_LABEL else "todo"
    notes = t["notes"] or ""
    sid = int(t["subject_id"]) if pd.notnull(t["subject_id"]) else None
    subj_name = ""
    if sid is not None:
        sub = df_s[df_s["id"] == sid]
        subj_name = (sub.iloc[0]["name"] if not sub.empty else "") or ""

    # Top bar
    cback, copen = st.columns([1,2])
    if cback.button("← Voltar", key="study_back"):
        # volta para tópicos se tiver matéria, senão para hoje
        st.session_state.study_timer_start = None
        st.session_state.study_timer_topic = None
        st.session_state.estudos_screen = "topics" if sid is not None else "today"
        st.session_state.estudos_subject_id = sid
        st.rerun()

    st.markdown(f"### 📝 {title}")
    if subj_name:
        st.caption(f"Matéria: **{subj_name}** • Status: **{STATUS_LABEL.get(status,status)}**")
    else:
        st.caption(f"Status: **{STATUS_LABEL.get(status,status)}**")

    # Notas
    new_notes = st.text_area("Anotações rápidas", value=notes, height=200, key=f"notes_{tid}")
    if st.button("Salvar anotações", key=f"save_notes_{tid}"):
        atualizar_estudos_topic(int(tid), {"notes": new_notes})
        recarregar()
        st.toast("Notas salvas.")
        st.rerun()

    st.divider()

    # Cronômetro discreto
    timer_running = (st.session_state.study_timer_start is not None) and (st.session_state.study_timer_topic == tid)

    col1, col2 = st.columns([1.3, 1.7])
    if not timer_running:
        if col1.button("▶️ Começar estudo", key=f"start_{tid}"):
            st.session_state.study_timer_start = datetime.utcnow()
            st.session_state.study_timer_topic = tid
            atualizar_estudos_topic(int(tid), {"status": "doing"})
            st.rerun()
    else:
        start = st.session_state.study_timer_start
        mins = int((datetime.utcnow() - start).total_seconds() // 60)
        col1.metric("Tempo", f"{mins} min")

    # Finalizar guiado (tudo/parcial/revisar)
    if timer_running and col2.button("⏹ Finalizar", key=f"finish_{tid}"):
        st.session_state.show_finish_dialog = True

    if timer_running and st.session_state.get("show_finish_dialog"):
        st.markdown("#### Como foi?")
        a, b, c = st.columns(3)
        if a.button("✅ Estudei tudo", key=f"res_all_{tid}"):
            _finish_session(tid, result="all")
        if b.button("🟡 Estudei parte", key=f"res_part_{tid}"):
            _finish_session(tid, result="partial")
        if c.button("🔁 Preciso revisar", key=f"res_rev_{tid}"):
            _finish_session(tid, result="review")

    # Próximo sugerido (micro-recompensa funcional)
    if sid is not None:
        nxt = _next_suggested(df_t, sid, current_topic_id=tid)
        if nxt is not None and int(nxt["id"]) != int(tid):
            st.caption(f"➡️ Próximo sugerido: **{(nxt['title'] or '').strip()}**")

def _finish_session(topic_id: int, result: str):
    # encerra e grava log
    start = st.session_state.study_timer_start
    if start is None:
        return
    end = datetime.utcnow()
    dur = int((end - start).total_seconds() // 60)
    dur = max(1, dur)

    inserir_estudos_log({
        "topic_id": int(topic_id),
        "start_at": start.isoformat() + "Z",
        "end_at": end.isoformat() + "Z",
        "duration_min": dur,
        "result": result
    })

    # atualiza tópico de forma "honesta"
    patch = {
        "last_studied_at": end.isoformat() + "Z"
    }

    hoje = date.today()

    if result == "all":
        patch.update({"status": "done", "review": False})
        msg = "Sessão registrada. Concluído."
    elif result == "partial":
        patch.update({"status": "doing"})
        msg = "Sessão registrada. Você avançou."
    else:
        # REVIEW: decisão C -> agenda +2 dias (sem culpa)
        patch.update({
            "status": "todo",     # volta para pendente
            "review": True,
            "planned_date": (hoje + timedelta(days=2)).isoformat()
        })
        msg = "Sessão registrada. Revisão agendada para +2 dias."

    atualizar_estudos_topic(int(topic_id), patch)

    # limpa timer e recarrega
    st.session_state.study_timer_start = None
    st.session_state.study_timer_topic = None
    st.session_state.show_finish_dialog = False

    recarregar()
    st.toast(msg)
    st.rerun()
