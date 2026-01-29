# nlp_pt.py
# -*- coding: utf-8 -*-
from __future__ import annotations
from datetime import datetime, timedelta, date, time
import re

WEEKDAYS = {
    'segunda': 0, 'seg': 0,
    'terça': 1, 'terca': 1, 'ter': 1,
    'quarta': 2, 'qua': 2,
    'quinta': 3, 'qui': 3,
    'sexta': 4, 'sex': 4,
    'sábado': 5, 'sabado': 5, 'sab': 5,
    'domingo': 6, 'dom': 6,
}

TAG_PATTERN = re.compile(r"(?P<tag>#[\w-]+)")

def _next_weekday(base: date, wd: int) -> date:
    delta = (wd - base.weekday()) % 7
    return base + timedelta(days=delta or 7)

def _extract_time(text: str):
    """Retorna (time, span) ou None.
    Padrões: 15h, 15h30, 15:30, às 9h, as 09:05
    """
    # 1) HH:MM
    m = re.search(r"(\b\d{1,2}):(\d{2})\b", text)
    if m:
        hh = int(m.group(1)); mm = int(m.group(2))
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return time(hh, mm), m.span()
    # 2) HHhMM ou HHh
    m = re.search(r"\b(\d{1,2})h(\d{2})?\b", text, re.IGNORECASE)
    if m:
        hh = int(m.group(1)); mm = int(m.group(2) or 0)
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return time(hh, mm), m.span()
    # 3) às HHh / as HH:MM
    m = re.search(r"\b(?:às|as)\s*(\d{1,2})(?::(\d{2}))?h?\b", text, re.IGNORECASE)
    if m:
        hh = int(m.group(1)); mm = int(m.group(2) or 0)
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return time(hh, mm), m.span()
    return None

def _extract_date(text: str, base: date):
    t = text.lower()
    if 'depois de amanhã' in t:
        return base + timedelta(days=2)
    if 'amanhã' in t or 'amanha' in t:
        return base + timedelta(days=1)
    if 'hoje' in t:
        return base
    # dia da semana
    for k, wd in WEEKDAYS.items():
        if re.search(rf"\b{k}\b", t):
            return _next_weekday(base, wd)
    # dd/mm(/yyyy)
    m = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{4}))?\b", t)
    if m:
        d = int(m.group(1)); mth = int(m.group(2)); yy = int(m.group(3) or base.year)
        try:
            return date(yy, mth, d)
        except Exception:
            pass
    # em X dias
    m2 = re.search(r"\bem\s+(\d{1,2})\s+dias?\b", t)
    if m2:
        return base + timedelta(days=int(m2.group(1)))
    return None

def _extract_tags(text: str):
    tags = []
    def repl(m):
        tags.append(m.group('tag')[1:].lower())
        return ''
    clean = TAG_PATTERN.sub(repl, text).strip()
    return clean, tags

def parse_quick_entry(text: str, now: datetime | None = None) -> dict:
    """
    Interpreta entrada livre e retorna dict para inserir_task():
    - Se hora -> evento (start_at)
    - Se data -> tarefa (due_at)
    - Sem data/hora -> tarefa sem data
    - Extrai #tags
    """
    now = now or datetime.now()
    base = now.date()
    raw = (text or '').strip()
    # tags
    title, tags = _extract_tags(raw)

    # hora
    tm = _extract_time(title)
    found_time = None
    if tm:
        found_time, span = tm
        title = (title[:span[0]] + title[span[1]:]).strip(',; .')

    # data
    d = _extract_date(title, base)
    if d:
        title = re.sub(r"\b(hoje|amanhã|amanha|depois de amanhã|segunda|terça|terca|quarta|quinta|sexta|sábado|sabado|domingo|seg|ter|qua|qui|sex|sab|dom)\b",
                       '', title, flags=re.IGNORECASE).strip(',; .')
        title = re.sub(r"\b\d{1,2}/\d{1,2}(?:/\d{4})?\b", '', title).strip(',; .')

    if found_time and not d:
        d = base  # hora sem data => hoje

    payload = {
        'title': title or 'Tarefa',
        'description': '',
        'assignee': 'Ambos',
        'status': 'todo',
        'priority': 'normal',
        'tags': tags,
        'recurrence': None,
        'due_at': None,
        'start_at': None,
        'type': 'task',
    }

    if found_time:
        start_dt = datetime.combine(d or base, found_time)
        payload.update({'type': 'event', 'start_at': start_dt.isoformat(), 'due_at': None})
    else:
        payload.update({'type': 'task', 'due_at': (d.isoformat() if d else None), 'start_at': None})

    return payload
