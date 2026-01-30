# views/tarefas_view.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import time
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from datetime import datetime, date, timedelta

from github_db import (
    buscar_tasks, inserir_task, atualizar_task, deletar_task, buscar_pessoas
)
from ui_helpers import confirmar_exclusao
from nlp_pt import parse_quick_entry

STATUS_LABELS = {
    "todo": "Não Iniciado",
    "doing": "Em Progresso",
    "done": "Finalizado",
    "cancelled": "Cancelado"
}


def _iso_to_date(x):
    try:
        return datetime.fromisoformat(x).date() if x else None
    except Exception:
        return None


def _iso_to_dt(x):
    try:
        return datetime.fromisoformat(x) if x else None
    except Exception:
        return None


def _group_for_agenda(tasks):
    agenda = {}
    for t in tasks:
        d = None
        if t.get("type") == "event":
            s = _iso_to_dt(t.get("start_at"))
            d = s.date() if s else None
        else:
            d = _iso_to_date(t.get("due_at"))
        agenda.setdefault(d, []).append(t)
    return agenda


def _progress_of_today(tasks):
    today = date.today()
    total = 0
    done = 0
    for t in tasks:
        if t.get("type") == "event":
            s = _iso_to_dt(t.get("start_at"))
            if s and s.date() == today:
                total += 1
                if t.get("status") == "done":
                    done += 1
        else:
            d = _iso_to_date(t.get("due_at"))
            if d == today:
                total += 1
                if t.get("status") == "done":
                    done += 1
    return done, total


def _next_from_recurrence(t: dict):
    rec = t.get("recurrence")
    if not rec:
        return None
    freq = rec.get("freq")
    interval = int(rec.get("interval", 1) or 1)

    if t.get("type") == "event":
        s = _iso_to_dt(t.get("start_at"))
        if not s:
            return None
        if freq == "daily":
            return s + timedelta(days=interval)
        if freq == "weekly":
            return s + timedelta(weeks=interval)
        if freq == "monthly":
            return s + timedelta(days=30 * interval)  # simplificação
    else:
        d = _iso_to_date(t.get("due_at"))
        if not d:
            return None
        if freq == "daily":
            return d + timedelta(days=interval)
        if freq == "weekly":
            return d + timedelta(weeks=interval)
        if freq == "monthly":
            return d + timedelta(days=30 * interval)  # simplificação

    return None


def _inject_notifications():
    components.html(
        """
        <script>
        (async function(){
          if (!('Notification' in window)) return;
          try{
            await Notification.requestPermission();
            window._notifyTask = function(title, body){
              if (Notification.permission === 'granted'){
                const n = new Notification(title, { body });
                n.onclick = () => window.focus();
              }
            }
          }catch(e){}
        })();
        </script>
        """,
        height=0
    )


