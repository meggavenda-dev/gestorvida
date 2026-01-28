# github_db.py
# -*- coding: utf-8 -*-
import base64
import json
import time
from typing import Tuple, Any, Optional, Callable, Dict, List

import requests
import streamlit as st
import pandas as pd
from datetime import date

GITHUB_API = "https://api.github.com"

# -------------------------------------------------
# Helpers GitHub (headers, get/put, update seguro)
# -------------------------------------------------
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
    owner, repo, branch = gh_repo_info()
    url = f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}"
    content_b64 = base64.b64encode(
        json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
    ).decode("utf-8")

    payload = {"message": message, "content": content_b64, "branch": branch}
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
    for attempt in range(max_retries):
        obj, sha = gh_get_file(path)
        new_obj = updater(obj)
        new_sha = gh_put_file(path, new_obj, commit_message or f"update {path}", sha)
        if new_sha:
            return new_obj, new_sha
        time.sleep(delay)
    st.error(f"[GitHub] Não foi possível atualizar {path} após {max_retries} tentativas.")
    return None, None

# -------------------------------------------------
# Bases por domínio (podem vir dos Secrets)
# -------------------------------------------------
FIN_BASE     = st.secrets.get("GITHUB_FIN_BASE",     "data/financeiro")
TASKS_BASE   = st.secrets.get("GITHUB_TASKS_BASE",   "data/tarefas")
SAUDE_BASE   = st.secrets.get("GITHUB_SAUDE_BASE",   "data/saude")
ESTUDOS_BASE = st.secrets.get("GITHUB_ESTUDOS_BASE", "data/estudos")

def fin_path(name: str) -> str:
    return f"{FIN_BASE}/{name}.json"

def tasks_path(name: str) -> str:
    return f"{TASKS_BASE}/{name}.json"

def saude_path(name: str) -> str:
    return f"{SAUDE_BASE}/{name}.json"

def estudos_path(name: str) -> str:
    return f"{ESTUDOS_BASE}/{name}.json"

# =================================================
#                    FINANCEIRO
# =================================================
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

def buscar_pessoas() -> List[str]:
    obj, _ = gh_get_file(fin_path("pessoas"))
    if obj and isinstance(obj, list):
        nomes = [n for n in obj if str(n).strip().lower() != "ambos"]
        return nomes + ["Ambos"]
    return ["Guilherme", "Alynne", "Ambos"]

def buscar_dados() -> pd.DataFrame:
    obj, _ = gh_get_file(fin_path("transacoes"))
    if not obj:
        return pd.DataFrame(columns=TRANS_COLS)
    df = pd.DataFrame(obj)
    return _normalize_transacoes_df(df)

