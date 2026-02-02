# views/tarefas_view.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import time
import streamlit as st
from datetime import datetime, date, timedelta, time as dtime

from github_db import (
    buscar_tasks, inserir_task, atualizar_task,
    deletar_task,            # fallback
    deletar_tasks_bulk,      # recomendado (1 commit)
    buscar_pessoas
)
from ui_helpers import confirmar_exclusao
from nlp_pt import parse_quick_entry

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
# Helpers de data/hora (tolerante a "Z")
# -------------------------
def _clean_iso(s: str | None) -> str | None:
    if not s:
        return None
    s = str(s)
    return s[:-1] if s.endswith("Z") else s


def _iso_to_date(x):
    try:
        x = _clean_iso(x)
        if not x:
            return None
        if len(x) == 10:
            return date.fromisoformat(x)
        return datetime.fromisoformat(x).date()
    except Exception:
        return None


def _iso_to_dt(x):
    try:
        x = _clean_iso(x)
        return datetime.fromisoformat(x) if x else None
    except Exception:
        return None


def _fmt_date_br(d: date | None) -> str:
    return d.strftime("%d/%m/%Y") if d else "—"


def _fmt_dt_br(dt: datetime | None) -> str:
    return dt.strftime("%d/%m/%Y %H:%M") if dt else "—"


def _task_day(t: dict) -> date | None:
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
    if not tasks:
        return 0, 0, 0, 0
    total = len(tasks)
    abertas = sum(1 for t in tasks if t.get("status") in ("todo", "doing"))
    hoje_qtd = sum(1 for t in tasks if _is_due_today(t) and t.get("status") in ("todo", "doing"))
    atrasadas = sum(1 for t in tasks if _is_overdue(t))
    return total, abertas, hoje_qtd, atrasadas


def _safe_bool(result) -> bool:
    # compat com funções que retornam None
    return bool(result) if isinstance(result, bool) else True


# -------------------------
# Helpers: patch local (evita GET por clique)
# -------------------------
def _apply_local_patch(task_id: int, patch: dict) -> list[dict]:
    backup = list(st.session_state.get("tasks", []))
    new_list = []
    for t in backup:
        try:
            tid = int(t.get("id", -999999))
        except Exception:
            tid = -999999
        if tid == int(task_id):
            tt = dict(t)
            tt.update(patch)
            new_list.append(tt)
        else:
            new_list.append(t)
    st.session_state.tasks = new_list
    return backup


