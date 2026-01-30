# github_db.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import base64
import json
import time
import random
from typing import Tuple, Any, Optional, Callable, Dict, List

import requests
import streamlit as st
import pandas as pd
from datetime import datetime

GITHUB_API = "https://api.github.com"
DEFAULT_TIMEOUT = 30

# ---------------------------------------------
#  GITHUB CORE
# ---------------------------------------------
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
    Lê JSON no GitHub (contents API) e retorna (obj, sha).
    """
    owner, repo, branch = gh_repo_info()
    url = f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}?ref={branch}"

    try:
        r = requests.get(url, headers=gh_headers(), timeout=DEFAULT_TIMEOUT)
    except Exception as e:
        st.error(f"[GitHub] Falha de rede ao ler {path}: {e}")
        return None, None

    if r.status_code == 200:
        try:
            data = r.json()
            content = base64.b64decode(data["content"]).decode("utf-8")
            return json.loads(content), data["sha"]
        except Exception as e:
            st.error(f"[GitHub] Erro ao decodificar JSON de {path}: {e}")
            return None, None

    if r.status_code == 404:
        return None, None

    st.error(f"[GitHub] Erro ao ler {path}: {r.status_code} {r.text}")
    return None, None

def gh_put_file(path: str, obj: Any, message: str, sha: Optional[str]) -> Optional[str]:
    """
    Grava JSON no GitHub (contents API).
    Retorna novo sha ou None.
    Obs.: 409 (conflito SHA) retorna None silenciosamente para permitir retry.
    """
    owner, repo, branch = gh_repo_info()
    url = f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}"

    content_str = json.dumps(obj, ensure_ascii=False, indent=2)
    content_b64 = base64.b64encode(content_str.encode("utf-8")).decode("utf-8")

    payload = {
        "message": message or f"update {path}",
        "content": content_b64,
        "branch": branch
    }
    if sha:
        payload["sha"] = sha

    try:
        r = requests.put(url, headers=gh_headers(), json=payload, timeout=DEFAULT_TIMEOUT)
    except Exception as e:
        st.error(f"[GitHub] Falha de rede ao gravar {path}: {e}")
        return None

    if r.status_code in (200, 201):
        try:
            return r.json()["content"]["sha"]
        except Exception:
            return None

    # ✅ 409 = conflito SHA (arquivo mudou entre GET e PUT). Deixa retry cuidar.
    if r.status_code == 409:
        return None

    st.error(f"[GitHub] Erro ao gravar {path}: {r.status_code} {r.text}")
    return None

def safe_update_json(
    path: str,
    updater: Callable[[Optional[Any]], Any],
    commit_message: str = "",
    max_retries: int = 8,
    delay: float = 0.6
) -> Tuple[Optional[Any], Optional[str]]:
    """
    Lê (obj, sha) -> aplica updater(obj) -> grava com sha -> retry em conflito/falha.
    Estratégia:
    - 409 (conflito) tenta novamente com jitter
    - mostra erro somente após esgotar tentativas
    """
    last_err: Optional[str] = None

    for attempt in range(max_retries):
        obj, sha = gh_get_file(path)

        try:
            new_obj = updater(obj)
        except Exception as e:
            st.error(f"[GitHub] updater falhou em {path}: {e}")
            return None, None

        new_sha = gh_put_file(path, new_obj, commit_message or f"update {path}", sha)
        if new_sha:
            return new_obj, new_sha

        # se não gravou, pode ter sido conflito 409 ou outra falha silenciosa
        last_err = f"tentativa {attempt+1}/{max_retries} falhou (possível conflito/concorrência)."

        # jitter reduz colisão entre sessões/reruns
        time.sleep(delay * (1.0 + random.random() * 0.7))

    st.error(f"[GitHub] Não foi possível atualizar {path} após {max_retries} tentativas. {last_err or ''}")
    return None, None

# ---------------------------------------------
#  BASES (podem ser customizadas via secrets)
# ---------------------------------------------
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
TRANS_COLS = ['id', 'data', 'descricao', 'valor', 'tipo', 'categoria', 'status', 'responsavel']

def _normalize_transacoes_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=TRANS_COLS)

    df['data'] = pd.to_datetime(df['data'], errors='coerce')

    if 'status' not in df.columns:
        df['status'] = 'Pago'
    df['status'] = df['status'].fillna('Pago').astype(str)

    if 'responsavel' not in df.columns:
        df['responsavel'] = 'Ambos'
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
        new_id = (max([int(r.get("id", 0)) for r in obj if isinstance(r, dict)]) + 1) if obj else 1
        reg2 = dict(reg)
        reg2['id'] = new_id
        obj.append(reg2)
        return obj
    safe_update_json(fin_path("transacoes"), updater, commit_message="add transacao")

def atualizar_transacao(trans_id: int, patch: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        for r in obj:
            if isinstance(r, dict) and int(r.get("id", -1)) == int(trans_id):
                r.update(dict(patch))
        return obj
    safe_update_json(fin_path("transacoes"), updater, commit_message=f"update transacao {trans_id}")

def deletar_transacao(trans_id: int) -> None:
    def updater(obj):
        obj = obj or []
        return [r for r in obj if not (isinstance(r, dict) and int(r.get("id", -1)) == int(trans_id))]
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
        return pd.DataFrame(columns=['id', 'descricao', 'valor', 'categoria', 'responsavel'])
    df = pd.DataFrame(obj)
    if 'responsavel' not in df.columns:
        df['responsavel'] = 'Ambos'
    df['responsavel'] = df['responsavel'].fillna('Ambos').astype(str)
    return df

def inserir_fixo(reg: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        new_id = (max([int(r.get("id", 0)) for r in obj if isinstance(r, dict)]) + 1) if obj else 1
        reg2 = dict(reg)
        reg2['id'] = new_id
        obj.append(reg2)
        return obj
    safe_update_json(fin_path("fixos"), updater, commit_message="add fixo")

def atualizar_fixo(fixo_id: int, patch: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        for r in obj:
            if isinstance(r, dict) and int(r.get("id", -1)) == int(fixo_id):
                r.update(dict(patch))
        return obj
    safe_update_json(fin_path("fixos"), updater, commit_message=f"update fixo {fixo_id}")

def deletar_fixo(fixo_id: int) -> None:
    def updater(obj):
        obj = obj or []
        return [r for r in obj if not (isinstance(r, dict) and int(r.get("id", -1)) == int(fixo_id))]
    safe_update_json(fin_path("fixos"), updater, commit_message=f"delete fixo {fixo_id}")

# =================================================
#                      TAREFAS
# =================================================
def _normalize_task_row(r: Dict[str, Any]) -> Dict[str, Any]:
    """
    Mantém compatibilidade com registros antigos e garante defaults
    para a nova UX (type/event/start_at/tags/priority/recurrence etc).
    """
    rr = dict(r)

    rr.setdefault("title", "")
    rr.setdefault("description", "")
    rr.setdefault("assignee", rr.get("assignee", "Ambos") or "Ambos")
    rr.setdefault("status", rr.get("status", "todo") or "todo")

    # Novo modelo
    rr.setdefault("type", rr.get("type", "task") or "task")  # task|event
    rr.setdefault("due_at", rr.get("due_at", None))
    rr.setdefault("start_at", rr.get("start_at", None))
    rr.setdefault("end_at", rr.get("end_at", None))

    rr.setdefault("priority", rr.get("priority", "normal") or "normal")  # normal|important
    rr.setdefault("tags", rr.get("tags", []) or [])
    if not isinstance(rr["tags"], list):
        rr["tags"] = []

    rr.setdefault("recurrence", rr.get("recurrence", None))
    rr.setdefault("context", rr.get("context", None))
    rr.setdefault("reminders", rr.get("reminders", []) or [])
    if not isinstance(rr["reminders"], list):
        rr["reminders"] = []

    rr.setdefault("created_at", rr.get("created_at"))
    rr.setdefault("updated_at", rr.get("updated_at"))
    rr.setdefault("completed_at", rr.get("completed_at"))

    return rr

def buscar_tasks() -> List[Dict[str, Any]]:
    obj, _ = gh_get_file(tasks_path("tasks"))
    if not obj or not isinstance(obj, list):
        return []
    out: List[Dict[str, Any]] = []
    for r in obj:
        if isinstance(r, dict) and r.get("id") is not None:
            out.append(_normalize_task_row(r))
    return out

def inserir_task(reg: Dict[str, Any]) -> bool:
    """
    Insere uma tarefa e retorna True se gravou (commit OK), False caso contrário.
    Robusto contra IDs inválidos em registros antigos.
    """
    def updater(obj):
        obj = obj if isinstance(obj, list) else []

        # IDs robustos (ignora inválidos)
        ids = []
        for r in obj:
            if not isinstance(r, dict):
                continue
            try:
                ids.append(int(r.get("id") or 0))
            except Exception:
                pass

        new_id = (max(ids) + 1) if ids else 1

        reg2 = dict(reg)
        reg2["id"] = new_id
        reg2.setdefault("status", "todo")
        reg2.setdefault("assignee", "Ambos")
        reg2.setdefault("type", "task")
        reg2.setdefault("priority", "normal")
        reg2.setdefault("tags", [])
        reg2.setdefault("recurrence", None)
        reg2.setdefault("reminders", [])

        obj.append(reg2)
        return obj

    new_obj, new_sha = safe_update_json(
        tasks_path("tasks"),
        updater,
        commit_message="add task",
        max_retries=15,   # <- aumenta para concorrência real
        delay=0.5
    )
    return bool(new_sha)

def atualizar_task(task_id: int, patch: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        for r in obj:
            if isinstance(r, dict) and int(r.get("id", -1)) == int(task_id):
                r.update(dict(patch))
        return obj
    safe_update_json(tasks_path("tasks"), updater, commit_message=f"update task {task_id}")

def deletar_task(task_id: int) -> None:
    def updater(obj):
        obj = obj or []
        return [r for r in obj if not (isinstance(r, dict) and int(r.get("id", -1)) == int(task_id))]
    safe_update_json(tasks_path("tasks"), updater, commit_message=f"delete task {task_id}")

# =================================================
#                       SAÚDE (LEGADO: HÁBITOS)
# =================================================
def _ensure_recurrence_dict_or_none(value: Any) -> Optional[dict]:
    """
    Garante que 'recurrence' seja dict ou None. Converte valores inválidos para None.
    """
    if value is None:
        return None
    if isinstance(value, dict):
        rtype = value.get("type")
        days = value.get("days")
        if rtype == "weekly" and isinstance(days, list):
            days_norm = []
            for d in days:
                if isinstance(d, str):
                    days_norm.append(d)
            return {"type": "weekly", "days": days_norm}
        return None
    return None

def buscar_habitos() -> List[Dict[str, Any]]:
    obj, _ = gh_get_file(saude_path("habits"))
    if not obj or not isinstance(obj, list):
        return []
    out = []
    for r in obj:
        if not isinstance(r, dict):
            continue
        rr = dict(r)
        try:
            rid = int(rr.get("id"))
        except Exception:
            continue
        name = (rr.get("name") or "").strip()
        try:
            tgt = int(rr.get("target_per_day", 0) or 0)
        except Exception:
            tgt = 0
        unit = rr.get("unit") or ""
        rec = _ensure_recurrence_dict_or_none(rr.get("recurrence"))
        out.append({"id": rid, "name": name, "target_per_day": tgt, "unit": unit, "recurrence": rec})
    return out

def inserir_habito(reg: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        new_id = (max([int(r.get("id", 0)) for r in obj if isinstance(r, dict)]) + 1) if obj else 1
        name = (reg.get("name") or "").strip()
        unit = (reg.get("unit") or "")
        try:
            target = int(reg.get("target_per_day", 0) or 0)
        except Exception:
            target = 0
        recurrence = _ensure_recurrence_dict_or_none(reg.get("recurrence"))
        obj.append({"id": new_id, "name": name, "unit": unit, "target_per_day": target, "recurrence": recurrence})
        return obj
    safe_update_json(saude_path("habits"), updater, commit_message="add habit")

def atualizar_habito(habit_id: int, patch: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        out = []
        for r in obj:
            if not isinstance(r, dict):
                continue
            rid = int(r.get("id", -1)) if r.get("id") is not None else -1
            if rid == int(habit_id):
                rr = dict(r)
                if "name" in patch:
                    rr["name"] = (patch.get("name") or "").strip()
                if "unit" in patch:
                    rr["unit"] = (patch.get("unit") or "")
                if "target_per_day" in patch:
                    try:
                        rr["target_per_day"] = int(patch.get("target_per_day", 0) or 0)
                    except Exception:
                        rr["target_per_day"] = 0
                if "recurrence" in patch:
                    rr["recurrence"] = _ensure_recurrence_dict_or_none(patch.get("recurrence"))
                rr.setdefault("target_per_day", 0)
                rr.setdefault("unit", "")
                rr.setdefault("recurrence", None)
                out.append(rr)
            else:
                out.append(r)
        return out
    safe_update_json(saude_path("habits"), updater, commit_message=f"update habit {habit_id}")

def deletar_habito(habit_id: int) -> None:
    def updater(obj):
        obj = obj or []
        return [r for r in obj if not (isinstance(r, dict) and int(r.get("id", -1)) == int(habit_id))]
    safe_update_json(saude_path("habits"), updater, commit_message=f"delete habit {habit_id}")

def buscar_habit_logs() -> List[Dict[str, Any]]:
    obj, _ = gh_get_file(saude_path("habit_logs"))
    if not obj or not isinstance(obj, list):
        return []
    out = []
    for r in obj:
        if not isinstance(r, dict):
            continue
        try:
            log_id = int(r.get("id"))
            habit_id = int(r.get("habit_id"))
        except Exception:
            continue
        date_str = r.get("date")
        try:
            amount = float(r.get("amount", 0) or 0)
        except Exception:
            amount = 0.0
        out.append({"id": log_id, "habit_id": habit_id, "date": date_str, "amount": amount})
    return out

def inserir_habit_log(reg: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        new_id = (max([int(r.get("id", 0)) for r in obj if isinstance(r, dict)]) + 1) if obj else 1
        try:
            habit_id = int(reg.get("habit_id"))
        except Exception:
            raise ValueError("habit_id inválido")
        date_str = reg.get("date")
        try:
            amount = float(reg.get("amount", 0) or 0)
        except Exception:
            amount = 0.0
        obj.append({"id": new_id, "habit_id": habit_id, "date": date_str, "amount": amount})
        return obj
    safe_update_json(saude_path("habit_logs"), updater, commit_message="add habit_log")

def atualizar_habit_log(log_id: int, patch: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        out = []
        for r in obj:
            if not isinstance(r, dict):
                continue
            rid = int(r.get("id", -1)) if r.get("id") is not None else -1
            if rid == int(log_id):
                rr = dict(r)
                if "habit_id" in patch:
                    try:
                        rr["habit_id"] = int(patch.get("habit_id"))
                    except Exception:
                        pass
                if "date" in patch:
                    rr["date"] = patch.get("date")
                if "amount" in patch:
                    try:
                        rr["amount"] = float(patch.get("amount", 0) or 0)
                    except Exception:
                        rr["amount"] = 0.0
                out.append(rr)
            else:
                out.append(r)
        return out
    safe_update_json(saude_path("habit_logs"), updater, commit_message=f"update habit_log {log_id}")

def deletar_habit_log(log_id: int) -> None:
    def updater(obj):
        obj = obj or []
        return [r for r in obj if not (isinstance(r, dict) and int(r.get("id", -1)) == int(log_id))]
    safe_update_json(saude_path("habit_logs"), updater, commit_message=f"delete habit_log {log_id}")

# =================================================
#          SAÚDE (NOVA): PESO / ÁGUA / TREINOS / CONFIG
# =================================================
def buscar_peso_logs() -> List[Dict[str, Any]]:
    obj, _ = gh_get_file(saude_path("weight_logs"))
    if not obj or not isinstance(obj, list):
        return []
    out = []
    for r in obj:
        if not isinstance(r, dict):
            continue
        try:
            rid = int(r.get("id"))
            w = float(r.get("weight_kg"))
        except Exception:
            continue
        out.append({
            "id": rid,
            "date": r.get("date"),
            "weight_kg": w,
            "body_fat_pct": float(r.get("body_fat_pct")) if r.get("body_fat_pct") not in (None, "") else None,
            "waist_cm": float(r.get("waist_cm")) if r.get("waist_cm") not in (None, "") else None,
        })
    return out

def inserir_peso(reg: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        new_id = (max([int(x.get("id", 0)) for x in obj if isinstance(x, dict)]) + 1) if obj else 1
        date_str = str(reg.get("date"))
        w = float(reg.get("weight_kg"))
        bf = reg.get("body_fat_pct")
        wc = reg.get("waist_cm")
        row = {"id": new_id, "date": date_str, "weight_kg": w}
        if bf not in (None, ""):
            row["body_fat_pct"] = float(bf)
        if wc not in (None, ""):
            row["waist_cm"] = float(wc)
        obj.append(row)
        return obj
    safe_update_json(saude_path("weight_logs"), updater, commit_message="add weight_log")

def atualizar_peso(log_id: int, patch: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        for r in obj:
            if isinstance(r, dict) and int(r.get("id", -1)) == int(log_id):
                if "date" in patch and patch["date"]:
                    r["date"] = str(patch["date"])
                if "weight_kg" in patch:
                    r["weight_kg"] = float(patch["weight_kg"])
                if "body_fat_pct" in patch:
                    r["body_fat_pct"] = float(patch["body_fat_pct"]) if patch["body_fat_pct"] not in (None, "") else None
                if "waist_cm" in patch:
                    r["waist_cm"] = float(patch["waist_cm"]) if patch["waist_cm"] not in (None, "") else None
        return obj
    safe_update_json(saude_path("weight_logs"), updater, commit_message=f"update weight_log {log_id}")

def deletar_peso(log_id: int) -> None:
    def updater(obj):
        obj = obj or []
        return [r for r in obj if not (isinstance(r, dict) and int(r.get("id", -1)) == int(log_id))]
    safe_update_json(saude_path("weight_logs"), updater, commit_message=f"delete weight_log {log_id}")

def buscar_agua_logs() -> List[Dict[str, Any]]:
    obj, _ = gh_get_file(saude_path("water_logs"))
    if not obj or not isinstance(obj, list):
        return []
    out = []
    for r in obj:
        if not isinstance(r, dict):
            continue
        try:
            rid = int(r.get("id"))
            amt = float(r.get("amount_ml"))
        except Exception:
            continue
        out.append({"id": rid, "date": r.get("date"), "amount_ml": amt})
    return out

def inserir_agua(reg: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        new_id = (max([int(x.get("id", 0)) for x in obj if isinstance(x, dict)]) + 1) if obj else 1
        date_str = str(reg.get("date"))
        amt = float(reg.get("amount_ml"))
        obj.append({"id": new_id, "date": date_str, "amount_ml": amt})
        return obj
    safe_update_json(saude_path("water_logs"), updater, commit_message="add water_log")

def atualizar_agua(log_id: int, patch: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        for r in obj:
            if isinstance(r, dict) and int(r.get("id", -1)) == int(log_id):
                if "date" in patch and patch["date"]:
                    r["date"] = str(patch["date"])
                if "amount_ml" in patch:
                    r["amount_ml"] = float(patch["amount_ml"])
        return obj
    safe_update_json(saude_path("water_logs"), updater, commit_message=f"update water_log {log_id}")

def deletar_agua(log_id: int) -> None:
    def updater(obj):
        obj = obj or []
        return [r for r in obj if not (isinstance(r, dict) and int(r.get("id", -1)) == int(log_id))]
    safe_update_json(saude_path("water_logs"), updater, commit_message=f"delete water_log {log_id}")

def buscar_saude_config() -> Dict[str, Any]:
    obj, _ = gh_get_file(saude_path("saude_config"))
    return obj if isinstance(obj, dict) else {}

def upsert_saude_config(patch: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or {}
        out = dict(obj)
        for k, v in patch.items():
            out[k] = v
        return out
    safe_update_json(saude_path("saude_config"), updater, commit_message="upsert saude_config")

def buscar_workout_logs() -> List[Dict[str, Any]]:
    obj, _ = gh_get_file(saude_path("workout_logs"))
    if not obj or not isinstance(obj, list):
        return []
    out = []
    for r in obj:
        if not isinstance(r, dict):
            continue
        try:
            rid = int(r.get("id"))
            reps = int(r.get("reps"))
            w = float(r.get("weight_kg") or 0.0)
        except Exception:
            continue
        out.append({
            "id": rid,
            "date": r.get("date"),
            "exercise": (r.get("exercise") or "").strip(),
            "reps": reps,
            "weight_kg": w,
            "rpe": float(r.get("rpe")) if r.get("rpe") not in (None, "") else None,
            "notes": r.get("notes") or ""
        })
    return out

def inserir_workout_log(reg: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        new_id = (max([int(x.get("id", 0)) for x in obj if isinstance(x, dict)]) + 1) if obj else 1
        row = {
            "id": new_id,
            "date": str(reg.get("date")),
            "exercise": (reg.get("exercise") or "").strip(),
            "reps": int(reg.get("reps")),
            "weight_kg": float(reg.get("weight_kg") or 0.0),
            "notes": (reg.get("notes") or "").strip()
        }
        if reg.get("rpe") not in (None, ""):
            row["rpe"] = float(reg.get("rpe"))
        obj.append(row)
        return obj
    safe_update_json(saude_path("workout_logs"), updater, commit_message="add workout_log")

def atualizar_workout_log(log_id: int, patch: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        for r in obj:
            if isinstance(r, dict) and int(r.get("id", -1)) == int(log_id):
                if "date" in patch and patch["date"]:
                    r["date"] = str(patch["date"])
                if "exercise" in patch:
                    r["exercise"] = (patch["exercise"] or "").strip()
                if "reps" in patch:
                    r["reps"] = int(patch["reps"])
                if "weight_kg" in patch:
                    r["weight_kg"] = float(patch["weight_kg"])
                if "rpe" in patch:
                    r["rpe"] = float(patch["rpe"]) if patch["rpe"] not in (None, "") else None
                if "notes" in patch:
                    r["notes"] = (patch["notes"] or "").strip()
        return obj
    safe_update_json(saude_path("workout_logs"), updater, commit_message=f"update workout_log {log_id}")

def deletar_workout_log(log_id: int) -> None:
    def updater(obj):
        obj = obj or []
        return [r for r in obj if not (isinstance(r, dict) and int(r.get("id", -1)) == int(log_id))]
    safe_update_json(saude_path("workout_logs"), updater, commit_message=f"delete workout_log {log_id}")

# =================================================
#            ESTUDOS (NOVO - SIMPLES + ESTÍMULO)
#   subjects.json | topics.json | study_logs.json
# =================================================
def buscar_estudos_subjects() -> List[Dict[str, Any]]:
    obj, _ = gh_get_file(estudos_path("subjects"))
    return obj if isinstance(obj, list) else []

def buscar_estudos_topics() -> List[Dict[str, Any]]:
    obj, _ = gh_get_file(estudos_path("topics"))
    return obj if isinstance(obj, list) else []

def buscar_estudos_logs() -> List[Dict[str, Any]]:
    obj, _ = gh_get_file(estudos_path("study_logs"))
    return obj if isinstance(obj, list) else []

def inserir_estudos_subject(reg: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        new_id = (max([int(r.get("id", 0)) for r in obj if isinstance(r, dict)]) + 1) if obj else 1

        name = (reg.get("name") or "").strip()
        if not name:
            raise ValueError("name inválido")

        try:
            order = int(reg.get("order", len(obj) + 1) or (len(obj) + 1))
        except Exception:
            order = len(obj) + 1

        obj.append({"id": new_id, "name": name, "order": order})
        return obj

    safe_update_json(estudos_path("subjects"), updater, commit_message="add estudos subject")

def atualizar_estudos_subject(subject_id: int, patch: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        for r in obj:
            if isinstance(r, dict) and int(r.get("id", -1)) == int(subject_id):
                if "name" in patch:
                    r["name"] = (patch.get("name") or "").strip()
                if "order" in patch:
                    try:
                        r["order"] = int(patch.get("order"))
                    except Exception:
                        pass
        return obj

    safe_update_json(estudos_path("subjects"), updater, commit_message=f"update estudos subject {subject_id}")

def deletar_estudos_subject(subject_id: int) -> None:
    def upd_sub(obj):
        obj = obj or []
        return [r for r in obj if not (isinstance(r, dict) and int(r.get("id", -1)) == int(subject_id))]

    safe_update_json(estudos_path("subjects"), upd_sub, commit_message=f"delete estudos subject {subject_id}")

    def upd_topics(obj):
        obj = obj or []
        return [t for t in obj if not (isinstance(t, dict) and int(t.get("subject_id", -1)) == int(subject_id))]

    safe_update_json(estudos_path("topics"), upd_topics, commit_message=f"delete topics from subject {subject_id}")

def inserir_estudos_topic(reg: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        new_id = (max([int(r.get("id", 0)) for r in obj if isinstance(r, dict)]) + 1) if obj else 1
        now = datetime.utcnow().isoformat() + "Z"

        try:
            subject_id = int(reg.get("subject_id"))
        except Exception:
            raise ValueError("subject_id inválido")

        title = (reg.get("title") or "").strip()
        if not title:
            raise ValueError("title inválido")

        # order padrão: último dentro da matéria
        try:
            default_order = 1
            same = [x for x in obj if isinstance(x, dict) and int(x.get("subject_id", -1)) == subject_id]
            if same:
                default_order = max([int(x.get("order", 0) or 0) for x in same]) + 1
            order = int(reg.get("order", default_order) or default_order)
        except Exception:
            order = 9999

        status = (reg.get("status") or "todo").strip()
        if status not in ("todo", "doing", "done"):
            status = "todo"

        planned_date = reg.get("planned_date", None)

        planned_weekdays = reg.get("planned_weekdays") or []
        if not isinstance(planned_weekdays, list):
            planned_weekdays = []
        wk: List[int] = []
        for v in planned_weekdays:
            try:
                iv = int(v)
                if 0 <= iv <= 6:
                    wk.append(iv)
            except Exception:
                pass

        row = {
            "id": new_id,
            "subject_id": subject_id,
            "title": title,
            "order": order,
            "status": status,
            "planned_date": planned_date,
            "planned_weekdays": wk,
            "notes": reg.get("notes") or "",
            "review": bool(reg.get("review", False)),
            "active": True if reg.get("active") is None else bool(reg.get("active")),
            "last_studied_at": reg.get("last_studied_at"),
            "created_at": now,
            "updated_at": now,
        }

        obj.append(row)
        return obj

    safe_update_json(estudos_path("topics"), updater, commit_message="add estudos topic")

def atualizar_estudos_topic(topic_id: int, patch: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        now = datetime.utcnow().isoformat() + "Z"

        for r in obj:
            if isinstance(r, dict) and int(r.get("id", -1)) == int(topic_id):
                for k, v in patch.items():
                    if k == "status":
                        vv = (v or "").strip()
                        if vv in ("todo", "doing", "done"):
                            r[k] = vv
                    elif k == "planned_weekdays":
                        lst = v if isinstance(v, list) else []
                        wk: List[int] = []
                        for x in lst:
                            try:
                                ix = int(x)
                                if 0 <= ix <= 6:
                                    wk.append(ix)
                            except Exception:
                                pass
                        r[k] = wk
                    elif k in ("order", "subject_id"):
                        try:
                            r[k] = int(v)
                        except Exception:
                            pass
                    elif k in ("review", "active"):
                        r[k] = bool(v)
                    else:
                        r[k] = v

                r["updated_at"] = now

        return obj

    safe_update_json(estudos_path("topics"), updater, commit_message=f"update estudos topic {topic_id}")

def deletar_estudos_topic(topic_id: int) -> None:
    def updater(obj):
        obj = obj or []
        return [r for r in obj if not (isinstance(r, dict) and int(r.get("id", -1)) == int(topic_id))]

    safe_update_json(estudos_path("topics"), updater, commit_message=f"delete estudos topic {topic_id}")

def inserir_estudos_log(reg: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        new_id = (max([int(r.get("id", 0)) for r in obj if isinstance(r, dict)]) + 1) if obj else 1

        try:
            topic_id = int(reg.get("topic_id"))
        except Exception:
            raise ValueError("topic_id inválido")

        duration = reg.get("duration_min", 0)
        try:
            duration = int(duration)
        except Exception:
            duration = 0
        if duration < 0:
            duration = 0

        result = (reg.get("result") or "partial").strip()
        if result not in ("all", "partial", "review"):
            result = "partial"

        row = {
            "id": new_id,
            "topic_id": topic_id,
            "start_at": reg.get("start_at"),
            "end_at": reg.get("end_at"),
            "duration_min": duration,
            "result": result,
            "counts_for_streak": bool(duration >= 10),
        }

        obj.append(row)
        return obj

    safe_update_json(estudos_path("study_logs"), updater, commit_message="add estudos study_log")

# =================================================
#          SAÚDE (PAINEL): PERFIL / REFEIÇÕES / HÁBITOS / ATIVIDADES
# =================================================
def saude_profile_path() -> str:
    return saude_path("profile")

def saude_meals_path() -> str:
    return saude_path("meals")

def saude_habits_path() -> str:
    return saude_path("habit_checks")

def saude_activity_path() -> str:
    return saude_path("activity_logs")

# --------- PERFIL ----------
def buscar_saude_profile() -> Dict[str, Any]:
    obj, _ = gh_get_file(saude_profile_path())
    return obj if isinstance(obj, dict) else {}

def upsert_saude_profile(patch: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or {}
        out = dict(obj)
        out.update(patch)
        return out
    safe_update_json(saude_profile_path(), updater, commit_message="upsert saude profile")

# --------- REFEIÇÕES ----------
def buscar_meals() -> List[Dict[str, Any]]:
    obj, _ = gh_get_file(saude_meals_path())
    return obj if isinstance(obj, list) else []

def inserir_meal(reg: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        new_id = (max([int(r.get("id", 0)) for r in obj if isinstance(r, dict)]) + 1) if obj else 1
        row = {
            "id": new_id,
            "date": str(reg.get("date")),
            "meal": (reg.get("meal") or "").strip(),
            "quality": (reg.get("quality") or "").strip(),
            "notes": (reg.get("notes") or "").strip()
        }
        obj.append(row)
        return obj
    safe_update_json(saude_meals_path(), updater, commit_message="add meal")

def atualizar_meal(meal_id: int, patch: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        for r in obj:
            if isinstance(r, dict) and int(r.get("id", -1)) == int(meal_id):
                r.update(dict(patch))
        return obj
    safe_update_json(saude_meals_path(), updater, commit_message=f"update meal {meal_id}")

def deletar_meal(meal_id: int) -> None:
    def updater(obj):
        obj = obj or []
        return [r for r in obj if not (isinstance(r, dict) and int(r.get("id", -1)) == int(meal_id))]
    safe_update_json(saude_meals_path(), updater, commit_message=f"delete meal {meal_id}")

# --------- HÁBITOS (1 registro por dia) ----------
def buscar_habit_checks() -> List[Dict[str, Any]]:
    obj, _ = gh_get_file(saude_habits_path())
    return obj if isinstance(obj, list) else []

def upsert_habit_check(date_str: str, patch: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        found = None
        for r in obj:
            if isinstance(r, dict) and str(r.get("date")) == date_str:
                found = r
                break
        if found is None:
            new_id = (max([int(r.get("id", 0)) for r in obj if isinstance(r, dict)]) + 1) if obj else 1
            found = {"id": new_id, "date": date_str, "water_done": False, "move_done": False, "sleep_done": False}
            obj.append(found)

        found.update(dict(patch))
        return obj

    safe_update_json(saude_habits_path(), updater, commit_message=f"upsert habit_check {date_str}")

# --------- ATIVIDADES (movimento simples) ----------
def buscar_activity_logs() -> List[Dict[str, Any]]:
    obj, _ = gh_get_file(saude_activity_path())
    return obj if isinstance(obj, list) else []

def inserir_activity_log(reg: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        new_id = (max([int(r.get("id", 0)) for r in obj if isinstance(r, dict)]) + 1) if obj else 1
        row = {
            "id": new_id,
            "date": str(reg.get("date")),
            "activity": (reg.get("activity") or "").strip(),
            "minutes": int(reg.get("minutes") or 0),
            "intensity": (reg.get("intensity") or "leve").strip()
        }
        obj.append(row)
        return obj
    safe_update_json(saude_activity_path(), updater, commit_message="add activity_log")

def deletar_activity_log(log_id: int) -> None:
    def updater(obj):
        obj = obj or []
        return [r for r in obj if not (isinstance(r, dict) and int(r.get("id", -1)) == int(log_id))]
    safe_update_json(saude_activity_path(), updater, commit_message=f"delete activity_log {log_id}")
