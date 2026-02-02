# ui_helpers.py
# -*- coding: utf-8 -*-
import streamlit as st

def confirmar_exclusao(chave_dialogo: str, titulo: str, on_confirm):
    """
    Abre diálogo de confirmação (quando disponível) SEM exigir 2 cliques.
    - chave_dialogo: chave única por item
    - titulo: título do diálogo
    - on_confirm: função sem args que executa a exclusão
    """
    # Se a flag ainda não existe, marcamos para abrir
    if chave_dialogo not in st.session_state:
        st.session_state[chave_dialogo] = True

    try:
        @st.dialog(titulo)
        def _dlg():
            st.write("Essa ação não poderá ser desfeita.")
            c1, c2 = st.columns(2)

            with c1:
                if st.button("Cancelar", key=f"{chave_dialogo}_cancel"):
                    st.session_state.pop(chave_dialogo, None)
                    st.rerun()

            with c2:
                if st.button("Excluir definitivamente", key=f"{chave_dialogo}_confirm"):
                    # Executa a ação
                    on_confirm()
                    st.session_state.pop(chave_dialogo, None)
                    st.toast("Excluído com sucesso.")
                    st.rerun()

        # ✅ ABRE O DIALOG NA MESMA EXECUÇÃO (1 clique apenas)
        if st.session_state.get(chave_dialogo):
            _dlg()

    except Exception:
        # Fallback para versões antigas sem st.dialog
        st.warning("Confirme a exclusão abaixo.")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Cancelar", key=f"{chave_dialogo}_cancel_fb"):
                st.session_state.pop(chave_dialogo, None)
                st.rerun()
        with c2:
            if st.button("Confirmar exclusão", key=f"{chave_dialogo}_confirm_fb"):
                on_confirm()
                st.session_state.pop(chave_dialogo, None)
                st.toast("Excluído com sucesso.")
                st.rerun()
