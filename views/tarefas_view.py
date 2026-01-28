# views/tarefas_view.py
# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta

from github_db import (
    buscar_tasks, inserir_task, atualizar_task, deletar_task,
    buscar_pessoas
)
from ui_helpers import confirmar_exclusao

# Status internos (mantêm os valores originais no banco)
STATUS_OPCOES = ['todo', 'doing', 'done', 'cancelled']

# Mapeamento → texto que aparece para o usuário
STATUS_LABELS = {
    "todo": "Não Iniciado",
    "doing": "Em Progresso",
    "done": "Finalizado",
    "cancelled": "Cancelado"
}

def parse_due_at(x):
    try:
        return datetime.fromisoformat(x).date() if x else None
    except Exception:
        return None

def filtrar_tasks(tasks, status_sel, resp_sel, janela):
    df = pd.DataFrame(tasks)
    if df.empty:
        return df
    df['due_date'] = df.get('due_at', None).apply(parse_due_at)
    if status_sel:
        df = df[df['status'].isin(status_sel)]
    if resp_sel != "Todos":
        df = df[df['assignee'] == resp_sel]
    hoje = date.today()
    if janela == "Hoje":
        df = df[df['due_date'] == hoje]
    elif janela == "Próximos 7 dias":
        limite = hoje + timedelta(days=7)
        df = df[(df['due_date'].notna()) & (df['due_date'] >= hoje) & (df['due_date'] <= limite)]
    elif janela == "Próximos 30 dias":
        limite = hoje + timedelta(days=30)
        df = df[(df['due_date'].notna()) & (df['due_date'] >= hoje) & (df['due_date'] <= limite)]
    df = df.sort_values(by=['due_date', 'status', 'title'], na_position='last')
    return df