def inserir_transacao(reg: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        new_id = (max([int(r.get("id", 0)) for r in obj]) + 1) if obj else 1
        reg['id'] = new_id
        obj.append(reg)
        return obj
    safe_update_json(fin_path("transacoes"), updater, commit_message="add transacao")

def atualizar_transacao(trans_id: int, patch: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        for r in obj:
            if int(r.get("id", -1)) == int(trans_id):
                r.update(patch)
        return obj
    safe_update_json(fin_path("transacoes"), updater, commit_message=f"update transacao {trans_id}")

def deletar_transacao(trans_id: int) -> None:
    def updater(obj):
        obj = obj or []
        return [r for r in obj if int(r.get("id", -1)) != int(trans_id)]
    safe_update_json(fin_path("transacoes"), updater, commit_message=f"delete transacao {trans_id}")

def buscar_metas() -> Dict[str, float]:
    obj, _ = gh_get_file(fin_path("metas"))
    return obj if isinstance(obj, dict) else {}

def upsert_meta(categoria: str, limite: float) -> None:
    def updater(obj):
        obj = obj or {}
        obj[categoria] = float(limite)
        return obj
    safe_update_json(fin_path("metas"), updater, commit_message=f"upsert meta {categoria}")

def buscar_fixos() -> pd.DataFrame:
    obj, _ = gh_get_file(fin_path("fixos"))
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
    safe_update_json(fin_path("fixos"), updater, commit_message="add fixo")

def atualizar_fixo(fixo_id: int, patch: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        for r in obj:
            if int(r.get("id", -1)) == int(fixo_id):
                r.update(patch)
        return obj
    safe_update_json(fin_path("fixos"), updater, commit_message=f"update fixo {fixo_id}")

def deletar_fixo(fixo_id: int) -> None:
    def updater(obj):
        obj = obj or []
        return [r for r in obj if int(r.get("id", -1)) != int(fixo_id)]
    safe_update_json(fin_path("fixos"), updater, commit_message=f"delete fixo {fixo_id}")

# =================================================
#                      TAREFAS
# =================================================
# /data/tarefas/tasks.json: lista de tarefas
# Campos sugeridos: id, title, description, due_at (ISO), status ('todo','doing','done','cancelled'), assignee ('Guilherme','Alynne','Ambos'), created_at (ISO)

def buscar_tasks() -> List[Dict[str, Any]]:
    obj, _ = gh_get_file(tasks_path("tasks"))
    return obj if isinstance(obj, list) else []

def inserir_task(reg: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        new_id = (max([int(r.get("id", 0)) for r in obj]) + 1) if obj else 1
        reg['id'] = new_id
        if 'status' not in reg: reg['status'] = 'todo'
        if 'assignee' not in reg: reg['assignee'] = 'Ambos'
        obj.append(reg)
        return obj
    safe_update_json(tasks_path("tasks"), updater, commit_message="add task")

def atualizar_task(task_id: int, patch: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        for r in obj:
            if int(r.get("id", -1)) == int(task_id):
                r.update(patch)
        return obj
    safe_update_json(tasks_path("tasks"), updater, commit_message=f"update task {task_id}")

def deletar_task(task_id: int) -> None:
    def updater(obj):
        obj = obj or []
        return [r for r in obj if int(r.get("id", -1)) != int(task_id)]
    safe_update_json(tasks_path("tasks"), updater, commit_message=f"delete task {task_id}")

# =================================================
#                       SAÚDE
# =================================================
# /data/saude/habits.json: lista de hábitos (id, name, target_per_day, unit)
# /data/saude/habit_logs.json: logs (id, habit_id, date (YYYY-MM-DD), amount)

def buscar_habitos() -> List[Dict[str, Any]]:
    obj, _ = gh_get_file(saude_path("habits"))
    return obj if isinstance(obj, list) else []

def inserir_habito(reg: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        new_id = (max([int(r.get("id", 0)) for r in obj]) + 1) if obj else 1
        reg['id'] = new_id
        reg.setdefault('target_per_day', 1)
        reg.setdefault('unit', '')
        obj.append(reg)
        return obj
    safe_update_json(saude_path("habits"), updater, commit_message="add habit")

def atualizar_habito(habit_id: int, patch: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        for r in obj:
            if int(r.get("id", -1)) == int(habit_id):
                r.update(patch)
        return obj
    safe_update_json(saude_path("habits"), updater, commit_message=f"update habit {habit_id}")

def deletar_habito(habit_id: int) -> None:
    def updater(obj):
        obj = obj or []
        return [r for r in obj if int(r.get("id", -1)) != int(habit_id)]
    safe_update_json(saude_path("habits"), updater, commit_message=f"delete habit {habit_id}")

def buscar_habit_logs() -> List[Dict[str, Any]]:
    obj, _ = gh_get_file(saude_path("habit_logs"))
    return obj if isinstance(obj, list) else []

def inserir_habit_log(reg: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        new_id = (max([int(r.get("id", 0)) for r in obj]) + 1) if obj else 1
        reg['id'] = new_id
        reg.setdefault('amount', 1)
        obj.append(reg)
        return obj
    safe_update_json(saude_path("habit_logs"), updater, commit_message="add habit_log")

def atualizar_habit_log(log_id: int, patch: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        for r in obj:
            if int(r.get("id", -1)) == int(log_id):
                r.update(patch)
        return obj
    safe_update_json(saude_path("habit_logs"), updater, commit_message=f"update habit_log {log_id}")

def deletar_habit_log(log_id: int) -> None:
    def updater(obj):
        obj = obj or []
        return [r for r in obj if int(r.get("id", -1)) != int(log_id)]
    safe_update_json(saude_path("habit_logs"), updater, commit_message=f"delete habit_log {log_id}")

# =================================================
#                      ESTUDOS
# =================================================
# subjects.json: id, name
# materials.json: id, subject_id, title, url
# flashcards.json: id, subject_id, front, back, easiness, interval_days, due_date
# sessions.json: id, subject_id, started_at (ISO), duration_min, notes

def buscar_subjects() -> List[Dict[str, Any]]:
    obj, _ = gh_get_file(estudos_path("subjects"))
    return obj if isinstance(obj, list) else []

def inserir_subject(reg: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        new_id = (max([int(r.get("id", 0)) for r in obj]) + 1) if obj else 1
        reg['id'] = new_id
        obj.append(reg)
        return obj
    safe_update_json(estudos_path("subjects"), updater, commit_message="add subject")

def atualizar_subject(subject_id: int, patch: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        for r in obj:
            if int(r.get("id", -1)) == int(subject_id):
                r.update(patch)
        return obj
    safe_update_json(estudos_path("subjects"), updater, commit_message=f"update subject {subject_id}")

def deletar_subject(subject_id: int) -> None:
    def updater(obj):
        obj = obj or []
        return [r for r in obj if int(r.get("id", -1)) != int(subject_id)]
    safe_update_json(estudos_path("subjects"), updater, commit_message=f"delete subject {subject_id}")

def buscar_materials() -> List[Dict[str, Any]]:
    obj, _ = gh_get_file(estudos_path("materials"))
    return obj if isinstance(obj, list) else []

def inserir_material(reg: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        new_id = (max([int(r.get("id", 0)) for r in obj]) + 1) if obj else 1
        reg['id'] = new_id
        obj.append(reg)
        return obj
    safe_update_json(estudos_path("materials"), updater, commit_message="add material")

def atualizar_material(material_id: int, patch: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        for r in obj:
            if int(r.get("id", -1)) == int(material_id):
                r.update(patch)
        return obj
    safe_update_json(estudos_path("materials"), updater, commit_message=f"update material {material_id}")

def deletar_material(material_id: int) -> None:
    def updater(obj):
        obj = obj or []
        return [r for r in obj if int(r.get("id", -1)) != int(material_id)]
    safe_update_json(estudos_path("materials"), updater, commit_message=f"delete material {material_id}")

def buscar_flashcards() -> List[Dict[str, Any]]:
    obj, _ = gh_get_file(estudos_path("flashcards"))
    return obj if isinstance(obj, list) else []

def inserir_flashcard(reg: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        new_id = (max([int(r.get("id", 0)) for r in obj]) + 1) if obj else 1
        reg['id'] = new_id
        reg.setdefault('easiness', 2.5)
        reg.setdefault('interval_days', 1)
        reg.setdefault('due_date', str(date.today()))
        obj.append(reg)
        return obj
    safe_update_json(estudos_path("flashcards"), updater, commit_message="add flashcard")

def atualizar_flashcard(card_id: int, patch: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        for r in obj:
            if int(r.get("id", -1)) == int(card_id):
                r.update(patch)
        return obj
    safe_update_json(estudos_path("flashcards"), updater, commit_message=f"update flashcard {card_id}")

def deletar_flashcard(card_id: int) -> None:
    def updater(obj):
        obj = obj or []
        return [r for r in obj if int(r.get("id", -1)) != int(card_id)]
    safe_update_json(estudos_path("flashcards"), updater, commit_message=f"delete flashcard {card_id}")

def buscar_sessions() -> List[Dict[str, Any]]:
    obj, _ = gh_get_file(estudos_path("sessions"))
    return obj if isinstance(obj, list) else []

def inserir_session(reg: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        new_id = (max([int(r.get("id", 0)) for r in obj]) + 1) if obj else 1
        reg['id'] = new_id
        obj.append(reg)
        return obj
    safe_update_json(estudos_path("sessions"), updater, commit_message="add study session")

def atualizar_session(session_id: int, patch: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        for r in obj:
            if int(r.get("id", -1)) == int(session_id):
                r.update(patch)
        return obj
    safe_update_json(estudos_path("sessions"), updater, commit_message=f"update study session {session_id}")

def deletar_session(session_id: int) -> None:
    def updater(obj):
        obj = obj or []
        return [r for r in obj if int(r.get("id", -1)) != int(session_id)]
    safe_update_json(estudos_path("sessions"), updater, commit_message=f"delete study session {session_id}")
