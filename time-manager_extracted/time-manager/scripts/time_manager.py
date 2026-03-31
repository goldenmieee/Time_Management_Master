#!/usr/bin/env python3
"""
time_manager.py — 主人公时间存档器

存储：JSON 文件（schedule.json）
设计原则：agent-friendly CLI
  - 所有业务输出走 stdout（human-readable 或 --json 模式输出机器可读 JSON）
  - 错误信息走 stderr
  - exit code：0=成功，1=业务错误，2=参数错误

用法：
  time_manager.py add-json '{"start":"2025-04-05 19:00","end":"2025-04-05 21:00","person":"小雨","location":"三里屯","task":"见面喝咖啡"}'
  time_manager.py list [--from YYYY-MM-DD] [--to YYYY-MM-DD] [--person 名字] [--json]
  time_manager.py free [--date YYYY-MM-DD] [--min 分钟] [--json]
  time_manager.py suggest --person 名字 [--duration 分钟] [--json]
  time_manager.py analyze [--json]
  time_manager.py delete <id>

--json 标志：所有命令均支持，输出纯 JSON，供 agent 解析。
"""

import json
import argparse
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

# ── 路径配置 ──────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
DATA_DIR   = SCRIPT_DIR.parent / "data"
DB_FILE    = DATA_DIR / "schedule.json"

# ── 存储层 ────────────────────────────────────────────────

