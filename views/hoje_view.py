# views/hoje_view.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import re
import unicodedata
import streamlit as st
from datetime import datetime, date, timedelta

from nlp_pt import parse_quick_entry
from github_db import (
    # Tarefas / Eventos
    buscar_tasks, inserir_task, atualizar_task,

    # Saúde
    buscar_agua_logs, inserir_agua,
    buscar_peso_logs, inserir_peso,
    buscar_activity_logs, buscar_workout_logs,
    buscar_saude_config,

    # Estudos
    buscar_estudos_topics, buscar_estudos_subjects, buscar_estudos_logs,
    inserir_estudos_log, atualizar_estudos_topic,
)

# ============================================================
# 0) TOLERÂNCIA A ERROS (normalização + aliases + correções)
# ============================================================
INTENT_ALIASES = {
    "water": {"agua", "agu", "aguas", "h2o", "water"},
    "weight": {"peso", "kg"},
    "study": {"estudo", "estudar", "study"},
}

COMMON_CORRECTIONS = {
    # água
    "aguaa": "agua",
    "aguac": "agua",
    "aguae": "agua",
    "aguá": "agua",      # caso venha com acento
    "agaua": "agua",
    "h20": "h2o",
    # peso
    "pseo": "peso",
    "peos": "peso",
    "psso": "peso",
    # estudo
    "estduo": "estudo",
    "estdo": "estudo",
    "estdu": "estudo",
}

def _strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn")

def _normalize_text(s: str) -> str:
    s = (s or "").strip()
    s = _strip_accents(s)
    s = s.lower()
    s = re.sub(r"\s+", " ", s)
    return s

def _apply_common_corrections(norm: str) -> str:
    out = norm
    for wrong, right in COMMON_CORRECTIONS.items():
        out = out.replace(wrong, right)
    return out

def _match_intent(norm: str) -> str | None:
    """
    Decide intenção por aliases tolerantes.
    - olha prefixo e tokens
    """
    tokens = set(re.split(r"\W+", norm))
    tokens.discard("")
    for intent, aliases in INTENT_ALIASES.items():
        # prefixo
        if any(norm.startswith(a) for a in aliases):
            return intent
        # token
        if any(a in tokens for a in aliases):
            return intent
    return None

# =========================
# Utils: datas/parse
# =========================
def _iso_to_dt(x: str | None):
    try:
        return datetime.fromisoformat(x) if x else None
    except Exception:
        return None

def _iso_to_date(x: str | None):
    # topics/weight/water usam date ISO (YYYY-MM-DD); tasks/events podem usar ISO datetime
    if not x:
        return None
    try:
        return date.fromisoformat(str(x))
    except Exception:
        try:
            return datetime.fromisoformat(str(x)).date()
        except Exception:
            return None

def _today() -> date:
    return date.today()

def _fmt_hhmm(dt: datetime | None) -> str:
    return dt.strftime("%H:%M") if dt else "—"

def _fmt_date_br(d: date | None) -> str:
    return d.strftime("%d/%m") if d else "—"

# =========================
# Saúde: cálculos rápidos
# =========================
def _water_today_ml(water_logs: list[dict], hoje: date) -> float:
    total = 0.0
    for r in (water_logs or []):
        if str(r.get("date")) == hoje.isoformat():
            try:
                total += float(r.get("amount_ml") or 0)
            except Exception:
                pass
    return float(total)

def _get_last_weight_kg(peso_logs: list[dict]) -> float | None:
    last = None
    last_d = None
    for r in (peso_logs or []):
        d = _iso_to_date(r.get("date"))
        if not d:
            continue
        try:
            w = float(r.get("weight_kg"))
        except Exception:
            continue
        if (last_d is None) or (d > last_d):
            last_d, last = d, w
    return last

def _auto_water_goal_ml(cfg: dict, last_weight_kg: float | None) -> int:
    # compatível com seu padrão: cfg["water_goal_ml"] override; senão peso*35ml (clamp 1500..4500)
    if isinstance(cfg, dict) and cfg.get("water_goal_ml") not in (None, ""):
        try:
            return int(cfg.get("water_goal_ml"))
        except Exception:
            pass
    if last_weight_kg and last_weight_kg > 0:
        goal = int(round(last_weight_kg * 35))
        goal = max(1500, min(4500, goal))
        # arredonda para 50ml
        goal = int(round(goal / 50.0) * 50)
        return goal
    return 2000