def render_tarefas():
    st.markdown("""
      <div class="header-container">
        <div class="main-title">🗓️ Tarefas</div>
        <div class="slogan">Organize, priorize e conclua</div>
      </div>
    """, unsafe_allow_html=True)

    if 'tasks' not in st.session_state:
        st.session_state.tasks = buscar_tasks()
    if 'pessoas' not in st.session_state or not st.session_state.pessoas:
        st.session_state.pessoas = buscar_pessoas()

    PESSOAS = st.session_state.pessoas
    tasks_raw = st.session_state.tasks
    df_all = pd.DataFrame(tasks_raw)

    # Métricas
    if df_all.empty:
        total = 0; abertas = 0; hoje_qtd = 0; atrasadas = 0
    else:
        df_all['due_date'] = df_all.get('due_at', None).apply(parse_due_at)
        total = len(df_all)
        abertas = int((df_all['status'].isin(['todo','doing'])).sum())
        hoje_qtd = int(((df_all['due_date'] == date.today()) & df_all['status'].isin(['todo','doing'])).sum())
        atrasadas = int(((df_all['due_date'].notna()) &
                         (df_all['due_date'] < date.today()) &
                         df_all['status'].isin(['todo','doing'])).sum())

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total", str(total))
    m2.metric("Abertas", str(abertas))
    m3.metric("Para Hoje", str(hoje_qtd))
    m4.metric("Atrasadas", str(atrasadas))

    st.divider()

    # Nova tarefa rápida
    st.markdown("#### ➕ Nova rápida")
    with st.form("form_task_quick", clear_on_submit=True):
        col_q1, col_q2, col_q3 = st.columns([2,1,1])
        title = col_q1.text_input("Título", placeholder="O que precisa ser feito?")
        assignee = col_q2.selectbox("Resp.", options=PESSOAS, index=0)
        due = col_q3.date_input("Venc.", value=None)
        desc = st.text_input("Detalhes (opcional)")
        if st.form_submit_button("Adicionar"):
            if not title.strip():
                st.error("Informe o título.")
            else:
                inserir_task({
                    "title": title.strip(),
                    "description": desc.strip(),
                    "due_at": due.isoformat() if due else None,
                    "status": "todo",
                    "assignee": assignee,
                    "created_at": datetime.utcnow().isoformat()
                })
                st.toast("Tarefa criada!")
                st.session_state.tasks = buscar_tasks()
                st.rerun()

    st.divider()

    # Filtros
    col_f1, col_f2, col_f3 = st.columns([1.5, 1.5, 1])
    status_sel = col_f1.multiselect(
        "Status",
        STATUS_OPCOES,
        default=['todo', 'doing'],
        format_func=lambda x: STATUS_LABELS[x]
    )
    resp_sel = col_f2.selectbox("Responsável", options=["Todos"] + PESSOAS, index=0)
    janela = col_f3.selectbox("Vencimento", options=["Todos", "Hoje", "Próximos 7 dias", "Próximos 30 dias"], index=0)

    st.markdown("### Lista de Tarefas")
    df_view = filtrar_tasks(st.session_state.tasks, status_sel, resp_sel, janela)

    if df_view.empty:
        st.info("Nenhuma tarefa com os filtros atuais.")
        return

    for _, row in df_view.iterrows():
        s = row['status']
        s_class = s if s in ['todo','doing','done','cancelled'] else 'todo'
        label_status = STATUS_LABELS.get(s, s)

        due_txt = row['due_date'].strftime('%d/%m/%Y') if pd.notnull(row['due_date']) else '—'
        overdue_flag = ""
        if row['due_date'] and row['status'] in ['todo','doing']:
            diff = (row['due_date'] - date.today()).days
            if diff < 0:
                overdue_flag = f" • 🔴 Atrasada há {-diff}d"
            elif diff == 0:
                overdue_flag = " • 🟡 Vence hoje"

        st.markdown(f"""
        <div class="task-card">
          <div class="task-left">
            <div class="task-icon">🗒️</div>
            <div class="tk-info">
              <div class="tk-title">{row.get('title','(sem título)')}</div>
              <div class="tk-meta">Resp.: <b>{row.get('assignee','Ambos')}</b> • Venc.: <b>{due_txt}</b>{overdue_flag}</div>
              <div class="status-badge {s_class}">{label_status}</div>
              <div class="tk-meta">{(row.get('description') or '').strip()}</div>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        # Botões de ação
        c1, c2, c3, c4 = st.columns([1,1.4,2,1])
        with c1:
            if s != 'done' and st.button("✔ Finalizar", key=f"tsk_done_{row['id']}"):
                atualizar_task(int(row['id']), {"status": "done"})
                st.toast("Tarefa finalizada!")
                st.session_state.tasks = buscar_tasks(); st.rerun()

        with c2:
            col_bs1, col_bs2 = st.columns(2)
            if col_bs1.button("⏳ Não Iniciado", key=f"tsk_to_{row['id']}"):
                atualizar_task(int(row['id']), {"status": "todo"})
                st.session_state.tasks = buscar_tasks(); st.rerun()
            if col_bs2.button("🔄 Em Progresso", key=f"tsk_do_{row['id']}"):
                atualizar_task(int(row['id']), {"status": "doing"})
                st.session_state.tasks = buscar_tasks(); st.rerun()

        with c3:
            with st.expander("Editar"):
                nt = st.text_input("Título", value=row.get('title',''), key=f"tsk_et_{row['id']}")
                nd = st.text_area("Descrição", value=row.get('description',''), key=f"tsk_ed_{row['id']}")
                ndue = st.date_input("Vencimento", value=row['due_date'] if pd.notnull(row['due_date']) else None, key=f"tsk_ev_{row['id']}")
                nass = st.selectbox("Responsável", options=PESSOAS, index=PESSOAS.index(row.get('assignee','Ambos')) if row.get('assignee','Ambos') in PESSOAS else 0, key=f"tsk_ea_{row['id']}")
                if st.button("Salvar Alterações", key=f"tsk_save_ed_{row['id']}"):
                    atualizar_task(int(row['id']), {
                        "title": nt.strip(),
                        "description": nd.strip(),
                        "due_at": ndue.isoformat() if ndue else None,
                        "assignee": nass
                    })
                    st.toast("Atualizado!")
                    st.session_state.tasks = buscar_tasks(); st.rerun()

       
        with c4:
                    st.markdown('<div class="btn-danger">', unsafe_allow_html=True)
                    if st.button("Excluir", key=f"tsk_del_{row['id']}"):
                        confirmar_exclusao(
                            f"dlg_tsk_{row['id']}",
                            "Confirmar exclusão",
                            lambda: deletar_task(int(row['id']))
                        )
                    st.markdown('</div>', unsafe_allow_html=True)