def load_db() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not DB_FILE.exists():
        db = {"events": [], "_next_id": 1}
        save_db(db)
        return db
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_db(db: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

def active_events(db: dict) -> list:
    return [e for e in db["events"] if e.get("status") != "cancelled"]

# ── 时间工具 ──────────────────────────────────────────────

FMT = "%Y-%m-%d %H:%M"

def parse_dt(s: str) -> datetime:
    try:
        return datetime.strptime(s, FMT)
    except ValueError:
        err(f"时间格式错误，需要 YYYY-MM-DD HH:MM，收到：{s!r}")
        sys.exit(2)

def fmt_dt(dt: datetime) -> str:
    return dt.strftime(FMT)

def weekday_cn(dt: datetime) -> str:
    return ["周一","周二","周三","周四","周五","周六","周日"][dt.weekday()]

# ── 输出工具 ──────────────────────────────────────────────

def err(msg: str):
    """错误走 stderr，不污染 stdout"""
    print(f"❌ {msg}", file=sys.stderr)

def out(msg: str):
    print(msg)

def out_json(data):
    print(json.dumps(data, ensure_ascii=False, indent=2))

# ── 冲突检测 ──────────────────────────────────────────────

def find_conflicts(db: dict, start: datetime, end: datetime, exclude_id=None) -> list:
    conflicts = []
    for e in active_events(db):
        if exclude_id and e["id"] == exclude_id:
            continue
        e_start = parse_dt(e["start"])
        e_end   = parse_dt(e["end"])
        if e_start < end and e_end > start:
            conflicts.append(e)
    return conflicts

# ── 命令：add-json ────────────────────────────────────────

def cmd_add_json(args):
    try:
        data = json.loads(args.json_data)
    except json.JSONDecodeError as e:
        err(f"JSON 解析失败: {e}")
        sys.exit(2)

    for field in ["start", "end", "task"]:
        if field not in data:
            err(f"缺少必填字段: {field}")
            sys.exit(2)

    start = parse_dt(data["start"])
    end   = parse_dt(data["end"])
    if end <= start:
        err("结束时间必须晚于开始时间")
        sys.exit(1)

    db        = load_db()
    conflicts = find_conflicts(db, start, end)

    event = {
        "id":         db["_next_id"],
        "start":      fmt_dt(start),
        "end":        fmt_dt(end),
        "person":     data.get("person", ""),
        "location":   data.get("location", ""),
        "task":       data["task"],
        "notes":      data.get("notes", ""),
        "status":     data.get("status", "confirmed"),
        "created_at": fmt_dt(datetime.now()),
    }

    db["events"].append(event)
    db["_next_id"] += 1
    save_db(db)

    if args.json:
        out_json({
            "ok": True,
            "event": event,
            "conflicts": conflicts,
        })
    else:
        out(f"✅ 已记录 [ID:{event['id']}] {event['start']} ~ {event['end'][11:]} | "
            f"{event['person'] or '—'} | {event['location'] or '—'} | {event['task']}")
        if conflicts:
            out("⚠️  注意：与以下日程冲突：")
            for c in conflicts:
                out(f"   [{c['id']}] {c['start']} ~ {c['end'][11:]} | {c['person'] or '—'} | {c['task']}")

# ── 命令：list ────────────────────────────────────────────

def cmd_list(args):
    db     = load_db()
    events = active_events(db)

    if args.from_date:
        events = [e for e in events if e["start"] >= args.from_date + " 00:00"]
    if args.to_date:
        events = [e for e in events if e["start"] <= args.to_date + " 23:59"]
    if args.person:
        events = [e for e in events if args.person in e.get("person", "")]

    events.sort(key=lambda e: e["start"])

    if args.json:
        out_json({"events": events, "count": len(events)})
        return

    if not events:
        out("📭 暂无日程")
        return

    out(f"\n📅 共 {len(events)} 条日程：")
    out("─" * 60)
    for e in events:
        person_str   = f"👤 {e['person']}"   if e['person']   else ""
        location_str = f"📍 {e['location']}" if e['location'] else ""
        start_dt = parse_dt(e["start"])
        out(f"[{e['id']:3d}] {e['start']} ~ {e['end'][11:]}（{weekday_cn(start_dt)}）")
        out(f"      📌 {e['task']}  {person_str}  {location_str}")
        if e.get("notes"):
            out(f"      💬 {e['notes']}")
    out("─" * 60)

# ── 命令：free ────────────────────────────────────────────

def cmd_free(args):
    db          = load_db()
    min_dur     = args.min
    work_start  = "09:00"
    work_end    = "23:00"

    if args.date:
        dates = [args.date]
    else:
        today = datetime.now().date()
        dates = [(today + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]

    result = {}
    for date in dates:
        day_start = parse_dt(f"{date} {work_start}")
        day_end   = parse_dt(f"{date} {work_end}")

        busy = []
        for e in active_events(db):
            e_start = parse_dt(e["start"])
            e_end   = parse_dt(e["end"])
            if e_start < day_end and e_end > day_start:
                busy.append((max(e_start, day_start), min(e_end, day_end)))
        busy.sort()

        free_slots = []
        cursor = day_start
        for b_start, b_end in busy:
            if cursor < b_start:
                dur = int((b_start - cursor).total_seconds() // 60)
                if dur >= min_dur:
                    free_slots.append({
                        "start": fmt_dt(cursor),
                        "end":   fmt_dt(b_start),
                        "duration_min": dur,
                    })
            cursor = max(cursor, b_end)
        if cursor < day_end:
            dur = int((day_end - cursor).total_seconds() // 60)
            if dur >= min_dur:
                free_slots.append({
                    "start": fmt_dt(cursor),
                    "end":   fmt_dt(day_end),
                    "duration_min": dur,
                })

        if free_slots:
            result[date] = free_slots

    if args.json:
        out_json({"free_slots": result, "min_duration_min": min_dur})
        return

    if not result:
        out(f"😵 没有找到 ≥{min_dur} 分钟的空闲时段")
        return

    out(f"\n🆓 空闲时段（≥{min_dur}分钟）：")
    out("─" * 50)
    for date, slots in sorted(result.items()):
        dt = datetime.strptime(date, "%Y-%m-%d")
        out(f"\n  📆 {date}（{weekday_cn(dt)}）")
        for s in slots:
            out(f"     {s['start'][11:]} ~ {s['end'][11:]}  ({s['duration_min']}分钟)")
    out("─" * 50)

# ── 命令：suggest ─────────────────────────────────────────

def cmd_suggest(args):
    db       = load_db()
    duration = args.duration
    person   = args.person
    today    = datetime.now().date()
    dates    = [(today + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(14)]

    # 优先傍晚（18:00~23:00），其次下午（14:00~23:00）
    windows = [("18:00", "23:00"), ("14:00", "18:00")]

    candidates = []
    for date in dates:
        for w_start_str, w_end_str in windows:
            w_start = parse_dt(f"{date} {w_start_str}")
            w_end   = parse_dt(f"{date} {w_end_str}")

            # 这天的忙碌时段
            busy = []
            for e in active_events(db):
                e_start = parse_dt(e["start"])
                e_end   = parse_dt(e["end"])
                if e_start < w_end and e_end > w_start:
                    busy.append((max(e_start, w_start), min(e_end, w_end)))
            busy.sort()

            cursor = w_start
            slot_found = False
            for b_start, b_end in busy:
                if cursor + timedelta(minutes=duration) <= b_start:
                    candidates.append({
                        "start":    fmt_dt(cursor),
                        "end":      fmt_dt(cursor + timedelta(minutes=duration)),
                        "date":     date,
                        "weekday":  weekday_cn(parse_dt(f"{date} 00:00")),
                        "priority": "evening" if w_start_str == "18:00" else "afternoon",
                    })
                    slot_found = True
                    break
                cursor = max(cursor, b_end)
            if not slot_found and cursor + timedelta(minutes=duration) <= w_end:
                candidates.append({
                    "start":    fmt_dt(cursor),
                    "end":      fmt_dt(cursor + timedelta(minutes=duration)),
                    "date":     date,
                    "weekday":  weekday_cn(parse_dt(f"{date} 00:00")),
                    "priority": "evening" if w_start_str == "18:00" else "afternoon",
                })

    # 傍晚优先，取前3
    candidates.sort(key=lambda x: (0 if x["priority"] == "evening" else 1, x["start"]))
    top3 = candidates[:3]

    if args.json:
        out_json({
            "person":      person,
            "duration_min": duration,
            "suggestions": top3,
        })
        return

    if not top3:
        out("😵 未来两周没找到合适的空档")
        return

    person_str = f"和 {person} " if person else ""
    out(f"\n💡 推荐见面时间（{person_str}约 {duration} 分钟）：")
    out("─" * 50)
    for i, s in enumerate(top3, 1):
        tag = "🌆" if s["priority"] == "evening" else "☀️"
        out(f"  {i}. {s['date']}（{s['weekday']}）{s['start'][11:]} ~ {s['end'][11:]}  {tag}")
    out("─" * 50)

# ── 命令：analyze ─────────────────────────────────────────

def cmd_analyze(args):
    db    = load_db()
    today = datetime.now().date()
    mon   = today - timedelta(days=today.weekday())
    sun   = mon + timedelta(days=6)

    week_events = [
        e for e in active_events(db)
        if mon.strftime("%Y-%m-%d") <= e["start"][:10] <= sun.strftime("%Y-%m-%d")
    ]
    week_events.sort(key=lambda e: e["start"])

    total_min = 0
    person_min = {}
    for e in week_events:
        dur = int((parse_dt(e["end"]) - parse_dt(e["start"])).total_seconds() // 60)
        total_min += dur
        for p in (e.get("person") or "").split(","):
            p = p.strip()
            if p:
                person_min[p] = person_min.get(p, 0) + dur

    if args.json:
        out_json({
            "week": f"{mon} ~ {sun}",
            "event_count": len(week_events),
            "total_minutes": total_min,
            "person_breakdown": person_min,
            "events": week_events,
        })
        return

    out(f"\n📊 本周时间分析（{mon} ~ {sun}）")
    out("─" * 50)
    out(f"  📅 共 {len(week_events)} 个日程，占用 {total_min//60}h{total_min%60}m")
    if person_min:
        out("\n  👤 按人分配：")
        for p, m in sorted(person_min.items(), key=lambda x: -x[1]):
            out(f"     {p}: {m//60}h{m%60}m")
    if week_events:
        out("\n  📋 本周日程：")
        for e in week_events:
            out(f"     {e['start'][5:]} ~ {e['end'][11:]} | {e['person'] or '—'} | {e['task']}")
    out("─" * 50)

# ── 命令：delete ──────────────────────────────────────────

def cmd_delete(args):
    db = load_db()
    target = next((e for e in db["events"] if e["id"] == args.id), None)
    if not target:
        err(f"找不到 ID={args.id} 的日程")
        sys.exit(1)

    target["status"] = "cancelled"
    save_db(db)

    if args.json:
        out_json({"ok": True, "deleted_id": args.id})
    else:
        out(f"✅ 已删除 [ID:{args.id}] {target['start']} | {target['person'] or '—'} | {target['task']}")

# ── CLI 入口 ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="主人公时间存档器 — agent-friendly CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON（供 agent 解析）")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # add-json
    p = sub.add_parser("add-json", help="新增日程（JSON输入）")
    p.add_argument("json_data", help='JSON: {"start","end","task","person","location","notes"}')
    p.add_argument("--json", action="store_true")

    # list
    p = sub.add_parser("list", help="列出日程")
    p.add_argument("--from", dest="from_date")
    p.add_argument("--to",   dest="to_date")
    p.add_argument("--person")
    p.add_argument("--json", action="store_true")

    # free
    p = sub.add_parser("free", help="查看空闲时段")
    p.add_argument("--date")
    p.add_argument("--min", type=int, default=60, dest="min")
    p.add_argument("--json", action="store_true")

    # suggest
    p = sub.add_parser("suggest", help="推荐见面时间")
    p.add_argument("--person", default="")
    p.add_argument("--duration", type=int, default=120)
    p.add_argument("--json", action="store_true")

    # analyze
    p = sub.add_parser("analyze", help="本周时间分析")
    p.add_argument("--json", action="store_true")

    # delete
    p = sub.add_parser("delete", help="删除日程")
    p.add_argument("id", type=int)
    p.add_argument("--json", action="store_true")

    args = parser.parse_args()

    dispatch = {
        "add-json": cmd_add_json,
        "list":     cmd_list,
        "free":     cmd_free,
        "suggest":  cmd_suggest,
        "analyze":  cmd_analyze,
        "delete":   cmd_delete,
    }
    dispatch[args.cmd](args)

if __name__ == "__main__":
    main()