def _last_activity_text(activity_logs: list[dict], workout_logs: list[dict]) -> str:
    # activity_logs: date, activity, minutes; workout_logs: date, exercise
    best_dt = None
    best_txt = None

    for r in (activity_logs or []):
        d = _iso_to_date(r.get("date"))
        if not d:
            continue
        txt = f"{(r.get('activity') or '').strip()} ({int(r.get('minutes') or 0)} min)"
        if best_dt is None or d > best_dt:
            best_dt, best_txt = d, txt

    for r in (workout_logs or []):
        d = _iso_to_date(r.get("date"))
        if not d:
            continue
        txt = f"Treino: {(r.get('exercise') or '').strip()}"
        if best_dt is None or d > best_dt:
            best_dt, best_txt = d, txt

    return best_txt or "—"

# =========================
# Tarefas/Eventos do dia
# =========================
def _task_day(t: dict) -> date | None:
    if t.get("type") == "event":
        dt = _iso_to_dt(t.get("start_at"))
        return dt.date() if dt else None
    return _iso_to_date(t.get("due_at"))

def _is_overdue_task(t: dict, hoje: date) -> bool:
    if t.get("type") == "event":
        return False
    if t.get("status") not in ("todo", "doing"):
        return False
    d = _task_day(t)
    return bool(d and d < hoje)

def _is_today_task(t: dict, hoje: date) -> bool:
    if t.get("type") == "event":
        return False
    if t.get("status") not in ("todo", "doing"):
        return False
    d = _task_day(t)
    return bool(d and d == hoje)

def _events_today(tasks: list[dict], hoje: date) -> list[dict]:
    ev = []
    for t in (tasks or []):
        if t.get("type") == "event":
            dt = _iso_to_dt(t.get("start_at"))
            if dt and dt.date() == hoje:
                ev.append(t)
    ev.sort(key=lambda x: (_iso_to_dt(x.get("start_at")) or datetime.max))
    return ev

def _done_today_count(tasks: list[dict], hoje: date) -> int:
    n = 0
    for t in (tasks or []):
        if t.get("status") != "done":
            continue
        dt = _iso_to_dt(t.get("completed_at")) or _iso_to_dt(t.get("updated_at"))
        if dt and dt.date() == hoje:
            n += 1
    return n

# =========================
# Estudos: planejado hoje + match subject+topic
# =========================
def _study_planned_today(topics: list[dict], hoje: date) -> list[dict]:
    wd = hoje.weekday()
    planned = []
    for tp in (topics or []):
        if not isinstance(tp, dict):
            continue
        if not tp.get("active", True):
            continue
        if str(tp.get("status")) == "done":
            continue

        if tp.get("planned_date") == hoje.isoformat():
            planned.append(tp)
            continue

        wds = tp.get("planned_weekdays") or []
        if isinstance(wds, list) and wd in wds:
            planned.append(tp)

    planned.sort(key=lambda x: (int(x.get("subject_id", 9999)), int(x.get("order", 9999))))
    return planned

def _tokens(txt: str) -> list[str]:
    return [t for t in re.split(r"\W+", (txt or "").lower()) if t]

def _score_match(query: str, subject_name: str, topic_title: str) -> int:
    q = _tokens(query)
    if not q:
        return 0

    subj = (subject_name or "").lower()
    title = (topic_title or "").lower()
    hay = (subj + " " + title).strip()

    score = 0
    if query.lower() in hay:
        score += 6

    subj_set = set(_tokens(subj))
    title_set = set(_tokens(title))

    for tok in q:
        if tok in title_set:
            score += 3
        elif tok in subj_set:
            score += 2

    return score

def _pick_topic_id_for_study(query: str, topics: list[dict], planned_today: list[dict], subj_map: dict[int, str]) -> int | None:
    query = (query or "").strip()
    if not query:
        return int(planned_today[0]["id"]) if planned_today else None

    best_sc = 0
    best_id = None
    for tp in (topics or []):
        if not isinstance(tp, dict):
            continue
        if not tp.get("active", True):
            continue
        if str(tp.get("status")) == "done":
            continue

        try:
            sid = int(tp.get("subject_id"))
        except Exception:
            sid = -1
        subj_name = subj_map.get(sid, "")
        title = tp.get("title") or ""

        sc = _score_match(query, subj_name, title)
        if sc > best_sc:
            best_sc = sc
            try:
                best_id = int(tp.get("id"))
            except Exception:
                best_id = None

    if best_id is None:
        return None

    # limiar contra match fraco
    if best_sc < 5:
        return None

    return best_id

