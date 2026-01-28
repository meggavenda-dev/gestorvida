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
    # Garante JSON-serializável
    content_str = json.dumps(obj, ensure_ascii=False, indent=2)
    content_b64 = base64.b64encode(content_str.encode("utf-8")).decode("utf-8")

    payload = {"message": message or f"update {path}", "content": content_b64, "branch": branch}
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
    Lê (obj, sha) -> aplica updater(obj) -> grava com sha -> retry em caso de conflito/falha.
    """
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
        time.sleep(delay)
    st.error(f"[GitHub] Não foi possível atualizar {path} após {max_retries} tentativas.")
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
        new_id = (max([int(r.get("id", 0)) for r in obj if isinstance(r, dict)]) + 1) if obj else 1
        reg = dict(reg)
        reg['id'] = new_id
        obj.append(reg)
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
        return pd.DataFrame(columns=['id','descricao','valor','categoria','responsavel'])
    df = pd.DataFrame(obj)
    if 'responsavel' not in df.columns: df['responsavel'] = 'Ambos'
    df['responsavel'] = df['responsavel'].fillna('Ambos').astype(str)
    return df

def inserir_fixo(reg: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        new_id = (max([int(r.get("id", 0)) for r in obj if isinstance(r, dict)]) + 1) if obj else 1
        reg = dict(reg); reg['id'] = new_id
        obj.append(reg)
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
def buscar_tasks() -> List[Dict[str, Any]]:
    obj, _ = gh_get_file(tasks_path("tasks"))
    return obj if isinstance(obj, list) else []

def inserir_task(reg: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        new_id = (max([int(r.get("id", 0)) for r in obj if isinstance(r, dict)]) + 1) if obj else 1
        reg = dict(reg); reg['id'] = new_id
        reg.setdefault('status', 'todo'); reg.setdefault('assignee', 'Ambos')
        obj.append(reg)
        return obj
    safe_update_json(tasks_path("tasks"), updater, commit_message="add task")

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
# --------- PESO ----------
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
        if bf not in (None, ""): row["body_fat_pct"] = float(bf)
        if wc not in (None, ""): row["waist_cm"] = float(wc)
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

# --------- ÁGUA ----------
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

# --------- CONFIG (ex.: meta de água) ----------
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

# --------- TREINOS (logs simples de séries) ----------
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
#                      ESTUDOS
# =================================================
def buscar_subjects() -> List[Dict[str, Any]]:
    obj, _ = gh_get_file(estudos_path("subjects"))
    return obj if isinstance(obj, list) else []

def inserir_subject(reg: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        new_id = (max([int(r.get("id", 0)) for r in obj if isinstance(r, dict)]) + 1) if obj else 1
        reg = dict(reg); reg['id'] = new_id
        obj.append(reg)
        return obj
    safe_update_json(estudos_path("subjects"), updater, commit_message="add subject")

def atualizar_subject(subject_id: int, patch: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        for r in obj:
            if isinstance(r, dict) and int(r.get("id", -1)) == int(subject_id):
                r.update(dict(patch))
        return obj
    safe_update_json(estudos_path("subjects"), updater, commit_message=f"update subject {subject_id}")

def deletar_subject(subject_id: int) -> None:
    def updater(obj):
        obj = obj or []
        return [r for r in obj if not (isinstance(r, dict) and int(r.get("id", -1)) == int(subject_id))]
    safe_update_json(estudos_path("subjects"), updater, commit_message=f"delete subject {subject_id}")

def buscar_materials() -> List[Dict[str, Any]]:
    obj, _ = gh_get_file(estudos_path("materials"))
    return obj if isinstance(obj, list) else []

def inserir_material(reg: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        new_id = (max([int(r.get("id", 0)) for r in obj if isinstance(r, dict)]) + 1) if obj else 1
        reg = dict(reg); reg['id'] = new_id
        obj.append(reg)
        return obj
    safe_update_json(estudos_path("materials"), updater, commit_message="add material")

def atualizar_material(material_id: int, patch: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        for r in obj:
            if isinstance(r, dict) and int(r.get("id", -1)) == int(material_id):
                r.update(dict(patch))
        return obj
    safe_update_json(estudos_path("materials"), updater, commit_message=f"update material {material_id}")

def deletar_material(material_id: int) -> None:
    def updater(obj):
        obj = obj or []
        return [r for r in obj if not (isinstance(r, dict) and int(r.get("id", -1)) == int(material_id))]
    safe_update_json(estudos_path("materials"), updater, commit_message=f"delete material {material_id}")

def buscar_flashcards() -> List[Dict[str, Any]]:
    obj, _ = gh_get_file(estudos_path("flashcards"))
    return obj if isinstance(obj, list) else []

def inserir_flashcard(reg: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        new_id = (max([int(r.get("id", 0)) for r in obj if isinstance(r, dict)]) + 1) if obj else 1
        reg = dict(reg); reg['id'] = new_id
        reg.setdefault('easiness', 2.5); reg.setdefault('interval_days', 1)
        reg.setdefault('due_date', str(date.today()))
        obj.append(reg)
        return obj
    safe_update_json(estudos_path("flashcards"), updater, commit_message="add flashcard")

def atualizar_flashcard(card_id: int, patch: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        for r in obj:
            if isinstance(r, dict) and int(r.get("id", -1)) == int(card_id):
                r.update(dict(patch))
        return obj
    safe_update_json(estudos_path("flashcards"), updater, commit_message=f"update flashcard {card_id}")

def deletar_flashcard(card_id: int) -> None:
    def updater(obj):
        obj = obj or []
        return [r for r in obj if not (isinstance(r, dict) and int(r.get("id", -1)) == int(card_id))]
    safe_update_json(estudos_path("flashcards"), updater, commit_message=f"delete flashcard {card_id}")

def buscar_sessions() -> List[Dict[str, Any]]:
    obj, _ = gh_get_file(estudos_path("sessions"))
    return obj if isinstance(obj, list) else []

def inserir_session(reg: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        new_id = (max([int(r.get("id", 0)) for r in obj if isinstance(r, dict)]) + 1) if obj else 1
        reg = dict(reg); reg['id'] = new_id
        obj.append(reg)
        return obj
    safe_update_json(estudos_path("sessions"), updater, commit_message="add study session")

def atualizar_session(session_id: int, patch: Dict[str, Any]) -> None:
    def updater(obj):
        obj = obj or []
        for r in obj:
            if isinstance(r, dict) and int(r.get("id", -1)) == int(session_id):
                r.update(dict(patch))
        return obj
    safe_update_json(estudos_path("sessions"), updater, commit_message=f"update study session {session_id}")

def deletar_session(session_id: int) -> None:
    def updater(obj):
        obj = obj or []
        return [r for r in obj if not (isinstance(r, dict) and int(r.get("id", -1)) == int(session_id))]
    safe_update_json(estudos_path("sessions"), updater, commit_message=f"delete study session {session_id}")
