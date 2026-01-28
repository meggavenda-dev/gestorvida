# views/estudos_view.py
# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta

from github_db import (
    buscar_subjects, inserir_subject, atualizar_subject, deletar_subject,
    buscar_materials, inserir_material, atualizar_material, deletar_material,
    buscar_flashcards, inserir_flashcard, atualizar_flashcard, deletar_flashcard,
    buscar_sessions, inserir_session, atualizar_session, deletar_session
)

from ui_helpers import confirmar_exclusao

# ----------------------------
# Utilidades internas
# ----------------------------
def recarregar():
    """Recarrega dados desta aba para a sessão."""
    st.session_state.subjects = buscar_subjects()
    st.session_state.materials = buscar_materials()
    st.session_state.flashcards = buscar_flashcards()
    st.session_state.sessions = buscar_sessions()

def _safe_sort(df: pd.DataFrame, col: str, ascending=True):
    """Ordena com segurança; se coluna não existir, retorna df como está."""
    if df is None or df.empty:
        return df
    if col not in df.columns:
        return df
    return df.sort_values(by=col, ascending=ascending)

def _ensure_int_or_none(x):
    try:
        if pd.isna(x):
            return None
        return int(x)
    except Exception:
        return None

def _ensure_float_or_zero(x):
    try:
        if pd.isna(x):
            return 0.0
        return float(x)
    except Exception:
        return 0.0