def _commit_patch(task_id: int, patch: dict, backup: list[dict]) -> bool:
    ok = _safe_bool(atualizar_task(int(task_id), patch))
    if not ok:
        st.session_state.tasks = backup
        st.error("Falha ao sincronizar (concorrência). Tente novamente em instantes.")
        return False
    return True


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

    # Sync leve para 2 dispositivos (sem forçar rerun)
    st.session_state.setdefault("_tasks_last_sync", 0.0)

    def _sync_if_old(ttl=30):
        now = time.time()
        last = float(st.session_state.get("_tasks_last_sync", 0.0))
        if now - last > ttl:
            st.session_state.tasks = buscar_tasks()
            st.session_state["_tasks_last_sync"] = now

    _sync_if_old(ttl=30)

    # Botão sync manual
    _, top2 = st.columns([10, 1])
    with top2:
        if st.button("↻", help="Sincronizar com GitHub"):
            st.session_state.tasks = buscar_tasks()
            st.session_state["_tasks_last_sync"] = time.time()
            st.toast("Sincronizado.")

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
    # 1) ADICIONAR (sem piscar): Quick Add em FORM + Detalhado em FORM
    # =========================================================
    st.markdown("### ➕ Adicionar")

    # ---- QUICK ADD: form com clear_on_submit => sem _clear_quick e sem rerun manual ----
    with st.form("form_quick_add", clear_on_submit=True):
        qc1, qc2 = st.columns([4, 1])
        with qc1:
            quick_txt = st.text_input(
                "Entrada rápida",
                placeholder="Ex.: Reunião amanhã 15h / Pagar boleto 12/02 / Comprar leite #casa",
                label_visibility="collapsed",
            )
        with qc2:
            submitted_quick = st.form_submit_button("Adicionar", use_container_width=True)

        if submitted_quick:
            txt = (quick_txt or "").strip()
            if not txt:
                st.warning("Digite algo para adicionar.")
            else:
                try:
                    payload = parse_quick_entry(txt)
                    payload.update({
                        "assignee": "Ambos",
                        "created_at": datetime.utcnow().isoformat() + "Z",
                        "updated_at": None
                    })

                    ok = _safe_bool(inserir_task(payload))
                    if ok:
                        # ✅ atualiza lista uma vez, sem st.rerun()
                        st.session_state.tasks = buscar_tasks()
                        st.session_state["_tasks_last_sync"] = time.time()
                        st.toast(f"✅ Adicionado: {payload.get('title', 'Tarefa')}")
                    else:
                        st.error("Não consegui salvar agora (concorrência). Tente novamente em instantes.")
                except Exception as e:
                    st.error(f"Erro no salvamento: {e}")

    # ---- FORM DETALHADO: checkboxes para data/hora (mais estável que value=None) ----
    with st.expander("➕ Adicionar com detalhes (opcional)", expanded=False):
        with st.form("form_task_full", clear_on_submit=True):
            fc1, fc2, fc3 = st.columns([2, 1, 1])
            title = fc1.text_input("Título", placeholder="O que precisa ser feito?")
            tipo = fc2.selectbox("Tipo", options=["Tarefa", "Evento"], index=0)
            assignee = fc3.selectbox("Responsável", options=PESSOAS, index=0)

            desc = st.text_area("Detalhes", placeholder="Opcional", height=80)

            dc1, dc2, dc3 = st.columns([1, 1, 1])
            status = dc1.selectbox(
                "Status",
                options=STATUS_OPCOES,
                format_func=lambda x: STATUS_LABELS.get(x, x),
                index=0
            )
            priority = dc2.selectbox(
                "Prioridade",
                options=PRIORITY_OPCOES,
                format_func=lambda x: PRIORITY_LABELS.get(x, x),
                index=0
            )
            tags_txt = dc3.text_input("Tags (opcional)", placeholder="#trabalho #casa")

            st.markdown("**Quando?**")
            cc1, cc2, cc3 = st.columns([1, 1, 1])

            use_date = cc1.checkbox("Definir data", value=False)
            chosen_date = cc2.date_input("Data", value=date.today(), disabled=not use_date)
            # Hora só faz sentido se for Evento
            use_time = cc3.checkbox("Definir hora (evento)", value=False, disabled=(tipo != "Evento" or not use_date))
            chosen_time = st.time_input("Hora", value=dtime(9, 0), disabled=(tipo != "Evento" or not use_date or not use_time))

            submitted_full = st.form_submit_button("Salvar")
            if submitted_full:
                if not title.strip():
                    st.error("Informe o título.")
                else:
                    # tags
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

                    # decide type + datas
                    if tipo == "Evento":
                        payload["type"] = "event"
                        if use_date and use_time:
                            payload["start_at"] = datetime.combine(chosen_date, chosen_time).isoformat()
                        elif use_date:
                            # evento sem hora => assume 09:00
                            payload["start_at"] = datetime.combine(chosen_date, dtime(9, 0)).isoformat()
                        else:
                            payload["start_at"] = None
                        payload["due_at"] = None
                    else:
                        payload["type"] = "task"
                        payload["due_at"] = chosen_date.isoformat() if use_date else None
                        payload["start_at"] = None

                    ok = _safe_bool(inserir_task(payload))
                    if ok:
                        st.session_state.tasks = buscar_tasks()
                        st.session_state["_tasks_last_sync"] = time.time()
                        st.toast("✅ Salvo com detalhes!")
                    else:
                        st.error("Falha ao gravar no GitHub (concorrência). Tente novamente.")

    st.divider()

    # =================================
    # 2) Filtros
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
        out = list(items)

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

        def sort_key(t):
            dd = _task_day(t) or date.max
            pr = 0 if t.get("priority") == "important" else 1
            ttl = t.get("title") or ""
            if t.get("type") == "event":
                dt = _iso_to_dt(t.get("start_at")) or datetime.max
                return (dd, dt.time(), pr, ttl.lower())
            return (dd, dtime(23, 59), pr, ttl.lower())

        out.sort(key=sort_key)
        return out

    st.divider()
    tab_hoje, tab_prox, tab_done, tab_all = st.tabs(["Hoje", "Próximos", "Concluídos", "Todas (filtros)"])

    # ========= delete imediato pós-confirmação (mantém confirmação) =========
    def _delete_now(task_id: int):
        task_id = int(task_id)

        # remove local primeiro
        st.session_state.tasks = [t for t in st.session_state.tasks if int(t.get("id", -1)) != task_id]

        ok = _safe_bool(deletar_tasks_bulk([task_id]))
        if not ok:
            ok = _safe_bool(deletar_task(task_id))

        st.session_state.tasks = buscar_tasks()
        st.session_state["_tasks_last_sync"] = time.time()

        if not ok:
            st.warning("Não consegui excluir agora (concorrência). Tente novamente em instantes.")

    def _render_quick_actions(t: dict, key_ns: str):
        tid = int(t.get("id", 0))
        c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 1, 1])

        with c1:
            if t.get("status") != "done":
                if st.button("✔ Finalizar", key=f"{key_ns}_done_{tid}"):
                    patch = {"status": "done", "completed_at": datetime.utcnow().isoformat() + "Z"}
                    backup = _apply_local_patch(tid, patch)
                    _commit_patch(tid, patch, backup)

        with c2:
            if st.button("⏳ Não Iniciado", key=f"{key_ns}_todo_{tid}"):
                patch = {"status": "todo", "updated_at": datetime.utcnow().isoformat() + "Z"}
                backup = _apply_local_patch(tid, patch)
                _commit_patch(tid, patch, backup)

        with c3:
            if st.button("🔄 Em Progresso", key=f"{key_ns}_doing_{tid}"):
                patch = {"status": "doing", "updated_at": datetime.utcnow().isoformat() + "Z"}
                backup = _apply_local_patch(tid, patch)
                _commit_patch(tid, patch, backup)

        with c4:
            imp = (t.get("priority") == "important")
            lab = "⭐ Importante" if imp else "⭐ Marcar"
            if st.button(lab, key=f"{key_ns}_imp_{tid}"):
                patch = {"priority": ("normal" if imp else "important"), "updated_at": datetime.utcnow().isoformat() + "Z"}
                backup = _apply_local_patch(tid, patch)
                _commit_patch(tid, patch, backup)

        with c5:
            st.markdown('<div class="btn-danger">', unsafe_allow_html=True)
            if st.button("Excluir", key=f"{key_ns}_del_{tid}"):
                confirmar_exclusao(
                    f"dlg_{key_ns}_{tid}",
                    "Confirmar exclusão",
                    lambda tid_=tid: _delete_now(tid_)
                )
            st.markdown("</div>", unsafe_allow_html=True)

        # reagendar rápido
        r1, r2, r3 = st.columns([1, 1, 1])
        with r1:
            if st.button("Amanhã", key=f"{key_ns}_tmw_{tid}"):
                if t.get("type") == "event":
                    s = _iso_to_dt(t.get("start_at")) or datetime.now()
                    ndt = datetime.combine(date.today() + timedelta(days=1), s.time())
                    patch = {"start_at": ndt.isoformat(), "updated_at": datetime.utcnow().isoformat() + "Z"}
                else:
                    patch = {"due_at": (date.today() + timedelta(days=1)).isoformat(), "updated_at": datetime.utcnow().isoformat() + "Z"}
                backup = _apply_local_patch(tid, patch)
                _commit_patch(tid, patch, backup)

        with r2:
            if st.button("+1d", key=f"{key_ns}_p1_{tid}"):
                if t.get("type") == "event":
                    s = _iso_to_dt(t.get("start_at")) or datetime.now()
                    patch = {"start_at": (s + timedelta(days=1)).isoformat(), "updated_at": datetime.utcnow().isoformat() + "Z"}
                else:
                    d = _iso_to_date(t.get("due_at")) or date.today()
                    patch = {"due_at": (d + timedelta(days=1)).isoformat(), "updated_at": datetime.utcnow().isoformat() + "Z"}
                backup = _apply_local_patch(tid, patch)
                _commit_patch(tid, patch, backup)

        with r3:
            if st.button("Sem data", key=f"{key_ns}_nodate_{tid}"):
                if t.get("type") == "event":
                    patch = {"start_at": None, "type": "task", "due_at": None, "updated_at": datetime.utcnow().isoformat() + "Z"}
                else:
                    patch = {"due_at": None, "updated_at": datetime.utcnow().isoformat() + "Z"}
                backup = _apply_local_patch(tid, patch)
                _commit_patch(tid, patch, backup)

    def _render_editor(t: dict, key_ns: str):
        tid = int(t.get("id", 0))
        with st.expander("Editar"):
            ec1, ec2, ec3 = st.columns([2, 1, 1])
            nt = ec1.text_input("Título", value=t.get("title", ""), key=f"{key_ns}_et_{tid}")
            nass = ec2.selectbox(
                "Responsável",
                options=PESSOAS,
                index=PESSOAS.index(t.get("assignee", "Ambos")) if t.get("assignee", "Ambos") in PESSOAS else 0,
                key=f"{key_ns}_ea_{tid}"
            )
            nstatus = ec3.selectbox(
                "Status",
                options=STATUS_OPCOES,
                format_func=lambda x: STATUS_LABELS.get(x, x),
                index=STATUS_OPCOES.index(t.get("status", "todo")) if t.get("status", "todo") in STATUS_OPCOES else 0,
                key=f"{key_ns}_es_{tid}"
            )

            nd = st.text_area("Detalhes", value=t.get("description", "") or "", height=90, key=f"{key_ns}_ed_{tid}")

            dc1, dc2, dc3 = st.columns([1, 1, 1])
            tipo_atual = "Evento" if t.get("type") == "event" else "Tarefa"
            ntipo = dc1.selectbox("Tipo", options=["Tarefa", "Evento"], index=0 if tipo_atual == "Tarefa" else 1, key=f"{key_ns}_tp_{tid}")
            cur_date = _task_day(t)
            cur_dt = _iso_to_dt(t.get("start_at")) if t.get("type") == "event" else None
            ndt = dc2.date_input("Data", value=(cur_date or date.today()), key=f"{key_ns}_d_{tid}")
            nth = dc3.time_input("Hora (se evento)", value=((cur_dt.time()) if cur_dt else dtime(9, 0)), key=f"{key_ns}_h_{tid}")

            pc1, pc2 = st.columns([1, 1])
            nprio = pc1.selectbox(
                "Prioridade",
                options=PRIORITY_OPCOES,
                format_func=lambda x: PRIORITY_LABELS.get(x, x),
                index=PRIORITY_OPCOES.index(t.get("priority", "normal")) if t.get("priority", "normal") in PRIORITY_OPCOES else 0,
                key=f"{key_ns}_pr_{tid}"
            )
            ntags = pc2.text_input("Tags", value=" ".join([f"#{x}" for x in (t.get("tags") or [])]),
                                   placeholder="#trabalho #casa", key=f"{key_ns}_tg_{tid}")

            if st.button("Salvar alterações", key=f"{key_ns}_save_{tid}"):
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

                if ntipo == "Evento":
                    patch["type"] = "event"
                    patch["start_at"] = datetime.combine(ndt, nth).isoformat()
                    patch["due_at"] = None
                else:
                    patch["type"] = "task"
                    patch["start_at"] = None
                    patch["due_at"] = ndt.isoformat() if ndt else None

                backup = _apply_local_patch(tid, patch)
                _commit_patch(tid, patch, backup)
                st.toast("✅ Atualizado!")

    def _render_card(t: dict, key_ns: str):
        is_event = (t.get("type") == "event")
        day = _task_day(t)
        dt = _iso_to_dt(t.get("start_at")) if is_event else None
        status = t.get("status", "todo")
        pr = t.get("priority", "normal")

        when_txt = f"🗓️ {_fmt_dt_br(dt)}" if is_event else f"📝 {_fmt_date_br(day)}"
        flag = ""
        if _is_overdue(t):
            diff = (date.today() - (day or date.today())).days
            flag = f" • 🔴 Atrasada há {diff}d"
        elif _is_due_today(t) and status in ("todo", "doing"):
            flag = " • 🟡 Vence hoje"

        tags = t.get("tags") or []
        tag_txt = (" • " + " ".join([f"#{x}" for x in tags[:6]])) if isinstance(tags, list) and tags else ""
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

    def _render_list(items: list[dict], key_ns_prefix: str):
        if not items:
            st.info("Nada por aqui.")
            return
        for t in items:
            _render_card(t, key_ns=f"{key_ns_prefix}_{t.get('id')}")

    # Abas
    with tab_hoje:
        hoje_items = [t for t in st.session_state.tasks if t.get("status") != "done" and _task_day(t) == date.today()]
        _render_list(_apply_filters(hoje_items), "hoje")

    with tab_prox:
        horizon = date.today() + timedelta(days=14)
        prox_items = []
        for t in st.session_state.tasks:
            if t.get("status") == "done":
                continue
            d = _task_day(t)
            if d and date.today() < d <= horizon:
                prox_items.append(t)
        _render_list(_apply_filters(prox_items), "prox")

    with tab_done:
        done_items = [t for t in st.session_state.tasks if t.get("status") == "done"]
        done_items = _apply_filters(done_items)
        done_items.sort(key=lambda x: x.get("completed_at") or x.get("updated_at") or x.get("created_at") or "", reverse=True)
        _render_list(done_items[:80], "done")

    with tab_all:
        _render_list(_apply_filters(list(st.session_state.tasks)), "all")
