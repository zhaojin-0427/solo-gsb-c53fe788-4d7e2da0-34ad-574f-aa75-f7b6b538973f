"""相容性规则引擎。

判定逻辑：
- 每条规则带 JSON 条件（cond），按化学品标签、浓度、温度、容器材质、事件类型匹配。
- 命中 action=forbid 的规则 → 判定“禁止”。
- 规则需要的数据（浓度/温度/材质）缺失且无法判定是否越限 → 判定“需人工复核”。
- 对当前同区组合、每个化学品自身容器、以及按顺序模拟每个事件后的新组合逐项判定。
"""
from itertools import combinations

CATEGORY_LABELS = {
    "acid_base": "酸碱",
    "redox": "氧化还原",
    "gas": "放气",
    "exotherm": "放热",
    "corrosion": "容器腐蚀",
}


def _tagset(chem):
    return set(chem.get("tags") or [])


def _finding(rule, chems, ctx, action, reason):
    return {
        "rule_id": rule["id"],
        "rule_name": rule["name"],
        "category": rule["category"],
        "category_label": CATEGORY_LABELS.get(rule["category"], rule["category"]),
        "action": action,
        "scope": ctx.get("scope"),          # zone | container | event
        "phase": ctx.get("phase"),          # before | after
        "zone": ctx.get("zone"),
        "event": ctx.get("event"),
        "chemical_ids": [c["id"] for c in chems],
        "chemicals": [c["name"] for c in chems],
        "reason": reason,
    }


def _event_ok(cond, ctx):
    evs = cond.get("event_types") or []
    if not evs:
        return True
    return ctx.get("event_type") in evs


def _threshold_check(cond, chems):
    """返回 (applies, missing)。已知数据已满足阈值→适用；数据缺失无法判定→复核。"""
    missing = []
    thr = cond.get("min_concentration_pct")
    if thr is not None:
        vals = [c.get("concentration_pct") for c in chems]
        known = [v for v in vals if v is not None]
        if known and max(known) >= thr:
            pass
        elif len(known) < len(vals):
            missing.append("浓度")
        else:
            return False, missing
    tmin = cond.get("min_temperature_c")
    if tmin is not None:
        vals = [c.get("temperature_c") for c in chems]
        known = [v for v in vals if v is not None]
        if known and max(known) >= tmin:
            pass
        elif len(known) < len(vals):
            missing.append("温度")
        else:
            return False, missing
    return True, missing


def _emit(rule, chems, ctx, missing):
    if missing:
        return _finding(
            rule, chems, ctx, "review",
            f"命中规则「{rule['name']}」的匹配条件，但缺少必填数据（{'、'.join(missing)}），需人工复核",
        )
    return _finding(rule, chems, ctx, rule["action"], rule["message"] or rule["name"])


def eval_pair(rules, a, b, ctx):
    """评估一对化学品之间的所有成对规则。"""
    out = []
    for rule in rules:
        cond = rule["cond"]
        if cond.get("tag_self"):
            continue
        ta, tb = cond.get("tag_a"), cond.get("tag_b")
        if not ta or not tb or not _event_ok(cond, ctx):
            continue
        sa, sb = _tagset(a), _tagset(b)
        if not ((ta in sa and tb in sb) or (ta in sb and tb in sa)):
            continue
        ok, missing = _threshold_check(cond, [a, b])
        if ok:
            out.append(_emit(rule, [a, b], ctx, missing))
    return out


def eval_single(rules, chem, material, ctx):
    """评估单个化学品（容器腐蚀类规则）。"""
    out = []
    for rule in rules:
        cond = rule["cond"]
        ts = cond.get("tag_self")
        if not ts or ts not in _tagset(chem) or not _event_ok(cond, ctx):
            continue
        mats = cond.get("materials") or []
        if mats:
            if not material:
                out.append(_finding(
                    rule, [chem], ctx, "review",
                    f"命中规则「{rule['name']}」的匹配条件，但缺少容器材质数据，需人工复核"))
                continue
            if material not in mats:
                continue
        ok, missing = _threshold_check(cond, [chem])
        if ok:
            out.append(_emit(rule, [chem], ctx, missing))
    return out