# ----------------------------
# Render principal
# ----------------------------
def render_estudos():
    st.markdown("""
      <div class="header-container">
        <div class="main-title">📚 Estudos</div>
        <div class="slogan">Consistência e foco</div>
      </div>
    """, unsafe_allow_html=True)

    # Carrega sessão (defensivo)
    if 'subjects' not in st.session_state: st.session_state.subjects = buscar_subjects()
    if 'materials' not in st.session_state: st.session_state.materials = buscar_materials()
    if 'flashcards' not in st.session_state: st.session_state.flashcards = buscar_flashcards()
    if 'sessions' not in st.session_state: st.session_state.sessions = buscar_sessions()

    aba_assuntos, aba_flash, aba_sessoes = st.tabs(["📂 Assuntos & Materiais", "🧠 Flashcards", "⏱️ Sessões"])

    # =========================================================
    # Assuntos & Materiais
    # =========================================================
    with aba_assuntos:
        st.markdown("### Assuntos")
        with st.expander("➕ Novo assunto", expanded=False):
            with st.form("form_subject", clear_on_submit=True):
                nome = st.text_input("Nome do assunto")
                if st.form_submit_button("Salvar"):
                    if not nome.strip():
                        st.error("Informe o nome do assunto.")
                    else:
                        try:
                            inserir_subject({"name": nome.strip()})
                            st.success("Assunto criado!")
                            recarregar()
                            st.rerun()
                        except Exception as e:
                            st.error("Não foi possível criar o assunto.")
                            st.exception(e)

        subs = st.session_state.subjects or []
        mats = st.session_state.materials or []

        # Garante DataFrames com colunas esperadas
        df_s = pd.DataFrame(subs)
        if df_s.empty:
            df_s = pd.DataFrame(columns=['id', 'name'])
        if 'name' not in df_s.columns: df_s['name'] = None
        if 'id' not in df_s.columns: df_s['id'] = None

        df_m = pd.DataFrame(mats)
        if df_m.empty:
            df_m = pd.DataFrame(columns=['id', 'subject_id', 'title', 'url'])
        for c in ['id','subject_id','title','url']:
            if c not in df_m.columns:
                df_m[c] = None

        # Normaliza tipos de IDs para evitar comparações inconsistentes
        if 'id' in df_s.columns:
            df_s['id'] = df_s['id'].apply(_ensure_int_or_none)
        if 'subject_id' in df_m.columns:
            df_m['subject_id'] = df_m['subject_id'].apply(_ensure_int_or_none)
        if 'id' in df_m.columns:
            df_m['id'] = df_m['id'].apply(_ensure_int_or_none)

        if df_s.empty or df_s['id'].isna().all():
            st.info("Nenhum assunto cadastrado.")
        else:
            # Ordena com segurança por nome
            df_s = _safe_sort(df_s, 'name', ascending=True)

            for _, s in df_s.iterrows():
                sid = _ensure_int_or_none(s.get('id'))
                nome_assunto = (s.get('name') or "").strip() or "(sem nome)"

                st.markdown(f"<div class='card'><b>📁 {nome_assunto}</b></div>", unsafe_allow_html=True)

                # Materiais do assunto
                st.markdown("**Materiais**")
                if sid is not None:
                    mlist = df_m[df_m['subject_id'] == sid].copy()
                else:
                    mlist = pd.DataFrame(columns=['id','title','url','subject_id'])

                if mlist.empty:
                    st.caption("Nenhum material.")
                else:
                    for _, mt in mlist.iterrows():
                        mid = _ensure_int_or_none(mt.get('id'))
                        mtitle = (mt.get('title') or "").strip() or "(sem título)"
                        murl = (mt.get('url') or "").strip()
                        st.write(f"🔗 **{mtitle}** — {murl}")
                        c1, c3 = st.columns([2,1])

                        with c1:
                            if mid is not None:
                                with st.expander("Editar material"):
                                    nt = st.text_input("Título", value=mtitle, key=f"mt_t_{mid}")
                                    nu = st.text_input("URL", value=murl, key=f"mt_u_{mid}")
                                    if st.button("Salvar", key=f"mt_sv_{mid}"):
                                        try:
                                            atualizar_material(mid, {"title": nt.strip(), "url": nu.strip()})
                                            st.toast("Material atualizado!")
                                            recarregar(); st.rerun()
                                        except Exception as e:
                                            st.error("Falha ao atualizar material.")
                                            st.exception(e)

                        with c3:
                            if mid is not None:
                                st.markdown('<div class="btn-danger">', unsafe_allow_html=True)
                                if st.button("Excluir", key=f"mt_del_{mid}"):
                                    confirmar_exclusao(
                                        f"dlg_mt_{mid}", "Confirmar exclusão",
                                        lambda mid_=mid: deletar_material(mid_)
                                    )
                                st.markdown('</div>', unsafe_allow_html=True)

                # Adicionar material ao assunto
                if sid is not None:
                    with st.expander("➕ Adicionar material", expanded=False):
                        with st.form(f"form_mat_{sid}", clear_on_submit=True):
                            t = st.text_input("Título")
                            u = st.text_input("URL")
                            if st.form_submit_button("Adicionar"):
                                if not t.strip():
                                    st.error("Informe o título do material.")
                                else:
                                    try:
                                        inserir_material({"subject_id": sid, "title": t.strip(), "url": u.strip()})
                                        st.success("Material adicionado!")
                                        recarregar(); st.rerun()
                                    except Exception as e:
                                        st.error("Falha ao adicionar material.")
                                        st.exception(e)

                # Editar/Excluir assunto
                col_a1, col_a2 = st.columns([2,1])
                with col_a1:
                    if sid is not None:
                        with st.expander("Editar assunto"):
                            nn = st.text_input("Nome", value=nome_assunto, key=f"sb_n_{sid}")
                            if st.button("Salvar assunto", key=f"sb_sv_{sid}"):
                                try:
                                    atualizar_subject(sid, {"name": nn.strip()})
                                    st.toast("Assunto atualizado!")
                                    recarregar(); st.rerun()
                                except Exception as e:
                                    st.error("Falha ao atualizar assunto.")
                                    st.exception(e)

                with col_a2:
                    if sid is not None:
                        st.markdown('<div class="btn-danger">', unsafe_allow_html=True)
                        if st.button("Excluir assunto", key=f"sb_del_{sid}"):
                            confirmar_exclusao(
                                f"dlg_sb_{sid}", "Confirmar exclusão",
                                lambda sid_=sid: deletar_subject(sid_)
                            )
                        st.markdown('</div>', unsafe_allow_html=True)

    # =========================================================
    # Flashcards
    # =========================================================
    with aba_flash:
        st.markdown("### Flashcards")
        subs = st.session_state.subjects or []
        cards = st.session_state.flashcards or []

        df_s = pd.DataFrame(subs)
        if df_s.empty:
            df_s = pd.DataFrame(columns=['id', 'name'])
        if 'id' not in df_s.columns: df_s['id'] = None
        if 'name' not in df_s.columns: df_s['name'] = None
        # Normaliza id
        df_s['id'] = df_s['id'].apply(_ensure_int_or_none)
        df_s = _safe_sort(df_s, 'name', ascending=True)

        df_c = pd.DataFrame(cards)
        if df_c.empty:
            df_c = pd.DataFrame(columns=['id', 'subject_id', 'front', 'back', 'easiness', 'interval_days', 'due_date'])
        for c in ['id','subject_id','front','back','easiness','interval_days','due_date']:
            if c not in df_c.columns:
                df_c[c] = None
        # Normaliza ids numéricos
        df_c['id'] = df_c['id'].apply(_ensure_int_or_none)
        df_c['subject_id'] = df_c['subject_id'].apply(_ensure_int_or_none)

        # Opções de assunto para filtros
        sid_options = [("Todos", None)]
        if not df_s.empty:
            for _, s in df_s.iterrows():
                sid = _ensure_int_or_none(s.get('id'))
                sname = (s.get('name') or "").strip() or (f"Assunto {sid}" if sid else "(sem nome)")
                if sid is not None:
                    sid_options.append((sname, sid))
        nomes_to_id = {n:i for n,i in sid_options}

        col_f1, col_f2, col_f3 = st.columns([2,1,1])
        sid_name = col_f1.selectbox("Assunto (filtro)", options=[n for n,_ in sid_options], index=0)
        filtro = col_f2.selectbox("Mostrar", options=["A vencer hoje", "Todos"], index=0)
        ordem = col_f3.selectbox("Ordem", options=["Mais urgentes", "Mais novos"], index=0)
        sel_sid = nomes_to_id[sid_name]

        # Formulário de novo flashcard - sempre visível se houver assunto
        st.markdown("#### ➕ Novo flashcard")
        with st.form("form_card", clear_on_submit=True):
            assuntos_validos = [n for n,_ in sid_options if _ is not None]
            if assuntos_validos:
                # Seleciona por padrão o assunto do filtro, se for específico
                default_idx = 0
                if sel_sid is not None:
                    # acha o índice do assunto correspondente em assuntos_validos
                    for i, nome in enumerate(assuntos_validos):
                        if nomes_to_id.get(nome) == sel_sid:
                            default_idx = i
                            break
                sb = st.selectbox("Assunto", options=assuntos_validos, index=default_idx, key="new_card_subj")
                subj_id = nomes_to_id[sb]
                front = st.text_area("Frente", height=80)
                back = st.text_area("Verso", height=80)
                if st.form_submit_button("Salvar"):
                    if not front.strip() or not back.strip():
                        st.error("Preencha frente e verso.")
                    else:
                        try:
                            inserir_flashcard({
                                "subject_id": subj_id,
                                "front": front.strip(),
                                "back": back.strip(),
                            })
                            st.success("Flashcard criado!")
                            recarregar(); st.rerun()
                        except Exception as e:
                            st.error("Falha ao criar flashcard.")
                            st.exception(e)
            else:
                st.warning("Cadastre um assunto primeiro em **Assuntos & Materiais** para criar flashcards.")

        st.divider()

        # Listagem / Estudo
        if df_c.empty:
            st.info("Nenhum flashcard cadastrado.")
        else:
            # Normaliza due_date
            df_c['due_date'] = pd.to_datetime(df_c['due_date'], errors='coerce').dt.date
            hoje = date.today()

            # Filtra por assunto
            if sel_sid is not None:
                df_c = df_c[df_c['subject_id'] == sel_sid]

            # Filtra por vencimento
            if filtro == "A vencer hoje":
                df_c = df_c[df_c['due_date'].isna() | (df_c['due_date'] <= hoje)]

            # Ordena
            if ordem == "Mais urgentes":
                df_c = df_c.sort_values(by=['due_date'], na_position='first')
            else:
                df_c = df_c.sort_values(by=['id'], ascending=False, na_position='last')

            st.caption(f"Cartões nesta visão: **{len(df_c)}**")

            # SM-2 simplificado (3 botões)
            def sm2_update(card, quality: int):
                e = float(card.get('easiness', 2.5) or 2.5)
                interval = int(card.get('interval_days', 1) or 1)
                e = e + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
                if e < 1.3: e = 1.3
                if quality < 3:
                    interval = 1
                else:
                    if interval == 1:
                        interval = 2
                    else:
                        interval = int(round(interval * e))
                due = date.today() + timedelta(days=interval)
                return e, interval, due

            def _apply_review(cid, card, q):
                e,i,d = sm2_update(card, q)
                atualizar_flashcard(cid, {"easiness": e, "interval_days": i, "due_date": d.isoformat()})
                st.toast(f"Revisado — próximo em {i}d")
                recarregar(); st.rerun()

            # Cartões
            for _, c in df_c.iterrows():
                cid = _ensure_int_or_none(c.get('id'))
                if cid is None:
                    continue

                st.markdown(f"<div class='card'><b>Frente:</b> {c.get('front','')}</div>", unsafe_allow_html=True)
                with st.expander("Mostrar resposta"):
                    st.write(c.get('back',''))

                col_r1, col_r2, col_r3 = st.columns(3)
                if col_r1.button("🔁 Novamente", key=f"qA_{cid}"):
                    _apply_review(cid, c, 1)  # 0–2
                if col_r2.button("👍 Bom", key=f"qG_{cid}"):
                    _apply_review(cid, c, 4)  # 3–4
                if col_r3.button("✨ Fácil", key=f"qE_{cid}"):
                    _apply_review(cid, c, 5)  # 5

                c1, c2 = st.columns([3,1])
                with c1:
                    with st.expander("Editar cartão"):
                        nf = st.text_area("Frente", value=c.get('front',''), key=f"cf_{cid}")
                        nb = st.text_area("Verso", value=c.get('back',''), key=f"cb_{cid}")
                        if st.button("Salvar", key=f"c_save_{cid}"):
                            try:
                                atualizar_flashcard(cid, {"front": nf.strip(), "back": nb.strip()})
                                st.toast("Atualizado!")
                                recarregar(); st.rerun()
                            except Exception as e:
                                st.error("Falha ao atualizar cartão.")
                                st.exception(e)
                with c2:
                    st.markdown('<div class="btn-danger">', unsafe_allow_html=True)
                    if st.button("Excluir", key=f"c_del_{cid}"):
                        confirmar_exclusao(
                            f"dlg_card_{cid}", "Confirmar exclusão",
                            lambda cid_=cid: deletar_flashcard(cid_)
                        )
                    st.markdown('</div>', unsafe_allow_html=True)

    # =========================================================
    # Sessões
    # =========================================================
    with aba_sessoes:
        st.markdown("### Sessões de estudo")
        subs = st.session_state.subjects or []
        sessions = st.session_state.sessions or []

        df_s = pd.DataFrame(subs)
        if df_s.empty:
            df_s = pd.DataFrame(columns=['id','name'])
        if 'id' not in df_s.columns: df_s['id'] = None
        if 'name' not in df_s.columns: df_s['name'] = None
        df_s['id'] = df_s['id'].apply(_ensure_int_or_none)
        df_s = _safe_sort(df_s, 'name', ascending=True)

        sid_options = []
        for _, s in df_s.iterrows():
            sid = _ensure_int_or_none(s.get('id'))
            if sid is not None:
                sid_options.append(( (s.get('name') or "").strip() or f"Assunto {sid}", sid))
        nomes_to_id = {n:i for n,i in sid_options} if sid_options else {}

        with st.expander("➕ Nova sessão", expanded=False):
            with st.form("form_session", clear_on_submit=True):
                if sid_options:
                    sb = st.selectbox("Assunto", options=[n for n,_ in sid_options], index=0, key="new_session_subj")
                    subj_id = nomes_to_id[sb]
                else:
                    st.warning("Cadastre um assunto primeiro.")
                    subj_id = None
                dur = st.number_input("Duração (minutos)", min_value=1, value=30, step=1)
                notes = st.text_area("Notas (opcional)", height=80)
                if st.form_submit_button("Salvar"):
                    if subj_id is None:
                        st.error("Selecione um assunto.")
                    else:
                        try:
                            inserir_session({
                                "subject_id": subj_id,
                                "started_at": datetime.utcnow().isoformat(),
                                "duration_min": int(dur),
                                "notes": notes.strip()
                            })
                            st.success("Sessão registrada!")
                            recarregar(); st.rerun()
                        except Exception as e:
                            st.error("Falha ao registrar sessão.")
                            st.exception(e)

        df_se = pd.DataFrame(sessions)
        if df_se.empty:
            st.info("Nenhuma sessão registrada.")
        else:
            # Garante colunas
            if 'started_at' not in df_se.columns: df_se['started_at'] = None
            if 'subject_id' not in df_se.columns: df_se['subject_id'] = None
            if 'duration_min' not in df_se.columns: df_se['duration_min'] = 0
            if 'notes' not in df_se.columns: df_se['notes'] = ""

            df_se['subject_id'] = df_se['subject_id'].apply(_ensure_int_or_none)
            df_se['duration_min'] = df_se['duration_min'].apply(lambda v: int(_ensure_float_or_zero(v)))
            df_se['started_at_dt'] = pd.to_datetime(df_se['started_at'], errors='coerce')

            # Mapa id -> nome
            nomes = {}
            for _, s in df_s.iterrows():
                sid = _ensure_int_or_none(s.get('id'))
                if sid is not None:
                    nomes[sid] = (s.get('name') or "").strip() or f"Assunto {sid}"

            st.caption(f"Total de sessões: {len(df_se)}")

            for _, se in df_se.sort_values(by='started_at_dt', ascending=False, na_position='last').head(30).iterrows():
                sid = _ensure_int_or_none(se.get('subject_id'))
                nome = nomes.get(sid, f"Assunto {sid}") if sid is not None else "(sem assunto)"
                dt_txt = se['started_at_dt'].strftime('%d/%m/%Y %H:%M') if pd.notnull(se['started_at_dt']) else (se.get('started_at','') or '')
                duracao = int(se.get('duration_min',0) or 0)
                notas = se.get('notes','') or ''

                st.markdown(f"<div class='card'>📌 <b>{nome}</b> • {dt_txt} • {duracao} min<br>{notas}</div>", unsafe_allow_html=True)

                sess_id = _ensure_int_or_none(se.get('id'))
                if sess_id is None:
                    continue

                c1, c3 = st.columns([2,1])
                with c1:
                    with st.expander("Editar sessão"):
                        ndur = st.number_input("Duração (min)", min_value=1, value=duracao if duracao > 0 else 1, step=1, key=f"se_dur_{sess_id}")
                        nnotes = st.text_area("Notas", value=notas, key=f"se_nt_{sess_id}")
                        if st.button("Salvar", key=f"se_sv_{sess_id}"):
                            try:
                                atualizar_session(int(sess_id), {"duration_min": int(ndur), "notes": nnotes.strip()})
                                st.toast("Sessão atualizada!")
                                recarregar(); st.rerun()
                            except Exception as e:
                                st.error("Falha ao atualizar sessão.")
                                st.exception(e)
                with c3:
                    st.markdown('<div class="btn-danger">', unsafe_allow_html=True)
                    if st.button("Excluir", key=f"se_del_{sess_id}"):
                        confirmar_exclusao(
                            f"dlg_se_{sess_id}", "Confirmar exclusão",
                            lambda sid_=sess_id: deletar_session(int(sid_))
                        )
                    st.markdown('</div>', unsafe_allow_html=True)