def _extract_duration_min(s: str) -> int:
    m = re.search(r"(\d{1,3})\s*(minutos|min|m)\b", (s or "").lower())
    if m:
        return max(0, int(m.group(1)))
    m2 = re.search(r"\b(\d{1,3})\b", (s or "").lower())
    if m2:
        return max(0, int(m2.group(1)))
    return 25

def _extract_result(s: str) -> str:
    t = (s or "").lower()
    if "revis" in t or "review" in t:
        return "review"
    if "tudo" in t or "all" in t or "completo" in t or "complete" in t:
        return "all"
    return "partial"

def _clean_study_text(s: str) -> str:
    t = (s or "").lower()
    t = re.sub(r"\b(estudo|estudar|study)\b", "", t).strip()
    t = re.sub(r"\b\d{1,3}\s*(minutos|min|m)\b", "", t).strip()
    t = re.sub(r"\b(revis(ao|ão)?|review|tudo|all|complete|completo)\b", "", t).strip()
    return t.strip(" ,;.-")

def _create_study_log(topic_id: int, duration_min: int, result: str = "partial"):
    start = datetime.utcnow()
    end = start + timedelta(minutes=max(0, int(duration_min)))

    inserir_estudos_log({
        "topic_id": int(topic_id),
        "start_at": start.isoformat() + "Z",
        "end_at": end.isoformat() + "Z",
        "duration_min": int(duration_min),
        "result": result,
    })
    # atualiza tópico: last_studied_at e status "doing" (leve)
    atualizar_estudos_topic(int(topic_id), {
        "last_studied_at": end.isoformat() + "Z",
        "status": "doing"
    })

# =========================
# Entrada universal (tolerante): água / peso / estudo / tarefas-eventos
# =========================
def _parse_universal(text: str, topics: list[dict], planned_today: list[dict], subj_map: dict[int, str]):
    raw = (text or "").strip()
    if not raw:
        return ("noop", None)

    # normaliza/tolera erros
    norm = _normalize_text(raw)
    norm = _apply_common_corrections(norm)

    intent = _match_intent(norm)

    # água
    if intent == "water":
        m = re.search(r"(\d{2,4})", norm)
        ml = int(m.group(1)) if m else 250
        return ("water", {"amount_ml": ml})

    # peso
    if intent == "weight":
        m = re.search(r"(\d{2,3}([.,]\d)?)", norm)
        if m:
            val = float(m.group(1).replace(",", "."))
            return ("weight", {"weight_kg": val})
        return ("weight", None)

    # estudo
    if intent == "study":
        dur = _extract_duration_min(norm)
        res = _extract_result(norm)
        q = _clean_study_text(raw)  # usa o RAW para manter nomes (melhor)
        tid = _pick_topic_id_for_study(q, topics, planned_today, subj_map)
        return ("study", {"topic_id": tid, "duration_min": dur, "result": res, "query": q})

    # fallback -> NLP de tarefa/evento (usa RAW para o NLP ficar mais forte)
    payload = parse_quick_entry(raw)
    return ("task_or_event", payload)