def render_tarefas():
    st.markdown(
        """
        <div class="header-container">
          <div class="main-title">🗓️ Tarefas</div>
          <div class="slogan">Entrada inteligente. Hoje primeiro. Sem fricção.</div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # ==========================
    # Bootstrap estado
    # ==========================
    if "tasks" not in st.session_state:
        st.session_state.tasks = buscar_tasks()

    if "pessoas" not in st.session_state or not st.session_state.pessoas:
        st.session_state.pessoas = buscar_pessoas()

    # Flags de controle da entrada rápida
    st.session_state.setdefault("_clear_quick", False)
    st.session_state.setdefault("_busy_add", False)
    st.session_state.setdefault("_last_add_text", "")
    st.session_state.setdefault("_last_add_ts", 0.0)

    # Limpa o input ANTES de criar o widget (evita StreamlitAPIException)
    if st.session_state.get("_clear_quick"):
        st.session_state["quick_in"] = ""
        st.session_state["_clear_quick"] = False

    tasks = st.session_state.tasks

    # ======= Notificações Web (in-app) opcional =======
    _inject_notifications()

    # ==========================
    # Entrada rápida (1 toque)
    # ==========================
    st.markdown("#### ✍️ Adicionar")

def _add_quick_from_text(txt: str):
    txt = (txt or "").strip()
    if not txt:
        return

    now_ts = time.time()
    if txt == st.session_state.get("_last_add_text") and (now_ts - st.session_state.get("_last_add_ts", 0.0)) < 1.5:
        return

    if st.session_state.get("_busy_add"):
        return

    st.session_state["_busy_add"] = True
    try:
        payload = parse_quick_entry(txt)
        payload.update({
            "assignee": "Ambos",
            "created_at": datetime.utcnow().isoformat() + "Z"
        })

        ok = inserir_task(payload)

        if ok:
            st.session_state["_last_add_text"] = txt
            st.session_state["_last_add_ts"] = now_ts
            st.session_state["_clear_quick"] = True
            st.session_state.tasks = buscar_tasks()
            st.toast(f"✅ Adicionado: {payload.get('title')}")
            st.rerun()
        else:
            st.error("Não consegui salvar agora (concorrência/sincronização). Tente novamente em 2s.")
    except Exception as e:
        st.error(f"Erro no processamento: {e}")
    finally:
        st.session_state["_busy_add"] = False

    def _on_enter_add():
        # callback: pode ler e usar o valor do widget
        _add_quick_from_text(st.session_state.get("quick_in"))

    cqi1, cqi2 = st.columns([4, 1])
    with cqi1:
        st.text_input(
            "Digite e pressione Enter",
            placeholder="Ex.: Reunião amanhã 15h / Pagar boleto 12/02 / Comprar leite #casa",
            label_visibility="collapsed",
            key="quick_in",
            on_change=_on_enter_add
        )

    with cqi2:
        if st.button("➕", use_container_width=True):
            # no clique, usamos o valor atual, mas limpamos no próximo rerun via flag
            _add_quick_from_text(st.session_state.get("quick_in"))

    # ==========================
    # Progresso do dia
    # ==========================
    done, total = _progress_of_today(tasks)
    if total > 0:
        pct = int((done / total) * 100)
        st.progress(pct / 100, text=f"Progresso de hoje: {done}/{total} ({pct}%)")
    else:
        st.progress(0.0, text="Sem itens para hoje ainda")

    st.divider()

    tab_hoje, tab_prox, tab_done = st.tabs(["Hoje", "Próximos", "Concluídos"])

    # ==========================
    # Ações rápidas (key_ns)
    # ==========================
    def _render_quick_actions(t, key_ns: str = ""):
        col = st.columns([1, 1, 1, 1, 1])

        # concluir
        with col[0]:
            chk = st.checkbox(
                "Feita",
                value=(t.get("status") == "done"),
                key=f"chk_{key_ns}{t['id']}"
            )
            if chk and t.get("status") != "done":
                patch = {"status": "done", "completed_at": datetime.utcnow().isoformat() + "Z"}
                nxt = _next_from_recurrence(t)

                # recorrente: gera próxima
                if nxt:
                    if t.get("type") == "event":
                        inserir_task({
                            **{k: v for k, v in t.items() if k != 'id'},
                            "status": "todo",
                            "start_at": nxt.isoformat(),
                            "created_at": datetime.utcnow().isoformat() + "Z",
                            "updated_at": None,
                            "completed_at": None
                        })
                    else:
                        patch["status"] = "todo"
                        patch["due_at"] = nxt.isoformat()

                atualizar_task(int(t["id"]), patch)
                st.session_state.tasks = buscar_tasks()
                st.rerun()

        # +1 dia
        with col[1]:
            if st.button("+1d", key=f"plus1_{key_ns}{t['id']}"):
                if t.get("type") == "event":
                    s = _iso_to_dt(t.get("start_at")) or datetime.now()
                    atualizar_task(int(t["id"]), {"start_at": (s + timedelta(days=1)).isoformat()})
                else:
                    d = _iso_to_date(t.get("due_at")) or date.today()
                    atualizar_task(int(t["id"]), {"due_at": (d + timedelta(days=1)).isoformat()})
                st.session_state.tasks = buscar_tasks()
                st.rerun()

        # amanhã
        with col[2]:
            if st.button("Amanhã", key=f"tmw_{key_ns}{t['id']}"):
                if t.get("type") == "event":
                    s = _iso_to_dt(t.get("start_at")) or datetime.now()
                    base_dt = datetime.combine(date.today() + timedelta(days=1), s.time())
                    atualizar_task(int(t["id"]), {"start_at": base_dt.isoformat()})
                else:
                    atualizar_task(int(t["id"]), {"due_at": (date.today() + timedelta(days=1)).isoformat()})
                st.session_state.tasks = buscar_tasks()
                st.rerun()

        # importante
        with col[3]:
            imp = t.get("priority", "normal") == "important"
            label = "⭐" if not imp else "⭐ Importante"
            if st.button(label, key=f"imp_{key_ns}{t['id']}"):
                atualizar_task(int(t["id"]), {"priority": ("normal" if imp else "important")})
                st.session_state.tasks = buscar_tasks()
                st.rerun()

        # excluir
        with col[4]:
            st.markdown('<div class="btn-excluir">', unsafe_allow_html=True)
            if st.button("Excluir", key=f"del_{key_ns}{t['id']}"):
                confirmar_exclusao(
                    f"dlg_task_{key_ns}{t['id']}",
                    "Confirmar exclusão",
                    lambda: deletar_task(int(t["id"]))
                )
            st.markdown('</div>', unsafe_allow_html=True)

    def _render_edit_inline(t):
        nt = st.text_input("Título", value=t.get("title", ""), key=f"et_{t['id']}")
        nd = st.text_input("Detalhes", value=t.get("description", ""), key=f"ed_{t['id']}")
        st.caption("Reagendamento e ações rápidas")
        _render_quick_actions(t, key_ns="e_")  # evita colisão com o cartão
        if st.button("Salvar", key=f"save_{t['id']}"):
            patch = {
                "title": nt.strip(),
                "description": nd.strip(),
                "updated_at": datetime.utcnow().isoformat() + "Z"
            }
            atualizar_task(int(t["id"]), patch)
            st.toast("Atualizado!")
            st.session_state.tasks = buscar_tasks()
            st.rerun()

    def _render_entry(t):
        is_event = (t.get("type") == "event")
        if is_event:
            s = _iso_to_dt(t.get("start_at"))
            head = f"🗓️ {s.strftime('%d/%m %H:%M') if s else '—'}"
        else:
            d = _iso_to_date(t.get("due_at"))
            head = f"📝 {d.strftime('%d/%m') if d else 'Sem data'}"

        st.markdown(f"""
        <div class="task-card">
          <div class="task-left">
            <div class="task-icon">{'🗓️' if is_event else '🗒️'}</div>
            <div class="tk-info">
              <div class="tk-title">{t.get('title','(sem título)')}</div>
              <div class="tk-meta">{head} • Resp.: <b>{t.get('assignee','Ambos')}</b></div>
              <div class="status-badge {t.get('status','todo')}">{STATUS_LABELS.get(t.get('status','todo'),'—')}</div>
              <div class="tk-meta">{(t.get('description') or '').strip()}</div>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        _render_quick_actions(t, key_ns="v_")  # evita colisão com editor
        with st.expander("Editar"):
            _render_edit_inline(t)

    # ==========================
    # HOJE
    # ==========================
    with tab_hoje:
        hoje = date.today()
        items = []
        for t in tasks:
            if t.get("status") == "done":
                continue
            if t.get("type") == "event":
                s = _iso_to_dt(t.get("start_at"))
                if s and s.date() == hoje:
                    items.append(t)
            else:
                d = _iso_to_date(t.get("due_at"))
                if d == hoje:
                    items.append(t)

        if not items:
            st.info("Nada para hoje. Adicione algo acima ✍️")
        else:
            ev = [x for x in items if x.get("type") == "event"]
            tk = [x for x in items if x.get("type") != "event"]
            ev.sort(key=lambda x: _iso_to_dt(x.get("start_at")) or datetime.now())
            tk.sort(key=lambda x: (x.get("priority", "normal") != "important", x.get("title", "")))
            for t in (ev + tk):
                _render_entry(t)

    # ==========================
    # PRÓXIMOS (14 dias)
    # ==========================
    with tab_prox:
        horizon = date.today() + timedelta(days=14)
        future = []
        for t in tasks:
            if t.get("status") == "done":
                continue
            if t.get("type") == "event":
                s = _iso_to_dt(t.get("start_at"))
                if s and (date.today() < s.date() <= horizon):
                    future.append(t)
            else:
                d = _iso_to_date(t.get("due_at"))
                if d and (date.today() < d <= horizon):
                    future.append(t)

        if not future:
            st.info("Sem próximos itens. Ótimo! 😉")
        else:
            agenda = _group_for_agenda(future)
            for day in sorted([d for d in agenda.keys() if d]):
                st.markdown(f"##### {day.strftime('%A, %d/%m').capitalize()}")
                day_items = agenda[day]
                ev = [x for x in day_items if x.get("type") == "event"]
                tk = [x for x in day_items if x.get("type") != "event"]
                ev.sort(key=lambda x: _iso_to_dt(x.get("start_at")) or datetime.now())
                tk.sort(key=lambda x: (x.get("priority", "normal") != "important", x.get("title", "")))
                for t in (ev + tk):
                    _render_entry(t)

    # ==========================
    # CONCLUÍDOS
    # ==========================
    with tab_done:
        done_items = [t for t in tasks if t.get("status") == "done"]
        if not done_items:
            st.info("Nada concluído ainda por aqui.")
        else:
            done_items.sort(
                key=lambda x: x.get("completed_at") or x.get("updated_at") or x.get("created_at") or "",
                reverse=True
            )
            for t in done_items[:50]:
                _render_entry(t)