def run_review(conn, version, rules):
    """对当前库存与待执行事件执行完整审查，返回可 JSON 序列化的结果。"""
    from . import db

    chemicals = {c["id"]: c for c in
                 (db.chem_out(r) for r in db.rows(conn, "SELECT * FROM chemicals"))}
    zones = {z["id"]: z["name"] for z in db.rows(conn, "SELECT * FROM zones")}
    events = db.rows(
        conn,
        "SELECT * FROM events WHERE status='pending' ORDER BY seq, planned_at, id")

    findings = []
    state = {cid: dict(c) for cid, c in chemicals.items()}

    def members(zid):
        return [c for c in state.values() if c.get("zone_id") == zid]

    # 阶段一：当前状态——同区两两组合 + 各化学品自身容器
    for zid, zname in zones.items():
        ms = members(zid)
        for a, b in combinations(ms, 2):
            findings += eval_pair(rules, a, b,
                                  {"scope": "zone", "phase": "before", "zone": zname})
        for c in ms:
            findings += eval_single(rules, c, c.get("container_material") or "",
                                    {"scope": "container", "phase": "before", "zone": zname})

    # 阶段二：按顺序模拟每个待执行事件，判定事件后的新状态
    for ev in events:
        ctx = {
            "scope": "event", "phase": "after",
            "event_type": ev["event_type"],
            "event": {"id": ev["id"], "event_type": ev["event_type"],
                      "seq": ev["seq"], "planned_at": ev["planned_at"], "note": ev["note"]},
        }
        c1 = state.get(ev["chemical_id"])
        if c1 is None:
            continue
        et = ev["event_type"]
        if et == "transfer":
            tgt = ev["target_zone_id"]
            ctx["zone"] = zones.get(tgt)
            for other in members(tgt):
                if other["id"] != c1["id"]:
                    findings += eval_pair(rules, c1, other, ctx)
            c1["zone_id"] = tgt
        elif et == "mix":
            c2 = state.get(ev["chemical_id_2"])
            if c2 is not None:
                ctx["zone"] = zones.get(c2.get("zone_id"))
                findings += eval_pair(rules, c1, c2, ctx)
                mat = ev["target_material"] or c2.get("container_material") or ""
                findings += eval_single(rules, c1, mat, ctx)
                findings += eval_single(rules, c2, mat, ctx)
        elif et == "dispose":
            ctx["zone"] = zones.get(ev["target_zone_id"]) or zones.get(c1.get("zone_id"))
            findings += eval_single(rules, c1, ev["target_material"] or "", ctx)

    for i, f in enumerate(findings):
        f["order"] = i

    forbids = [f for f in findings if f["action"] == "forbid"]
    reviews = [f for f in findings if f["action"] == "review"]
    event_forbids = [f for f in forbids if f["scope"] == "event"]
    earliest = event_forbids[0] if event_forbids else (forbids[0] if forbids else None)

    # 需隔离对象：所有命中禁止条目的化学品
    isolation = {}
    for f in forbids:
        for cid, name in zip(f["chemical_ids"], f["chemicals"]):
            entry = isolation.setdefault(cid, {"id": cid, "name": name, "reasons": []})
            entry["reasons"].append(f"{f['rule_name']}（{f['zone'] or '事件'}）")

    return {
        "version": version["version"],
        "version_id": version["id"],
        "summary": {
            "forbid": len(forbids),
            "review": len(reviews),
            "total": len(findings),
            "events_checked": len(events),
            "chemicals_checked": len(chemicals),
        },
        "earliest_conflict": earliest,
        "isolation": sorted(isolation.values(), key=lambda x: x["id"]),
        "findings": findings,
        "rules_snapshot": [
            {"id": r["id"], "category": r["category"], "name": r["name"],
             "action": r["action"], "cond": r["cond"], "message": r["message"]}
            for r in rules
        ],
    }
