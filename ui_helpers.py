# ui_helpers.py
# -*- coding: utf-8 -*-
import streamlit as st

def confirmar_exclusao(chave_dialogo: str, titulo: str, on_confirm):
    """
    Abre um diálogo de confirmação (se disponível). Fallback: segundo clique.
    - chave_dialogo: chave única p/ cada item
    - titulo: título do diálogo
    - on_confirm: função sem args que executa a exclusão
    """
    try:
        @st.dialog(titulo)
        def _dlg():
            st.write("Essa ação não poderá ser desfeita.")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Cancelar"):
                    st.session_state.pop(chave_dialogo, None)
                    st.rerun()
            with c2:
                if st.button("Excluir definitivamente"):
                    on_confirm()
                    st.session_state.pop(chave_dialogo, None)
                    st.toast("Excluído com sucesso.")
                    st.rerun()

        if st.session_state.get(chave_dialogo):
            _dlg()
        else:
            st.session_state[chave_dialogo] = True
            st.rerun()
    except Exception:
        # Fallback simples de dois cliques (para versões antigas do Streamlit)
        st.warning("Toque novamente para confirmar a exclusão.")
        if st.button("Confirmar exclusão"):
            on_confirm()
            st.toast("Excluído com sucesso.")
            st.rerun()
