# views/hoje_view.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import re
import streamlit as st
from datetime import datetime, date

from nlp_pt import parse_quick_entry
from github_db import (
    # tarefas/eventos
    buscar_tasks, inserir_task, atualizar_task,

    # saúde (novo)
    buscar_agua_logs, inserir_agua,
    buscar_peso_logs, inserir_peso,
    buscar_activity_logs, buscar_workout_logs,
    buscar_saude_config,

    # estudos
    buscar_estudos_topics, buscar_estudos_subjects,
)

# ---------- utils ----------
def _iso_to_dt(x: str | None):
    try:
        return datetime.fromisoformat(x) if x else None
    except Exception:
        return None

def _iso_to_date(x: str | None):
    try:
        return datetime.fromisoformat(x).date() if x else None
    except Exception:
        try:
            return date.fromisoformat(x) if x else None
        except Exception:
            return None

def _today():
    return date.today()

def _water_today_ml(water_logs: list[dict], hoje: date) -> float:
    total = 0.0
    for r in water_logs or []:
        if str(r.get("date")) == hoje.isoformat():
            try:
                total += float(r.get("amount_ml") or 0)
            except Exception:
                pass
    return float(total)

def _last_activity(activity_logs: list[dict], workout_logs: list[dict]):
    # pega o último registro (activity_logs tem date + minutes; workout_logs tem date + exercise)
    last = None
    for r in activity_logs or []:
        d = _iso_to_date(r.get("date"))
        if d:
            last = max(last, (d, f"{r.get('activity','')} ({r.get('minutes',0)} min)")) if last else (d, f"{r.get('activity','')} ({r.get('minutes',0)} min)")
    for r in workout_logs or []:
        d = _iso_to_date(r.get("date"))
        if d:
            last = max(last, (d, f"Treino: {r.get('exercise','')}")) if last else (d, f"Treino: {r.get('exercise','')}")
    return last[1] if last else "—"

def _tasks_today(tasks: list[dict], hoje: date):
    pend = []
    atras = []
    eventos = []
    for t in tasks or []:
        status = t.get("status")
        ttype = t.get("type", "task")

        if ttype == "event":
            dt = _iso_to_dt(t.get("start_at"))
            if dt and dt.date() == hoje:
                eventos.append(t)
            continue

        # task
        d = _iso_to_date(t.get("due_at"))
        if status in ("todo", "doing"):
            if d and d < hoje:
                atras.append(t)
            elif d == hoje:
                pend.append(t)
            elif d is None:
                # sem data não entra no HOJE (pode entrar num "Inbox" depois)
                pass

    # ordena eventos por hora
    eventos.sort(key=lambda x: (_iso_to_dt(x.get("start_at")) or datetime.max))
    # ordena tarefas: atrasadas primeiro
    atras.sort(key=lambda x: (_iso_to_date(x.get("due_at")) or date.min))
    pend.sort(key=lambda x: (x.get("priority") != "important", (x.get("title") or "").lower()))
    return eventos, atras, pend

def _done_today_count(tasks: list[dict], hoje: date) -> int:
    n = 0
    for t in tasks or []:
        if t.get("status") == "done":
            dt = _iso_to_dt(t.get("completed_at")) or _iso_to_dt(t.get("updated_at"))
            if dt and dt.date() == hoje:
                n += 1
    return n

def _study_planned_today(topics: list[dict], hoje: date):
    wd = hoje.weekday()
    planned = []
    for t in topics or []:
        if not isinstance(t, dict) or not t.get("active", True):
            continue
        if str(t.get("status")) == "done":
            continue
        if t.get("planned_date") == hoje.isoformat():
            planned.append(t)
            continue
        wds = t.get("planned_weekdays") or []
        if isinstance(wds, list) and wd in wds:
            planned.append(t)
    planned.sort(key=lambda x: (x.get("subject_id", 9999), x.get("order", 9999)))
    return planned[:5]

# ---------- entrada universal ----------
def _parse_universal(text: str):
    s = (text or "").strip().lower()
    if not s:
        return ("noop", None)

    # água: "agua 500" / "água 600ml" / "water 300"
    if s.startswith(("agua", "água", "water")):
        m = re.search(r"(\d{2,4})", s)
        ml = int(m.group(1)) if m else 250
        return ("water", {"amount_ml": ml})

    # peso: "peso 79.8" / "79,8kg"
    if s.startswith("peso") or "kg" in s:
        m = re.search(r"(\d{2,3}([.,]\d)?)", s)
        if m:
            val = float(m.group(1).replace(",", "."))
            return ("weight", {"weight_kg": val})
        return ("weight", None)

    # fallback -> tarefas/eventos pelo NLP existente
    payload = parse_quick_entry(text)
    return ("task_or_event", payload)