# =========================
# Render HOJE
# =========================
def render_hoje():
    st.markdown("""
      <div class="header-container">
        <div class="main-title">🏠 Hoje</div>
        <div class="slogan">Abra o app e já saiba o que fazer.</div>
      </div>
    """, unsafe_allow_html=True)

    hoje = _today()

    # ---------- cache em sessão ----------
    if "tasks" not in st.session_state:
        st.session_state.tasks = buscar_tasks()

    if "agua_logs" not in st.session_state:
        st.session_state.agua_logs = buscar_agua_logs()

    if "peso_logs" not in st.session_state:
        st.session_state.peso_logs = buscar_peso_logs()

    if "activity_logs" not in st.session_state:
        st.session_state.activity_logs = buscar_activity_logs()

    if "w_logs" not in st.session_state:
        st.session_state.w_logs = buscar_workout_logs()

    if "saude_cfg" not in st.session_state:
        st.session_state.saude_cfg = buscar_saude_config()

    if "est_subjects" not in st.session_state:
        st.session_state.est_subjects = buscar_estudos_subjects()

    if "est_topics" not in st.session_state:
        st.session_state.est_topics = buscar_estudos_topics()

    if "est_logs" not in st.session_state:
        st.session_state.est_logs = buscar_estudos_logs()

    # ---------- estudos: subj_map + planejados hoje ----------
    subj_map = {
        int(s.get("id")): (s.get("name") or "").strip()
        for s in (st.session_state.est_subjects or [])
        if isinstance(s, dict) and str(s.get("id", "")).isdigit()
    }

    planned = _study_planned_today(st.session_state.est_topics, hoje)

    # ---------- Entrada única ----------
    st.text_input(
        "O que você quer registrar?",
        placeholder="Ex: aguá 500 | pseo 79.8 | estudo 25min direito constitucional | Reunião amanhã 15h | Pagar boleto 12/02 #contas",
        key="hoje_quick"
    )
    cA, cB = st.columns([4, 1])
    with cB:
        if st.button("Registrar", use_container_width=True):
            kind, data = _parse_universal(
                st.session_state.get("hoje_quick"),
                st.session_state.est_topics,
                planned,
                subj_map
            )

            if kind == "water":
                inserir_agua({"date": hoje.isoformat(), "amount_ml": int(data["amount_ml"])})
                st.session_state.agua_logs = buscar_agua_logs()
                st.toast(f"+{int(data['amount_ml'])} ml")
                st.rerun()
                return

            elif kind == "weight":
                if data and data.get("weight_kg") is not None:
                    inserir_peso({"date": hoje.isoformat(), "weight_kg": float(data["weight_kg"])})
                    st.session_state.peso_logs = buscar_peso_logs()
                    st.toast("Peso registrado.")
                    st.rerun()
                    return
                else:
                    st.warning("Não entendi o peso. Ex: 'peso 79.8'")

            elif kind == "study":
                if data.get("topic_id") is None:
                    # fallback 1-toque
                    st.session_state["_pending_study"] = data
                    st.rerun()
                    return

                _create_study_log(int(data["topic_id"]), int(data["duration_min"]), str(data["result"]))
                st.session_state.est_logs = buscar_estudos_logs()
                st.toast(f"📚 Estudo registrado: {int(data['duration_min'])} min")
                st.rerun()
                return

            elif kind == "task_or_event":
                payload = dict(data or {})
                payload.update({
                    "assignee": "Ambos",
                    "created_at": datetime.utcnow().isoformat() + "Z",
                    "updated_at": None
                })
                inserir_task(payload)
                st.session_state.tasks = buscar_tasks()
                st.toast(f"✅ Adicionado: {payload.get('title','')}")
                st.rerun()
                return

    # ---------- fallback seletor de tópico (quando match falha) ----------
    if st.session_state.get("_pending_study"):
        pend = st.session_state["_pending_study"]
        st.markdown("**Escolha o tópico (1 toque):**")

        # planejados hoje primeiro, depois ativos
        options = []
        seen = set()

        for tp in planned:
            try:
                tid = int(tp.get("id"))
            except Exception:
                continue
            options.append(tp)
            seen.add(tid)

        for tp in (st.session_state.est_topics or []):
            if not isinstance(tp, dict) or not tp.get("active", True) or str(tp.get("status")) == "done":
                continue
            try:
                tid = int(tp.get("id"))
            except Exception:
                continue
            if tid not in seen:
                options.append(tp)
                seen.add(tid)

        def _label(tp: dict) -> str:
            try:
                sid = int(tp.get("subject_id"))
            except Exception:
                sid = -1
            subj = subj_map.get(sid, "—")
            return f"{int(tp.get('id'))} — {subj} — {tp.get('title','')}"

        labels = [_label(tp) for tp in options] if options else []
        if not labels:
            st.warning("Você não tem tópicos ativos para registrar estudo.")
            st.session_state["_pending_study"] = None
        else:
            sel = st.selectbox("Tópico", labels, index=0, key="study_topic_pick")
            if st.button("Salvar estudo", key="study_pick_save"):
                picked_id = int(sel.split("—")[0].strip())
                _create_study_log(picked_id, int(pend["duration_min"]), str(pend["result"]))
                st.session_state.est_logs = buscar_estudos_logs()
                st.session_state["_pending_study"] = None
                st.toast(f"📚 Estudo registrado: {int(pend['duration_min'])} min")
                st.rerun()
                return

    st.divider()

    # ---------- Métricas honestas ----------
    done_today = _done_today_count(st.session_state.tasks, hoje)
    water_today = _water_today_ml(st.session_state.agua_logs, hoje)
    last_w = _get_last_weight_kg(st.session_state.peso_logs)
    water_goal = _auto_water_goal_ml(st.session_state.saude_cfg, last_w)
    last_act = _last_activity_text(st.session_state.activity_logs, st.session_state.w_logs)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Feitas hoje", str(done_today))
    m2.metric("Água hoje", f"{int(water_today)} ml", delta=("Meta batida" if water_today >= water_goal else None))
    m3.metric("Meta água", f"{int(water_goal)} ml")
    m4.metric("Última atividade", last_act)

    st.divider()

    # ---------- Seções do dia ----------
    # Eventos
    st.subheader("⏰ Eventos de hoje")
    ev = _events_today(st.session_state.tasks, hoje)
    if not ev:
        st.caption("Sem eventos hoje.")
    else:
        for e in ev[:8]:
            dt = _iso_to_dt(e.get("start_at"))
            st.write(f"• **{_fmt_hhmm(dt)}** — {e.get('title','')}")

    # Tarefas atrasadas e de hoje
    st.subheader("✅ Tarefas pendentes e atrasadas")
    atrasadas = [t for t in (st.session_state.tasks or []) if _is_overdue_task(t, hoje)]
    pendentes = [t for t in (st.session_state.tasks or []) if _is_today_task(t, hoje)]

    if not atrasadas and not pendentes:
        st.caption("Nada pendente por data hoje ✅")
    else:
        if atrasadas:
            st.markdown("**🔴 Atrasadas**")
            atrasadas.sort(key=lambda t: (_task_day(t) or date.min))
            for t in atrasadas[:8]:
                d = _task_day(t)
                c1, c2 = st.columns([4, 1])
                with c1:
                    st.write(f"• {t.get('title','')} — vence em **{_fmt_date_br(d)}**")
                with c2:
                    if st.button("Finalizar", key=f"hoje_done_over_{t['id']}"):
                        atualizar_task(int(t["id"]), {
                            "status": "done",
                            "completed_at": datetime.utcnow().isoformat() + "Z"
                        })
                        st.session_state.tasks = buscar_tasks()
                        st.toast("Concluída.")
                        st.rerun()
                        return

        if pendentes:
            st.markdown("**🟡 Para hoje**")
            pendentes.sort(key=lambda t: (t.get("priority") != "important", (t.get("title") or "").lower()))
            for t in pendentes[:12]:
                c1, c2 = st.columns([4, 1])
                with c1:
                    star = "⭐ " if t.get("priority") == "important" else ""
                    st.write(f"• {star}{t.get('title','')}")
                with c2:
                    if st.button("Finalizar", key=f"hoje_done_today_{t['id']}"):
                        atualizar_task(int(t["id"]), {
                            "status": "done",
                            "completed_at": datetime.utcnow().isoformat() + "Z"
                        })
                        st.session_state.tasks = buscar_tasks()
                        st.toast("Concluída.")
                        st.rerun()
                        return

    st.divider()

    # Água (quick actions)
    st.subheader("💧 Água do dia")
    prog = min(water_today / max(1, water_goal), 1.0)
    st.progress(prog)
    st.caption(f"{int(water_today)} / {int(water_goal)} ml")

    a1, a2, a3 = st.columns(3)
    if a1.button("+250 ml", key="hoje_water_250"):
        inserir_agua({"date": hoje.isoformat(), "amount_ml": 250})
        st.session_state.agua_logs = buscar_agua_logs()
        st.toast("+250 ml")
        st.rerun()
        return
    if a2.button("+500 ml", key="hoje_water_500"):
        inserir_agua({"date": hoje.isoformat(), "amount_ml": 500})
        st.session_state.agua_logs = buscar_agua_logs()
        st.toast("+500 ml")
        st.rerun()
        return
    if a3.button("+600 ml", key="hoje_water_600"):
        inserir_agua({"date": hoje.isoformat(), "amount_ml": 600})
        st.session_state.agua_logs = buscar_agua_logs()
        st.toast("+600 ml")
        st.rerun()
        return

    st.divider()

    # Estudos planejados hoje
    st.subheader("📚 Estudo planejado hoje")
    if not planned:
        st.caption("Nada planejado hoje.")
    else:
        for tp in planned[:6]:
            try:
                sid = int(tp.get("subject_id"))
            except Exception:
                sid = -1
            subj = subj_map.get(sid, "—")
            title = tp.get("title", "")
            tid = int(tp.get("id"))

            c1, c2, c3 = st.columns([4, 1, 1])
            with c1:
                st.write(f"• **{subj}** — {title}")
            with c2:
                if st.button("+25min", key=f"hoje_study_25_{tid}"):
                    _create_study_log(tid, 25, "partial")
                    st.session_state.est_logs = buscar_estudos_logs()
                    st.toast("📚 +25min registrados.")
                    st.rerun()
                    return
            with c3:
                if st.button("Revisão 15m", key=f"hoje_study_rev_{tid}"):
                    _create_study_log(tid, 15, "review")
                    st.session_state.est_logs = buscar_estudos_logs()
                    st.toast("📚 Revisão registrada.")
                    st.rerun()
                    return
