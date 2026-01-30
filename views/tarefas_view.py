# views/tarefas_view.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import time
import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta, time as dtime

from github_db import buscar_tasks, inserir_task, atualizar_task, deletar_task, buscar_pessoas
from ui_helpers import confirmar_exclusao
from nlp_pt import parse_quick_entry

# Status internos
STATUS_OPCOES = ["todo", "doing", "done", "cancelled"]
STATUS_LABELS = {
    "todo": "Não Iniciado",
    "doing": "Em Progresso",
    "done": "Finalizado",
    "cancelled": "Cancelado"
}

PRIORITY_OPCOES = ["normal", "important"]
PRIORITY_LABELS = {"normal": "Normal", "important": "Importante"}


# -------------------------
# Helpers de data/hora
# -------------------------
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


def _fmt_date_br(d: date | None) -> str:
    return d.strftime("%d/%m/%Y") if d else "—"


def _fmt_dt_br(dt: datetime | None) -> str:
    return dt.strftime("%d/%m/%Y %H:%M") if dt else "—"


def _task_day(t: dict) -> date | None:
    """Dia de referência: evento por start_at, tarefa por due_at."""
    if t.get("type") == "event":
        s = _iso_to_dt(t.get("start_at"))
        return s.date() if s else None
    return _iso_to_date(t.get("due_at"))


def _is_due_today(t: dict) -> bool:
    d = _task_day(t)
    return bool(d and d == date.today())


def _is_overdue(t: dict) -> bool:
    d = _task_day(t)
    return bool(d and d < date.today() and t.get("status") in ("todo", "doing"))


def _progress_metrics(tasks: list[dict]):
    """Total, abertas, hoje, atrasadas."""
    if not tasks:
        return 0, 0, 0, 0
    total = len(tasks)
    abertas = sum(1 for t in tasks if t.get("status") in ("todo", "doing"))
    hoje_qtd = sum(1 for t in tasks if _is_due_today(t) and t.get("status") in ("todo", "doing"))
    atrasadas = sum(1 for t in tasks if _is_overdue(t))
    return total, abertas, hoje_qtd, atrasadas


def _safe_bool_insert(result) -> bool:
    """Compat: se inserir_task retornar bool, usa; se retornar None, assume True e deixa o reload confirmar."""
    return bool(result) if isinstance(result, bool) else True


