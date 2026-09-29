"""FastAPI 应用：REST API + 静态前端。"""
import json
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import db, engine

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


@asynccontextmanager
async def lifespan(_):
    db.init()
    yield


app = FastAPI(title="实验室化学品相容性审查台", lifespan=lifespan)


# ---------- 输入模型 ----------
class ZoneIn(BaseModel):
    name: str
    description: str = ""


class ChemicalIn(BaseModel):
    name: str
    cas: str = ""
    tags: list[str] = []
    concentration_pct: Optional[float] = None
    volume_ml: Optional[float] = None
    temperature_c: Optional[float] = None
    container_material: str = ""
    zone_id: Optional[int] = None


class EventIn(BaseModel):
    event_type: str                      # transfer | mix | dispose
    chemical_id: int
    chemical_id_2: Optional[int] = None
    source_zone_id: Optional[int] = None
    target_zone_id: Optional[int] = None
    target_material: str = ""
    quantity_ml: Optional[float] = None
    planned_at: str = ""
    seq: int = 0
    note: str = ""
    status: str = "pending"


class RuleIn(BaseModel):
    category: str
    name: str
    action: str = "forbid"               # forbid | review
    cond: dict = {}
    message: str = ""


class ReviewIn(BaseModel):
    version_id: Optional[int] = None


# ---------- 分区 ----------
@app.get("/api/zones")
def list_zones():
    conn = db.connect()
    try:
        return db.rows(conn, "SELECT * FROM zones ORDER BY id")
    finally:
        conn.close()


@app.post("/api/zones", status_code=201)
def create_zone(payload: ZoneIn):
    conn = db.connect()
    try:
        cur = conn.execute("INSERT INTO zones(name, description) VALUES (?, ?)",
                           (payload.name, payload.description))
        conn.commit()
        return db.row(conn, "SELECT * FROM zones WHERE id=?", (cur.lastrowid,))
    finally:
        conn.close()


@app.delete("/api/zones/{zid}")
def delete_zone(zid: int):
    conn = db.connect()
    try:
        conn.execute("DELETE FROM zones WHERE id=?", (zid,))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


# ---------- 化学品 ----------
@app.get("/api/chemicals")
def list_chemicals():
    conn = db.connect()
    try:
        return [db.chem_out(r) for r in db.rows(conn, "SELECT * FROM chemicals ORDER BY id")]
    finally:
        conn.close()


@app.post("/api/chemicals", status_code=201)
def create_chemical(payload: ChemicalIn):
    conn = db.connect()
    try:
        cur = conn.execute(
            "INSERT INTO chemicals(name, cas, tags, concentration_pct, volume_ml, "
            "temperature_c, container_material, zone_id) VALUES (?,?,?,?,?,?,?,?)",
            (payload.name, payload.cas, json.dumps(payload.tags, ensure_ascii=False),
             payload.concentration_pct, payload.volume_ml, payload.temperature_c,
             payload.container_material, payload.zone_id))
        conn.commit()
        return db.chem_out(db.row(conn, "SELECT * FROM chemicals WHERE id=?", (cur.lastrowid,)))
    finally:
        conn.close()


@app.put("/api/chemicals/{cid}")
def update_chemical(cid: int, payload: ChemicalIn):
    conn = db.connect()
    try:
        conn.execute(
            "UPDATE chemicals SET name=?, cas=?, tags=?, concentration_pct=?, volume_ml=?, "
            "temperature_c=?, container_material=?, zone_id=? WHERE id=?",
            (payload.name, payload.cas, json.dumps(payload.tags, ensure_ascii=False),
             payload.concentration_pct, payload.volume_ml, payload.temperature_c,
             payload.container_material, payload.zone_id, cid))
        conn.commit()
        r = db.row(conn, "SELECT * FROM chemicals WHERE id=?", (cid,))
        if not r:
            raise HTTPException(404, "化学品不存在")
        return db.chem_out(r)
    finally:
        conn.close()


@app.delete("/api/chemicals/{cid}")
def delete_chemical(cid: int):
    conn = db.connect()
    try:
        conn.execute("DELETE FROM chemicals WHERE id=?", (cid,))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


