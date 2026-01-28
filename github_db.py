# github_db.py
# -*- coding: utf-8 -*-
import base64
import json
import time
from typing import Tuple, Any, Optional, Callable, Dict, List

import requests
import streamlit as st
import pandas as pd

GITHUB_API = "https://api.github.com"

def gh_headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {st.secrets['GITHUB_TOKEN']}",
        "Accept": "application/vnd.github+json"
    }

def gh_repo_info() -> Tuple[str, str, str]:
    owner = st.secrets["GITHUB_OWNER"]
    repo = st.secrets["GITHUB_REPO"]
    branch = st.secrets.get("GITHUB_BRANCH", "main")
    return owner, repo, branch

def gh_get_file(path: str) -> Tuple[Optional[Any], Optional[str]]:
    """
    Lê um arquivo do GitHub e retorna (objeto json, sha).
    Se não existir, retorna (None, None).
    """
    owner, repo, branch = gh_repo_info()
    url = f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}?ref={branch}"
    r = requests.get(url, headers=gh_headers(), timeout=30)
    if r.status_code == 200:
        data = r.json()
        content = base64.b64decode(data["content"]).decode("utf-8")
        return json.loads(content), data["sha"]
    elif r.status_code == 404:
        return None, None
    else:
        st.error(f"[GitHub] Erro ao ler {path}: {r.status_code} {r.text}")
        return None, None

def gh_put_file(path: str, obj: Any, message: str, sha: Optional[str]) -> Optional[str]:
    """
    Grava arquivo no GitHub (create/update).
    Requer o sha para update seguro. Retorna novo sha.
    """
    owner, repo, branch = gh_repo_info()
    url = f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}"
    content_b64 = base64.b64encode(
        json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
    ).decode("utf-8")

    payload = {
        "message": message,
        "content": content_b64,
        "branch": branch
    }
    if sha:
        payload["sha"] = sha

    r = requests.put(url, headers=gh_headers(), json=payload, timeout=30)
    if r.status_code in (200, 201):
        return r.json()["content"]["sha"]
    else:
        st.error(f"[GitHub] Erro ao gravar {path}: {r.status_code} {r.text}")
        return None

def safe_update_json(
    path: str,
    updater: Callable[[Optional[Any]], Any],
    commit_message: str = "",
    max_retries: int = 3,
    delay: float = 0.8
) -> Tuple[Optional[Any], Optional[str]]:
    """
    Padrão de atualização com retry:
      1) Lê (obj, sha)
      2) updater(obj) -> novo_obj
      3) Grava com sha
      4) Se falhar, tenta novamente (até max_retries)
    """
    for attempt in range(max_retries):
        obj, sha = gh_get_file(path)
        new_obj = updater(obj)  # constrói a nova versão
        new_sha = gh_put_file(path, new_obj, commit_message or f"update {path}", sha)
        if new_sha:
            return new_obj, new_sha
        time.sleep(delay)
    st.error(f"[GitHub] Não foi possível atualizar {path} após {max_retries} tentativas.")
    return None, None

# =========================
#  Financeiro (paths base)
# =========================
FIN_BASE = st.secrets.get("GITHUB_BASE_PATH", "data/financeiro")
def gh_path(name: str) -> str:
    # name sem extensão
    return f"{FIN_BASE}/{name}.json"

# =========================
#  Pessoas
# =========================
def buscar_pessoas() -> List[str]:
    obj, _ = gh_get_file(gh_path("pessoas"))
    if obj and isinstance(obj, list):
        nomes = [n for n in obj if str(n).strip().lower() != "ambos"]
        return nomes + ["Ambos"]
    return ["Guilherme", "Alynne", "Ambos"]

# =========================
#  Transações
# =========================
TRANS_COLS = ['id','data','descricao','valor','tipo','categoria','status','responsavel']

def _normalize_transacoes_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=TRANS_COLS)
    df['data'] = pd.to_datetime(df['data'], errors='coerce')
    if 'status' not in df.columns: df['status'] = 'Pago'
    df['status'] = df['status'].fillna('Pago').astype(str)
    if 'responsavel' not in df.columns: df['responsavel'] = 'Ambos'
    df['responsavel'] = df['responsavel'].fillna('Ambos').astype(str)
    for c in TRANS_COLS:
        if c not in df.columns:
            df[c] = None
    return df[TRANS_COLS]

def buscar_dados() -> pd.DataFrame:
    obj, _ = gh_get_file(gh_path("transacoes"))
    if not obj:
        return pd.DataFrame(columns=TRANS_COLS)
    df = pd.DataFrame(obj)
    return _normalize_transacoes_df(df)

def inserir_transacao(reg: Dict[str, Any]) -> None:
    def updater(obj):
        if obj is None:
            obj = []
        new_id = (max([int(r.get("id", 0)) for r in obj]) + 1) if obj else 1
        reg['id'] = new_id
        obj.append(reg)
        return obj
    safe_update_json(gh_path("transacoes"), updater, commit_message="add transacao")

def atualizar_transacao(trans_id: int, patch: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        for r in obj:
            if int(r.get("id", -1)) == int(trans_id):
                r.update(patch)
        return obj
    safe_update_json(gh_path("transacoes"), updater, commit_message=f"update transacao {trans_id}")

def deletar_transacao(trans_id: int) -> None:
    def updater(obj):
        obj = obj or []
        return [r for r in obj if int(r.get("id", -1)) != int(trans_id)]
    safe_update_json(gh_path("transacoes"), updater, commit_message=f"delete transacao {trans_id}")

# =========================
#  Metas
# =========================
def buscar_metas() -> Dict[str, float]:
    obj, _ = gh_get_file(gh_path("metas"))
    return obj if isinstance(obj, dict) else {}

def upsert_meta(categoria: str, limite: float) -> None:
    def updater(obj):
        obj = obj or {}
        obj[categoria] = float(limite)
        return obj
    safe_update_json(gh_path("metas"), updater, commit_message=f"upsert meta {categoria}")

# =========================
#  Fixos
# =========================
def buscar_fixos() -> pd.DataFrame:
    obj, _ = gh_get_file(gh_path("fixos"))
    if not obj:
        return pd.DataFrame(columns=['id','descricao','valor','categoria','responsavel'])
    df = pd.DataFrame(obj)
    if 'responsavel' not in df.columns: df['responsavel'] = 'Ambos'
    df['responsavel'] = df['responsavel'].fillna('Ambos').astype(str)
    return df

def inserir_fixo(reg: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        new_id = (max([int(r.get("id", 0)) for r in obj]) + 1) if obj else 1
        reg['id'] = new_id
        obj.append(reg)
        return obj
    safe_update_json(gh_path("fixos"), updater, commit_message="add fixo")

def atualizar_fixo(fixo_id: int, patch: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        for r in obj:
            if int(r.get("id", -1)) == int(fixo_id):
                r.update(patch)
        return obj
    safe_update_json(gh_path("fixos"), updater, commit_message=f"update fixo {fixo_id}")

def deletar_fixo(fixo_id: int) -> None:
    def updater(obj):
        obj = obj or []
        return [r for r in obj if int(r.get("id", -1)) != int(fixo_id)]
    safe_update_json(gh_path("fixos"), updater, commit_message=f"delete fixo {fixo_id}")