# -------------------------
# Render
# -------------------------
def render_tarefas():
    st.markdown(
        """
        <div class="header-container">
          <div class="main-title">🗓️ Tarefas</div>
          <div class="slogan">Entrada inteligente + controle total (quando você quiser)</div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # ========= Estado base =========
    if "tasks" not in st.session_state:
        st.session_state.tasks = buscar_tasks()

    if "pessoas" not in st.session_state or not st.session_state.pessoas:
        st.session_state.pessoas = buscar_pessoas()

    PESSOAS = st.session_state.pessoas or ["Guilherme", "Alynne", "Ambos"]

    # Flags de controle
    st.session_state.setdefault("_clear_quick", False)
    st.session_state.setdefault("_busy_add", False)
    st.session_state.setdefault("_last_add_text", "")
    st.session_state.setdefault("_last_add_ts", 0.0)

    # ✅ Limpa o input antes do widget existir (evita “corrida”)
    if st.session_state.get("_clear_quick"):
        if "quick_in" in st.session_state:
            del st.session_state["quick_in"]
        st.session_state["_clear_quick"] = False

    tasks = st.session_state.tasks

    # ========= Métricas =========
    total, abertas, hoje_qtd, atrasadas = _progress_metrics(tasks)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total", str(total))
    m2.metric("Abertas", str(abertas))
    m3.metric("Para Hoje", str(hoje_qtd))
    m4.metric("Atrasadas", str(atrasadas))

    st.divider()

    # =========================================================
    # 1) ADICIONAR: Entrada inteligente + Form opcional completo
    # =========================================================
    st.markdown("### ➕ Adicionar")

    def _add_quick_from_text(txt: str):
        """Entrada inteligente robusta: debounce + busy + rerun só no sucesso."""
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
                "created_at": datetime.utcnow().isoformat() + "Z",
                "updated_at": None
            })
            ok = _safe_bool_insert(inserir_task(payload))

            # Recarrega para confirmar
            st.session_state.tasks = buscar_tasks()

            if ok:
                st.session_state["_last_add_text"] = txt
                st.session_state["_last_add_ts"] = now_ts
                st.session_state["_clear_quick"] = True
                st.toast(f"✅ Adicionado: {payload.get('title')}")
                st.rerun()
            else:
                st.error("Não consegui salvar agora (concorrência/sincronização). Tente novamente em 2s.")
        except Exception as e:
            st.error(f"Erro no salvamento: {e}")
        finally:
            st.session_state["_busy_add"] = False

    def _on_enter_add():
        _add_quick_from_text(st.session_state.get("quick_in"))

    c1, c2 = st.columns([4, 1])
    with c1:
        st.text_input(
            "Entrada rápida",
            placeholder="Ex.: Reunião amanhã 15h / Pagar boleto 12/02 / Comprar leite #casa",
            label_visibility="collapsed",
            key="quick_in",
            on_change=_on_enter_add
        )
    with c2:
        if st.button("Adicionar", use_container_width=True):
            _add_quick_from_text(st.session_state.get("quick_in"))

    # ---- Form completo opcional (sem perder suas funções antigas) ----
    with st.expander("➕ Adicionar com detalhes (opcional)"):
        with st.form("form_task_full", clear_on_submit=True):
            fc1, fc2, fc3 = st.columns([2, 1, 1])

            title = fc1.text_input("Título", placeholder="O que precisa ser feito?")
            tipo = fc2.selectbox("Tipo", options=["Tarefa", "Evento"], index=0)
            assignee = fc3.selectbox("Responsável", options=PESSOAS, index=0)

            desc = st.text_area("Detalhes", placeholder="Opcional", height=80)

            dc1, dc2, dc3 = st.columns([1, 1, 1])
            dsel = dc1.date_input("Data", value=None)
            tsel = dc2.time_input("Hora (opcional)", value=None)
            status = dc3.selectbox("Status", options=STATUS_OPCOES, format_func=lambda x: STATUS_LABELS.get(x, x), index=0)

            pc1, pc2 = st.columns([1, 1])
            priority = pc1.selectbox("Prioridade", options=PRIORITY_OPCOES, format_func=lambda x: PRIORITY_LABELS.get(x, x), index=0)
            tags_txt = pc2.text_input("Tags (opcional)", placeholder="#trabalho #casa")

            submitted = st.form_submit_button("Salvar")
            if submitted:
                if not title.strip():
                    st.error("Informe o título.")
                else:
                    tags = []
                    for part in (tags_txt or "").split():
                        if part.startswith("#") and len(part) > 1:
                            tags.append(part[1:].lower())

                    payload = {
                        "title": title.strip(),
                        "description": (desc or "").strip(),
                        "assignee": assignee,
                        "status": status,
                        "priority": priority,
                        "tags": tags,
                        "created_at": datetime.utcnow().isoformat() + "Z",
                        "updated_at": None
                    }

                    # Decide tarefa vs evento + data/hora
                    if tipo == "Evento" and dsel and tsel:
                        payload["type"] = "event"
                        payload["start_at"] = datetime.combine(dsel, tsel).isoformat()
                        payload["due_at"] = None
                    else:
                        payload["type"] = "task"
                        payload["due_at"] = dsel.isoformat() if dsel else None
                        payload["start_at"] = None

                    ok = _safe_bool_insert(inserir_task(payload))
                    st.session_state.tasks = buscar_tasks()
                    if ok:
                        st.toast("✅ Salvo!")
                        st.rerun()
                    else:
                        st.error("Falha ao gravar no GitHub. Tente novamente.")

    st.divider()

    # =================================
    # 2) Filtros (como no modelo antigo)
    # =================================
    f1, f2, f3 = st.columns([1.5, 1.5, 1])
    status_sel = f1.multiselect(
        "Status",
        STATUS_OPCOES,
        default=["todo", "doing"],
        format_func=lambda x: STATUS_LABELS.get(x, x),
        key="flt_status"
    )
    resp_sel = f2.selectbox("Responsável", options=["Todos"] + PESSOAS, index=0, key="flt_resp")
    janela = f3.selectbox("Janela", options=["Todos", "Hoje", "Próximos 7 dias", "Próximos 30 dias"], index=0, key="flt_janela")

    def _apply_filters(items: list[dict]):
        out = items
        if status_sel:
            out = [t for t in out if t.get("status") in status_sel]
        if resp_sel != "Todos":
            out = [t for t in out if t.get("assignee") == resp_sel]

        hoje = date.today()
        if janela == "Hoje":
            out = [t for t in out if _task_day(t) == hoje]
        elif janela == "Próximos 7 dias":
            lim = hoje + timedelta(days=7)
            out = [t for t in out if _task_day(t) and hoje <= _task_day(t) <= lim]
        elif janela == "Próximos 30 dias":
            lim = hoje + timedelta(days=30)
            out = [t for t in out if _task_day(t) and hoje <= _task_day(t) <= lim]

        # ordena: data/hora, prioridade, título
        def sort_key(t):
            dd = _task_day(t) or date.max
            pr = 0 if t.get("priority") == "important" else 1
            ttl = t.get("title") or ""
            # eventos por hora
            if t.get("type") == "event":
                dt = _iso_to_dt(t.get("start_at")) or datetime.max
                return (dd, dt.time(), pr, ttl.lower())
            return (dd, dtime(23, 59), pr, ttl.lower())

        out.sort(key=sort_key)
        return out

    st.divider()

    # ==========================
    # 3) Abas principais
    # ==========================
    tab_hoje, tab_prox, tab_done, tab_all = st.tabs(["Hoje", "Próximos", "Concluídos", "Todas (filtros)"])

    # ==========================
    # Render de card + ações
    # ==========================
    def _render_quick_actions(t: dict, key_ns: str):
        """Ações rápidas no cartão (com key namespace)."""
        c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 1, 1])

        # Finalizar
        with c1:
            if t.get("status") != "done":
                if st.button("✔ Finalizar", key=f"{key_ns}_done_{t['id']}"):
                    atualizar_task(int(t["id"]), {"status": "done", "completed_at": datetime.utcnow().isoformat() + "Z"})
                    st.session_state.tasks = buscar_tasks()
                    st.rerun()

        # Voltar para todo / doing
        with c2:
            if st.button("⏳ Não Iniciado", key=f"{key_ns}_todo_{t['id']}"):
                atualizar_task(int(t["id"]), {"status": "todo"})
                st.session_state.tasks = buscar_tasks()
                st.rerun()

        with c3:
            if st.button("🔄 Em Progresso", key=f"{key_ns}_doing_{t['id']}"):
                atualizar_task(int(t["id"]), {"status": "doing"})
                st.session_state.tasks = buscar_tasks()
                st.rerun()

        # Importante
        with c4:
            imp = (t.get("priority") == "important")
            lab = "⭐ Importante" if imp else "⭐ Marcar"
            if st.button(lab, key=f"{key_ns}_imp_{t['id']}"):
                atualizar_task(int(t["id"]), {"priority": ("normal" if imp else "important")})
                st.session_state.tasks = buscar_tasks()
                st.rerun()

        # Excluir
        with c5:
            st.markdown('<div class="btn-danger">', unsafe_allow_html=True)
            if st.button("Excluir", key=f"{key_ns}_del_{t['id']}"):
                confirmar_exclusao(
                    f"dlg_{key_ns}_{t['id']}",
                    "Confirmar exclusão",
                    lambda: deletar_task(int(t["id"]))
                )
            st.markdown("</div>", unsafe_allow_html=True)

        # Reagendar rápido (sem modais)
        r1, r2, r3 = st.columns([1, 1, 1])
        with r1:
            if st.button("Amanhã", key=f"{key_ns}_tmw_{t['id']}"):
                if t.get("type") == "event":
                    s = _iso_to_dt(t.get("start_at")) or datetime.now()
                    ndt = datetime.combine(date.today() + timedelta(days=1), s.time())
                    atualizar_task(int(t["id"]), {"start_at": ndt.isoformat()})
                else:
                    atualizar_task(int(t["id"]), {"due_at": (date.today() + timedelta(days=1)).isoformat()})
                st.session_state.tasks = buscar_tasks()
                st.rerun()

        with r2:
            if st.button("+1d", key=f"{key_ns}_p1_{t['id']}"):
                if t.get("type") == "event":
                    s = _iso_to_dt(t.get("start_at")) or datetime.now()
                    atualizar_task(int(t["id"]), {"start_at": (s + timedelta(days=1)).isoformat()})
                else:
                    d = _iso_to_date(t.get("due_at")) or date.today()
                    atualizar_task(int(t["id"]), {"due_at": (d + timedelta(days=1)).isoformat()})
                st.session_state.tasks = buscar_tasks()
                st.rerun()

        with r3:
            if st.button("Sem data", key=f"{key_ns}_nodate_{t['id']}"):
                if t.get("type") == "event":
                    atualizar_task(int(t["id"]), {"start_at": None, "type": "task"})
                else:
                    atualizar_task(int(t["id"]), {"due_at": None})
                st.session_state.tasks = buscar_tasks()
                st.rerun()

    def _render_editor(t: dict, key_ns: str):
        """Editor completo (sem perder funções)."""
        with st.expander("Editar"):
            ec1, ec2, ec3 = st.columns([2, 1, 1])
            nt = ec1.text_input("Título", value=t.get("title", ""), key=f"{key_ns}_et_{t['id']}")
            nass = ec2.selectbox("Responsável", options=PESSOAS,
                                 index=PESSOAS.index(t.get("assignee", "Ambos")) if t.get("assignee", "Ambos") in PESSOAS else 0,
                                 key=f"{key_ns}_ea_{t['id']}")
            nstatus = ec3.selectbox("Status", options=STATUS_OPCOES,
                                    format_func=lambda x: STATUS_LABELS.get(x, x),
                                    index=STATUS_OPCOES.index(t.get("status", "todo")) if t.get("status", "todo") in STATUS_OPCOES else 0,
                                    key=f"{key_ns}_es_{t['id']}")

            nd = st.text_area("Detalhes", value=t.get("description", "") or "", height=90, key=f"{key_ns}_ed_{t['id']}")

            dc1, dc2, dc3 = st.columns([1, 1, 1])
            # Data/hora conforme tipo
            tipo = "Evento" if t.get("type") == "event" else "Tarefa"
            ntipo = dc1.selectbox("Tipo", options=["Tarefa", "Evento"], index=0 if tipo == "Tarefa" else 1, key=f"{key_ns}_tp_{t['id']}")

            # data/hora atuais
            cur_date = _task_day(t)
            cur_dt = _iso_to_dt(t.get("start_at")) if t.get("type") == "event" else None
            ndt = dc2.date_input("Data", value=cur_date, key=f"{key_ns}_d_{t['id']}")
            nth = dc3.time_input("Hora (se evento)", value=(cur_dt.time() if cur_dt else None), key=f"{key_ns}_h_{t['id']}")

            pc1, pc2 = st.columns([1, 1])
            nprio = pc1.selectbox("Prioridade", options=PRIORITY_OPCOES,
                                  format_func=lambda x: PRIORITY_LABELS.get(x, x),
                                  index=PRIORITY_OPCOES.index(t.get("priority", "normal")) if t.get("priority", "normal") in PRIORITY_OPCOES else 0,
                                  key=f"{key_ns}_pr_{t['id']}")
            ntags = pc2.text_input("Tags", value=" ".join([f"#{x}" for x in (t.get("tags") or [])]),
                                   placeholder="#trabalho #casa", key=f"{key_ns}_tg_{t['id']}")

            if st.button("Salvar alterações", key=f"{key_ns}_save_{t['id']}"):
                tags = []
                for part in (ntags or "").split():
                    if part.startswith("#") and len(part) > 1:
                        tags.append(part[1:].lower())

                patch = {
                    "title": (nt or "").strip(),
                    "description": (nd or "").strip(),
                    "assignee": nass,
                    "status": nstatus,
                    "priority": nprio,
                    "tags": tags,
                    "updated_at": datetime.utcnow().isoformat() + "Z"
                }

                # aplica data/hora conforme tipo escolhido
                if ntipo == "Evento":
                    patch["type"] = "event"
                    if ndt and nth:
                        patch["start_at"] = datetime.combine(ndt, nth).isoformat()
                        patch["due_at"] = None
                    else:
                        # evento sem data/hora vira tarefa sem data
                        patch["type"] = "task"
                        patch["start_at"] = None
                        patch["due_at"] = None
                else:
                    patch["type"] = "task"
                    patch["start_at"] = None
                    patch["due_at"] = ndt.isoformat() if ndt else None

                atualizar_task(int(t["id"]), patch)
                st.toast("✅ Atualizado!")
                st.session_state.tasks = buscar_tasks()
                st.rerun()

    def _render_card(t: dict, key_ns: str):
        is_event = (t.get("type") == "event")
        day = _task_day(t)
        dt = _iso_to_dt(t.get("start_at")) if is_event else None
        status = t.get("status", "todo")
        pr = t.get("priority", "normal")

        # texto data
        if is_event:
            when_txt = f"🗓️ {_fmt_dt_br(dt)}"
        else:
            when_txt = f"📝 {_fmt_date_br(day)}"

        # atraso / hoje
        flag = ""
        if _is_overdue(t):
            diff = (date.today() - (day or date.today())).days
            flag = f" • 🔴 Atrasada há {diff}d"
        elif _is_due_today(t) and status in ("todo", "doing"):
            flag = " • 🟡 Vence hoje"

        # tags
        tags = t.get("tags") or []
        tag_txt = ""
        if isinstance(tags, list) and tags:
            tag_txt = " • " + " ".join([f"#{x}" for x in tags[:6]])

        # prioridade
        pr_txt = " • ⭐ Importante" if pr == "important" else ""

        st.markdown(f"""
        <div class="task-card">
          <div class="task-left">
            <div class="task-icon">{'🗓️' if is_event else '🗒️'}</div>
            <div class="tk-info">
              <div class="tk-title">{t.get('title','(sem título)')}</div>
              <div class="tk-meta">{when_txt} • Resp.: <b>{t.get('assignee','Ambos')}</b>{flag}{pr_txt}{tag_txt}</div>
              <div class="status-badge {status}">{STATUS_LABELS.get(status,status)}</div>
              <div class="tk-meta">{(t.get('description') or '').strip()}</div>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        _render_quick_actions(t, key_ns=key_ns)
        _render_editor(t, key_ns=key_ns)

    # ==========================
    # 4) Conteúdos das abas
    # ==========================
    def _render_list(items: list[dict], key_ns_prefix: str):
        if not items:
            st.info("Nada por aqui.")
            return
        for t in items:
            _render_card(t, key_ns=f"{key_ns_prefix}_{t.get('id')}")

    with tab_hoje:
        hoje_items = [t for t in tasks if t.get("status") != "done" and _task_day(t) == date.today()]
        hoje_items = _apply_filters(hoje_items)
        _render_list(hoje_items, "hoje")

    with tab_prox:
        horizon = date.today() + timedelta(days=14)
        prox_items = []
        for t in tasks:
            if t.get("status") == "done":
                continue
            d = _task_day(t)
            if d and date.today() < d <= horizon:
                prox_items.append(t)
        prox_items = _apply_filters(prox_items)
        _render_list(prox_items, "prox")

    with tab_done:
        done_items = [t for t in tasks if t.get("status") == "done"]
        done_items = _apply_filters(done_items)
        # mais recentes primeiro
        done_items.sort(key=lambda x: x.get("completed_at") or x.get("updated_at") or x.get("created_at") or "", reverse=True)
        _render_list(done_items[:80], "done")

    with tab_all:
        all_items = _apply_filters(list(tasks))
        _render_list(all_items, "all")
