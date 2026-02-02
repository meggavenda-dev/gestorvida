# views/tarefas_view.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import time
import streamlit as st
from datetime import datetime, date, timedelta, time as dtime

from github_db import (
    buscar_tasks, inserir_task, atualizar_task,
    deletar_task,  # mantido (fallback)
    deletar_tasks_bulk,  # ✅ novo (cole no github_db.py conforme abaixo)
    buscar_pessoas
)
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
        # aceita YYYY-MM-DD
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


def _safe_bool(result) -> bool:
    """Compat: se a função retornar bool, usa; se retornar None, assume True e deixa sync confirmar."""
    return bool(result) if isinstance(result, bool) else True


# -------------------------
# Helpers de UX/consistência (UI otimista + rollback)
# -------------------------
def _prepend_local_task(payload: dict) -> int:
    """Cria uma tarefa local temporária (id negativo) e coloca no topo."""
    temp_id = -int(time.time() * 1000)
    tmp = dict(payload)
    tmp["id"] = temp_id
    tmp.setdefault("status", "todo")
    tmp.setdefault("priority", "normal")
    tmp.setdefault("type", "task")
    tmp.setdefault("tags", [])
    st.session_state.tasks = st.session_state.get("tasks", [])
    st.session_state.tasks = [tmp] + st.session_state.tasks
    return temp_id


def _rollback_local_task(temp_id: int):
    st.session_state.tasks = [t for t in st.session_state.tasks if int(t.get("id", 0)) != int(temp_id)]


