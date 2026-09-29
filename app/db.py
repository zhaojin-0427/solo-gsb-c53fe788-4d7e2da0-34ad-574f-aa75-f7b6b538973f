"""SQLite 数据访问层：建表、连接、种子数据。"""
import json
import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE_DIR, "..", "data", "app.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS zones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS chemicals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    cas TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '[]',
    concentration_pct REAL,
    volume_ml REAL,
    temperature_c REAL,
    container_material TEXT NOT NULL DEFAULT '',
    zone_id INTEGER REFERENCES zones(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    chemical_id INTEGER NOT NULL REFERENCES chemicals(id) ON DELETE CASCADE,
    chemical_id_2 INTEGER REFERENCES chemicals(id) ON DELETE SET NULL,
    source_zone_id INTEGER REFERENCES zones(id) ON DELETE SET NULL,
    target_zone_id INTEGER REFERENCES zones(id) ON DELETE SET NULL,
    target_material TEXT NOT NULL DEFAULT '',
    quantity_ml REAL,
    planned_at TEXT NOT NULL DEFAULT '',
    seq INTEGER NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending'
);
CREATE TABLE IF NOT EXISTS rule_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version INTEGER NOT NULL UNIQUE,
    note TEXT NOT NULL DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 0,
    is_sealed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version_id INTEGER NOT NULL REFERENCES rule_versions(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    name TEXT NOT NULL,
    action TEXT NOT NULL DEFAULT 'forbid',
    cond TEXT NOT NULL DEFAULT '{}',
    message TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    result TEXT NOT NULL
);
"""


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def rows(conn, sql, params=()):
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def row(conn, sql, params=()):
    r = conn.execute(sql, params).fetchone()
    return dict(r) if r else None


def chem_out(r):
    d = dict(r)
    d["tags"] = json.loads(d.get("tags") or "[]")
    return d


def rule_out(r):
    d = dict(r)
    d["cond"] = json.loads(d.get("cond") or "{}")
    return d


def init():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        if row(conn, "SELECT COUNT(*) AS c FROM rule_versions")["c"] == 0:
            _seed(conn)
        conn.commit()
    finally:
        conn.close()


def _seed(conn):
    # 分区
    zones = [
        ("A-酸碱柜", "无机酸碱常规储存"),
        ("B-氧化剂柜", "氧化剂专用，远离易燃物"),
        ("C-废液暂存区", "待处置废液临时存放"),
    ]
    conn.executemany("INSERT INTO zones(name, description) VALUES (?, ?)", zones)

    # 化学品：name, cas, tags, 浓度%, 体积mL, 温度°C, 材质, zone_id
    chemicals = [
        ("盐酸", "7647-01-0", '["acid"]', 37, 500, 25, "玻璃", 1),
        ("氢氧化钠溶液", "1310-73-2", '["base"]', 30, 1000, 25, "铝", 1),
        ("氨水", "1336-21-6", '["base"]', None, 500, 25, "玻璃", 1),
        ("高锰酸钾", "7722-64-7", '["oxidizer"]', None, None, 25, "玻璃", 2),
        ("乙醇", "64-17-5", '["flammable", "organic"]', 95, 500, 25, "玻璃", 2),
        ("硝酸", "7697-37-2", '["acid", "oxidizer"]', 65, 500, 25, "玻璃", 2),
        ("硫化钠溶液", "1313-82-2", '["sulfide", "base"]', 10, 2000, 25, "碳钢", 3),
    ]
    conn.executemany(
        "INSERT INTO chemicals(name, cas, tags, concentration_pct, volume_ml, "
        "temperature_c, container_material, zone_id) VALUES (?,?,?,?,?,?,?,?)",
        chemicals,
    )

    # 规则版本 v1（当前可编辑版本）
    cur = conn.execute(
        "INSERT INTO rule_versions(version, note, is_active, is_sealed) VALUES (1, '初始内置规则', 1, 0)"
    )
    vid = cur.lastrowid
    rules = [
        ("acid_base", "酸碱中和放热", "forbid",
         {"tag_a": "acid", "tag_b": "base", "min_concentration_pct": 5},
         "酸碱混合发生剧烈中和放热反应，禁止同区存放或混合"),
        ("acid_base", "高浓度酸碱剧烈反应", "forbid",
         {"tag_a": "acid", "tag_b": "base", "min_concentration_pct": 50},
         "高浓度酸碱混合剧烈放热，可能沸腾喷溅"),
        ("redox", "氧化剂-易燃物", "forbid",
         {"tag_a": "oxidizer", "tag_b": "flammable"},
         "氧化剂与易燃物接触可能起火爆炸"),
        ("redox", "氧化剂-还原剂", "forbid",
         {"tag_a": "oxidizer", "tag_b": "reducer"},
         "氧化剂与还原剂混合可能发生剧烈氧化还原反应"),
        ("redox", "氧化剂-有机物", "review",
         {"tag_a": "oxidizer", "tag_b": "organic"},
         "氧化剂与有机物共存需人工评估"),
        ("gas", "酸-硫化物放气", "forbid",
         {"tag_a": "acid", "tag_b": "sulfide"},
         "酸与硫化物反应放出硫化氢毒气"),
        ("gas", "酸-氰化物放气", "forbid",
         {"tag_a": "acid", "tag_b": "cyanide"},
         "酸与氰化物反应放出氰化氢剧毒气体"),
        ("gas", "酸-碳酸盐放气", "review",
         {"tag_a": "acid", "tag_b": "carbonate"},
         "酸与碳酸盐反应放出二氧化碳，需评估通风与承压"),
        ("exotherm", "浓酸遇水放热", "review",
         {"tag_a": "acid", "tag_b": "water", "min_concentration_pct": 30},
         "浓酸遇水剧烈放热，须按规程稀释"),
        ("exotherm", "高温下氧化剂-易燃物", "forbid",
         {"tag_a": "oxidizer", "tag_b": "flammable", "min_temperature_c": 40},
         "高温环境下氧化剂与易燃物反应风险加剧"),
        ("corrosion", "酸腐蚀金属容器", "forbid",
         {"tag_self": "acid", "materials": ["碳钢", "铁", "铝"]},
         "酸会腐蚀金属容器导致泄漏"),
        ("corrosion", "碱腐蚀铝容器", "forbid",
         {"tag_self": "base", "materials": ["铝"]},
         "强碱腐蚀铝容器并放出氢气"),
    ]
    conn.executemany(
        "INSERT INTO rules(version_id, category, name, action, cond, message) VALUES (?,?,?,?,?,?)",
        [(vid, c, n, a, json.dumps(cond, ensure_ascii=False), m) for c, n, a, cond, m in rules],
    )

    # 待执行事件
    events = [
        ("mix", 1, 2, None, None, "玻璃", 100, "2026-10-01 09:00", 1, "中和废酸", "pending"),
        ("dispose", 1, None, 1, 3, "碳钢", 200, "2026-10-01 10:00", 2, "废盐酸倒入废液桶", "pending"),
        ("mix", 4, 5, None, None, "玻璃", 50, "2026-10-02 09:00", 3, "氧化性废液处理", "pending"),
        ("transfer", 6, None, 2, 1, "", 500, "2026-10-02 10:00", 4, "硝酸移至酸碱柜", "pending"),
    ]
    conn.executemany(
        "INSERT INTO events(event_type, chemical_id, chemical_id_2, source_zone_id, "
        "target_zone_id, target_material, quantity_ml, planned_at, seq, note, status) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        events,
    )