def render_hoje():
    st.markdown("""
      <div class="header-container">
        <div class="main-title">🏠 Hoje</div>
        <div class="slogan">Abra o app e já saiba o que fazer.</div>
      </div>
    """, unsafe_allow_html=True)

    hoje = _today()

    # --- cache: puxa só se não existir ---
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
    if "est_topics" not in st.session_state:
        st.session_state.est_topics = buscar_estudos_topics()
    if "est_subjects" not in st.session_state:
        st.session_state.est_subjects = buscar_estudos_subjects()

    # --- entrada única ---
    st.text_input(
        "O que você quer registrar?",
        placeholder="Ex: água 500 | peso 79.8 | Reunião amanhã 15h | Pagar boleto 12/02 #contas",
        key="hoje_quick"
    )
    c1, c2 = st.columns([3, 1])
    with c2:
        if st.button("Registrar", use_container_width=True):
            kind, data = _parse_universal(st.session_state.get("hoje_quick"))
            if kind == "water" and data:
                inserir_agua({"date": hoje.isoformat(), "amount_ml": int(data["amount_ml"])})
                st.session_state.agua_logs = buscar_agua_logs()
                st.toast(f"+{int(data['amount_ml'])} ml")
                st.rerun()

            elif kind == "weight" and data:
                inserir_peso({"date": hoje.isoformat(), "weight_kg": float(data["weight_kg"])})
                st.session_state.peso_logs = buscar_peso_logs()
                st.toast("Peso registrado.")
                st.rerun()

            elif kind == "task_or_event" and data:
                data.update({
                    "assignee": "Ambos",
                    "created_at": datetime.utcnow().isoformat() + "Z",
                    "updated_at": None
                })
                inserir_task(data)
                st.session_state.tasks = buscar_tasks()
                st.toast(f"✅ Adicionado: {data.get('title','')}")
                st.rerun()

    st.divider()

    # --- métricas honestas ---
    done_today = _done_today_count(st.session_state.tasks, hoje)
    water_today = _water_today_ml(st.session_state.agua_logs, hoje)
    last_act = _last_activity(st.session_state.activity_logs, st.session_state.w_logs)

    m1, m2, m3 = st.columns(3)
    m1.metric("Feitas hoje", str(done_today))
    m2.metric("Água hoje (ml)", str(int(water_today)))
    m3.metric("Última atividade", last_act)

    st.divider()

    # --- cards do HOJE ---
    eventos, atrasadas, pendentes = _tasks_today(st.session_state.tasks, hoje)

    # Eventos
    st.subheader("⏰ Eventos de hoje")
    if not eventos:
        st.caption("Sem eventos hoje.")
    else:
        for e in eventos[:6]:
            dt = _iso_to_dt(e.get("start_at"))
            st.write(f"• **{dt.strftime('%H:%M') if dt else '—'}** — {e.get('title','')}")

    # Tarefas atrasadas
    st.subheader("🔴 Atrasadas")
    if not atrasadas:
        st.caption("Nada atrasado ✅")
    else:
        for t in atrasadas[:6]:
            st.write(f"• {t.get('title','')} — vence em {t.get('due_at')}")
            if st.button("Finalizar", key=f"hoje_done_{t['id']}"):
                atualizar_task(int(t["id"]), {"status": "done", "completed_at": datetime.utcnow().isoformat() + "Z"})
                st.session_state.tasks = buscar_tasks()
                st.toast("Concluída.")
                st.rerun()

    # Tarefas de hoje
    st.subheader("✅ Pra hoje")
    if not pendentes:
        st.caption("Nada pendente pra hoje.")
    else:
        for t in pendentes[:10]:
            st.write(f"• {t.get('title','')}")
            if st.button("Finalizar", key=f"hoje_done_today_{t['id']}"):
                atualizar_task(int(t["id"]), {"status": "done", "completed_at": datetime.utcnow().isoformat() + "Z"})
                st.session_state.tasks = buscar_tasks()
                st.toast("Concluída.")
                st.rerun()

    # Estudos planejados
    st.subheader("📚 Estudo de hoje")
    planned = _study_planned_today(st.session_state.est_topics, hoje)
    if not planned:
        st.caption("Nada planejado hoje.")
    else:
        # monta mapa subject_id -> nome
        subj_map = {int(s.get("id")): s.get("name") for s in (st.session_state.est_subjects or []) if isinstance(s, dict) and str(s.get("id","")).isdigit()}
        for t in planned:
            subj = subj_map.get(int(t.get("subject_id", -1)), "—")
            st.write(f"• **{subj}** — {t.get('title','')}")