def _apply_local_patch(task_id: int, patch: dict) -> list[dict]:
    """Aplica patch localmente e retorna backup para rollback."""
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

    # Flags de controle
    st.session_state.setdefault("_clear_quick", False)
    st.session_state.setdefault("_busy_add", False)
    st.session_state.setdefault("_last_add_text", "")
    st.session_state.setdefault("_last_add_ts", 0.0)

    # Sync/concorrência
    st.session_state.setdefault("_tasks_last_sync", 0.0)
    st.session_state.setdefault("_pending_deletes", [])  # lista de ids (int)

    # ✅ Sync TTL (bom para 2 dispositivos)
    def _sync_if_old(ttl=30):
        now = time.time()
        last = float(st.session_state.get("_tasks_last_sync", 0.0))
        if now - last > ttl:
            st.session_state.tasks = buscar_tasks()
            st.session_state["_tasks_last_sync"] = now

    _sync_if_old(ttl=30)

    # ✅ Limpa o input antes do widget existir (evita “corrida”)
    if st.session_state.get("_clear_quick"):
        if "quick_in" in st.session_state:
            del st.session_state["quick_in"]
        st.session_state["_clear_quick"] = False

    # ========= Barra superior: sincronizar =========
    top1, top2 = st.columns([10, 1])
    with top2:
        if st.button("↻", help="Sincronizar com GitHub"):
            st.session_state.tasks = buscar_tasks()
            st.session_state["_tasks_last_sync"] = time.time()
            st.toast("Sincronizado.")
            st.rerun()

    # ========= Processa exclusões pendentes (BULK) =========
    if st.session_state.get("_pending_deletes"):
        pend = list(dict.fromkeys(st.session_state["_pending_deletes"]))  # unique mantendo ordem
        st.session_state["_pending_deletes"] = []  # limpa já (evita duplicar)

        with st.spinner(f"Sincronizando exclusão ({len(pend)})..."):
            ok = _safe_bool(deletar_tasks_bulk([int(x) for x in pend]))

            # fallback: se bulk falhar, tenta individual (melhor do que perder operação)
            if not ok:
                failures = []
                for tid in pend:
                    ok2 = _safe_bool(deletar_task(int(tid)))
                    if not ok2:
                        failures.append(tid)
                if failures:
                    st.warning(f"Algumas exclusões falharam por concorrência: {failures}. Tente novamente em instantes.")

        # Recarrega estado real uma vez
        st.session_state.tasks = buscar_tasks()
        st.session_state["_tasks_last_sync"] = time.time()
        st.toast("🗑️ Exclusões sincronizadas.")

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

    def _add_from_text(txt: str):
        """Entrada inteligente robusta: debounce + busy + UI otimista + sync."""
        txt = (txt or "").strip()
        if not txt:
            return

        now_ts = time.time()
        if txt == st.session_state.get("_last_add_text") and (now_ts - st.session_state.get("_last_add_ts", 0.0)) < 1.5:
            return
        if st.session_state.get("_busy_add"):
            return

        st.session_state["_busy_add"] = True
        temp_id = None
        try:
            payload = parse_quick_entry(txt)
            payload.update({
                "assignee": "Ambos",
                "created_at": datetime.utcnow().isoformat() + "Z",
                "updated_at": None
            })

            # ✅ UI instantânea
            temp_id = _prepend_local_task(payload)
            st.toast(f"✅ Adicionando: {payload.get('title', 'Tarefa')}")

            # ✅ Persistência
            ok = _safe_bool(inserir_task(payload))
            if ok:
                # sincroniza para obter ID real
                st.session_state.tasks = buscar_tasks()
                st.session_state["_tasks_last_sync"] = time.time()

                st.session_state["_last_add_text"] = txt
                st.session_state["_last_add_ts"] = now_ts
                st.session_state["_clear_quick"] = True
                st.toast("✅ Salvo.")
                st.rerun()
            else:
                if temp_id is not None:
                    _rollback_local_task(temp_id)
                st.error("Não consegui salvar agora (concorrência/sincronização). Tente novamente em 2s.")

        except Exception as e:
            if temp_id is not None:
                _rollback_local_task(temp_id)
            st.error(f"Erro no salvamento: {e}")
        finally:
            st.session_state["_busy_add"] = False

    def _on_enter_add():
        _add_from_text(st.session_state.get("quick_in"))

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
            _add_from_text(st.session_state.get("quick_in"))

    # ---- Form completo opcional ----
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
            status = dc3.selectbox(
                "Status",
                options=STATUS_OPCOES,
                format_func=lambda x: STATUS_LABELS.get(x, x),
                index=0
            )

            pc1, pc2 = st.columns([1, 1])
            priority = pc1.selectbox(
                "Prioridade",
                options=PRIORITY_OPCOES,
                format_func=lambda x: PRIORITY_LABELS.get(x, x),
                index=0
            )
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

                    if tipo == "Evento" and dsel and tsel:
                        payload["type"] = "event"
                        payload["start_at"] = datetime.combine(dsel, tsel).isoformat()
                        payload["due_at"] = None
                    else:
                        payload["type"] = "task"
                        payload["due_at"] = dsel.isoformat() if dsel else None
                        payload["start_at"] = None

                    # UI otimista
                    temp_id = _prepend_local_task(payload)
                    ok = _safe_bool(inserir_task(payload))
                    if ok:
                        st.session_state.tasks = buscar_tasks()
                        st.session_state["_tasks_last_sync"] = time.time()
                        st.toast("✅ Salvo!")
                        st.rerun()
                    else:
                        _rollback_local_task(temp_id)
                        st.error("Falha ao gravar no GitHub. Tente novamente.")

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

        # ordena: data/hora, prioridade, título
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

    # ==========================
    # 3) Abas principais
    # ==========================
    tab_hoje, tab_prox, tab_done, tab_all = st.tabs(["Hoje", "Próximos", "Concluídos", "Todas (filtros)"])

    # ==========================
    # Render de card + ações
    # ==========================
    def _queue_delete(task_id: int):
        """Remove do cache AGORA e coloca em fila para sincronizar com GitHub depois."""
        task_id = int(task_id)
        st.session_state.tasks = [
            x for x in st.session_state.tasks
            if int(x.get("id", -1)) != task_id
        ]
        if task_id not in st.session_state["_pending_deletes"]:
            st.session_state["_pending_deletes"].append(task_id)

    def _render_quick_actions(t: dict, key_ns: str):
        """Ações rápidas no cartão (sem GET por clique)."""
        tid = int(t.get("id", 0))

        # Se ainda estiver com id temporário, bloqueia ações (evita inconsistência)
        if tid < 0:
            st.caption("⏳ Sincronizando…")
            return

        c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 1, 1])

        # Finalizar
        with c1:
            if t.get("status") != "done":
                if st.button("✔ Finalizar", key=f"{key_ns}_done_{tid}"):
                    patch = {"status": "done", "completed_at": datetime.utcnow().isoformat() + "Z"}
                    backup = _apply_local_patch(tid, patch)
                    ok = _commit_patch(tid, patch, backup)
                    if ok:
                        st.toast("Concluída.")
                    st.rerun()

        # Voltar para todo
        with c2:
            if st.button("⏳ Não Iniciado", key=f"{key_ns}_todo_{tid}"):
                patch = {"status": "todo", "updated_at": datetime.utcnow().isoformat() + "Z"}
                backup = _apply_local_patch(tid, patch)
                _commit_patch(tid, patch, backup)
                st.rerun()

        # Em progresso
        with c3:
            if st.button("🔄 Em Progresso", key=f"{key_ns}_doing_{tid}"):
                patch = {"status": "doing", "updated_at": datetime.utcnow().isoformat() + "Z"}
                backup = _apply_local_patch(tid, patch)
                _commit_patch(tid, patch, backup)
                st.rerun()

        # Importante
        with c4:
            imp = (t.get("priority") == "important")
            lab = "⭐ Importante" if imp else "⭐ Marcar"
            if st.button(lab, key=f"{key_ns}_imp_{tid}"):
                patch = {"priority": ("normal" if imp else "important"), "updated_at": datetime.utcnow().isoformat() + "Z"}
                backup = _apply_local_patch(tid, patch)
                _commit_patch(tid, patch, backup)
                st.rerun()

        # Excluir (com confirmação) — some instantaneamente, sync depois
        with c5:
            st.markdown('<div class="btn-danger">', unsafe_allow_html=True)
            if st.button("Excluir", key=f"{key_ns}_del_{tid}"):
                confirmar_exclusao(
                    f"dlg_{key_ns}_{tid}",
                    "Confirmar exclusão",
                    lambda: _queue_delete(tid)
                )
            st.markdown("</div>", unsafe_allow_html=True)

        # Reagendar rápido (sem modais)
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
                st.rerun()

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
                st.rerun()

        with r3:
            if st.button("Sem data", key=f"{key_ns}_nodate_{tid}"):
                if t.get("type") == "event":
                    patch = {"start_at": None, "type": "task", "due_at": None, "updated_at": datetime.utcnow().isoformat() + "Z"}
                else:
                    patch = {"due_at": None, "updated_at": datetime.utcnow().isoformat() + "Z"}
                backup = _apply_local_patch(tid, patch)
                _commit_patch(tid, patch, backup)
                st.rerun()

    def _render_editor(t: dict, key_ns: str):
        """Editor completo."""
        tid = int(t.get("id", 0))
        if tid < 0:
            return  # não edita enquanto não sincroniza

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
            tipo = "Evento" if t.get("type") == "event" else "Tarefa"
            ntipo = dc1.selectbox("Tipo", options=["Tarefa", "Evento"], index=0 if tipo == "Tarefa" else 1, key=f"{key_ns}_tp_{tid}")

            cur_date = _task_day(t)
            cur_dt = _iso_to_dt(t.get("start_at")) if t.get("type") == "event" else None
            ndt = dc2.date_input("Data", value=cur_date, key=f"{key_ns}_d_{tid}")
            nth = dc3.time_input("Hora (se evento)", value=(cur_dt.time() if cur_dt else None), key=f"{key_ns}_h_{tid}")

            pc1, pc2 = st.columns([1, 1])
            nprio = pc1.selectbox(
                "Prioridade",
                options=PRIORITY_OPCOES,
                format_func=lambda x: PRIORITY_LABELS.get(x, x),
                index=PRIORITY_OPCOES.index(t.get("priority", "normal")) if t.get("priority", "normal") in PRIORITY_OPCOES else 0,
                key=f"{key_ns}_pr_{tid}"
            )
            ntags = pc2.text_input(
                "Tags",
                value=" ".join([f"#{x}" for x in (t.get("tags") or [])]),
                placeholder="#trabalho #casa",
                key=f"{key_ns}_tg_{tid}"
            )

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
                    if ndt and nth:
                        patch["start_at"] = datetime.combine(ndt, nth).isoformat()
                        patch["due_at"] = None
                    else:
                        patch["type"] = "task"
                        patch["start_at"] = None
                        patch["due_at"] = None
                else:
                    patch["type"] = "task"
                    patch["start_at"] = None
                    patch["due_at"] = ndt.isoformat() if ndt else None

                backup = _apply_local_patch(tid, patch)
                ok = _commit_patch(tid, patch, backup)
                if ok:
                    st.toast("✅ Atualizado!")
                st.rerun()

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
        tag_txt = ""
        if isinstance(tags, list) and tags:
            tag_txt = " • " + " ".join([f"#{x}" for x in tags[:6]])

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

    # --------------------------
    # Abas
    # --------------------------
    with tab_hoje:
        hoje_items = [t for t in st.session_state.tasks if t.get("status") != "done" and _task_day(t) == date.today()]
        hoje_items = _apply_filters(hoje_items)
        _render_list(hoje_items, "hoje")

    with tab_prox:
        horizon = date.today() + timedelta(days=14)
        prox_items = []
        for t in st.session_state.tasks:
            if t.get("status") == "done":
                continue
            d = _task_day(t)
            if d and date.today() < d <= horizon:
                prox_items.append(t)
        prox_items = _apply_filters(prox_items)
        _render_list(prox_items, "prox")

    with tab_done:
        done_items = [t for t in st.session_state.tasks if t.get("status") == "done"]
        done_items = _apply_filters(done_items)
        done_items.sort(
            key=lambda x: x.get("completed_at") or x.get("updated_at") or x.get("created_at") or "",
            reverse=True
        )
        _render_list(done_items[:80], "done")

    with tab_all:
        all_items = _apply_filters(list(st.session_state.tasks))
        _render_list(all_items, "all")