# ---------- 事件 ----------
@app.get("/api/events")
def list_events():
    conn = db.connect()
    try:
        return db.rows(conn, "SELECT * FROM events ORDER BY seq, planned_at, id")
    finally:
        conn.close()


@app.post("/api/events", status_code=201)
def create_event(payload: EventIn):
    if payload.event_type not in ("transfer", "mix", "dispose"):
        raise HTTPException(400, "event_type 须为 transfer/mix/dispose")
    conn = db.connect()
    try:
        cur = conn.execute(
            "INSERT INTO events(event_type, chemical_id, chemical_id_2, source_zone_id, "
            "target_zone_id, target_material, quantity_ml, planned_at, seq, note, status) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (payload.event_type, payload.chemical_id, payload.chemical_id_2,
             payload.source_zone_id, payload.target_zone_id, payload.target_material,
             payload.quantity_ml, payload.planned_at, payload.seq, payload.note, payload.status))
        conn.commit()
        return db.row(conn, "SELECT * FROM events WHERE id=?", (cur.lastrowid,))
    finally:
        conn.close()


@app.put("/api/events/{eid}")
def update_event(eid: int, payload: EventIn):
    conn = db.connect()
    try:
        conn.execute(
            "UPDATE events SET event_type=?, chemical_id=?, chemical_id_2=?, source_zone_id=?, "
            "target_zone_id=?, target_material=?, quantity_ml=?, planned_at=?, seq=?, note=?, "
            "status=? WHERE id=?",
            (payload.event_type, payload.chemical_id, payload.chemical_id_2,
             payload.source_zone_id, payload.target_zone_id, payload.target_material,
             payload.quantity_ml, payload.planned_at, payload.seq, payload.note,
             payload.status, eid))
        conn.commit()
        r = db.row(conn, "SELECT * FROM events WHERE id=?", (eid,))
        if not r:
            raise HTTPException(404, "事件不存在")
        return r
    finally:
        conn.close()


@app.delete("/api/events/{eid}")
def delete_event(eid: int):
    conn = db.connect()
    try:
        conn.execute("DELETE FROM events WHERE id=?", (eid,))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


# ---------- 规则版本与规则 ----------
def _active_version(conn):
    v = db.row(conn, "SELECT * FROM rule_versions WHERE is_active=1")
    if not v:
        raise HTTPException(500, "没有当前规则版本")
    return v


@app.get("/api/rule-versions")
def list_versions():
    conn = db.connect()
    try:
        vs = db.rows(conn, "SELECT * FROM rule_versions ORDER BY version")
        for v in vs:
            v["rule_count"] = db.row(
                conn, "SELECT COUNT(*) AS c FROM rules WHERE version_id=?", (v["id"],))["c"]
        return vs
    finally:
        conn.close()


@app.post("/api/rule-versions/seal", status_code=201)
def seal_version():
    """封存当前版本并以其副本新建可编辑版本。"""
    conn = db.connect()
    try:
        v = _active_version(conn)
        conn.execute("UPDATE rule_versions SET is_sealed=1, is_active=0 WHERE id=?", (v["id"],))
        new_ver = v["version"] + 1
        cur = conn.execute(
            "INSERT INTO rule_versions(version, note, is_active, is_sealed) VALUES (?, '', 1, 0)",
            (new_ver,))
        new_id = cur.lastrowid
        conn.execute(
            "INSERT INTO rules(version_id, category, name, action, cond, message) "
            "SELECT ?, category, name, action, cond, message FROM rules WHERE version_id=?",
            (new_id, v["id"]))
        conn.commit()
        return db.row(conn, "SELECT * FROM rule_versions WHERE id=?", (new_id,))
    finally:
        conn.close()


@app.post("/api/rule-versions/{vid}/activate")
def activate_version(vid: int):
    conn = db.connect()
    try:
        if not db.row(conn, "SELECT id FROM rule_versions WHERE id=?", (vid,)):
            raise HTTPException(404, "版本不存在")
        conn.execute("UPDATE rule_versions SET is_active=0")
        conn.execute("UPDATE rule_versions SET is_active=1 WHERE id=?", (vid,))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@app.get("/api/rules")
def list_rules(version_id: Optional[int] = None):
    conn = db.connect()
    try:
        if version_id is None:
            version_id = _active_version(conn)["id"]
        return [db.rule_out(r) for r in db.rows(
            conn, "SELECT * FROM rules WHERE version_id=? ORDER BY id", (version_id,))]
    finally:
        conn.close()


def _check_editable(conn, rule_id=None):
    v = _active_version(conn)
    if v["is_sealed"]:
        raise HTTPException(400, "当前版本已封存，请先「封存并新建版本」后再编辑")
    if rule_id is not None:
        r = db.row(conn, "SELECT * FROM rules WHERE id=?", (rule_id,))
        if not r:
            raise HTTPException(404, "规则不存在")
        if r["version_id"] != v["id"]:
            raise HTTPException(400, "只能编辑当前版本中的规则")
    return v


@app.post("/api/rules", status_code=201)
def create_rule(payload: RuleIn):
    conn = db.connect()
    try:
        v = _check_editable(conn)
        cur = conn.execute(
            "INSERT INTO rules(version_id, category, name, action, cond, message) "
            "VALUES (?,?,?,?,?,?)",
            (v["id"], payload.category, payload.name, payload.action,
             json.dumps(payload.cond, ensure_ascii=False), payload.message))
        conn.commit()
        return db.rule_out(db.row(conn, "SELECT * FROM rules WHERE id=?", (cur.lastrowid,)))
    finally:
        conn.close()


@app.put("/api/rules/{rid}")
def update_rule(rid: int, payload: RuleIn):
    conn = db.connect()
    try:
        _check_editable(conn, rid)
        conn.execute(
            "UPDATE rules SET category=?, name=?, action=?, cond=?, message=? WHERE id=?",
            (payload.category, payload.name, payload.action,
             json.dumps(payload.cond, ensure_ascii=False), payload.message, rid))
        conn.commit()
        return db.rule_out(db.row(conn, "SELECT * FROM rules WHERE id=?", (rid,)))
    finally:
        conn.close()


@app.delete("/api/rules/{rid}")
def delete_rule(rid: int):
    conn = db.connect()
    try:
        _check_editable(conn, rid)
        conn.execute("DELETE FROM rules WHERE id=?", (rid,))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


# ---------- 审查 ----------
@app.post("/api/reviews", status_code=201)
def run_review(payload: Optional[ReviewIn] = None):
    conn = db.connect()
    try:
        if payload and payload.version_id:
            version = db.row(conn, "SELECT * FROM rule_versions WHERE id=?", (payload.version_id,))
            if not version:
                raise HTTPException(404, "规则版本不存在")
        else:
            version = _active_version(conn)
        rules = [db.rule_out(r) for r in db.rows(
            conn, "SELECT * FROM rules WHERE version_id=? ORDER BY id", (version["id"],))]
        result = engine.run_review(conn, version, rules)
        cur = conn.execute(
            "INSERT INTO reviews(version_id, version, result) VALUES (?,?,?)",
            (version["id"], version["version"], json.dumps(result, ensure_ascii=False)))
        conn.commit()
        result["review_id"] = cur.lastrowid
        return result
    finally:
        conn.close()


@app.get("/api/reviews")
def list_reviews():
    conn = db.connect()
    try:
        out = []
        for r in db.rows(conn, "SELECT * FROM reviews ORDER BY id DESC"):
            res = json.loads(r["result"])
            out.append({"id": r["id"], "version": r["version"],
                        "created_at": r["created_at"], "summary": res["summary"]})
        return out
    finally:
        conn.close()


@app.get("/api/reviews/{rid}")
def get_review(rid: int):
    conn = db.connect()
    try:
        r = db.row(conn, "SELECT * FROM reviews WHERE id=?", (rid,))
        if not r:
            raise HTTPException(404, "审查记录不存在")
        res = json.loads(r["result"])
        res["review_id"] = r["id"]
        res["created_at"] = r["created_at"]
        return res
    finally:
        conn.close()


# ---------- 静态前端 ----------
@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
