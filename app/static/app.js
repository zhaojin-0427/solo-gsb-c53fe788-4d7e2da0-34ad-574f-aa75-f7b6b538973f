"use strict";

const TAGS = [
  ["acid", "酸"], ["base", "碱"], ["oxidizer", "氧化剂"], ["reducer", "还原剂"],
  ["flammable", "易燃"], ["organic", "有机物"], ["sulfide", "硫化物"],
  ["carbonate", "碳酸盐"], ["cyanide", "氰化物"], ["water", "含水"],
  ["peroxide", "过氧化物"], ["halogen", "卤素"],
];
const MATERIALS = ["玻璃", "聚乙烯(PE)", "聚丙烯(PP)", "聚四氟乙烯(PTFE)", "碳钢", "不锈钢", "铝", "铁", "铜"];
const CATEGORIES = { acid_base: "酸碱", redox: "氧化还原", gas: "放气", exotherm: "放热", corrosion: "容器腐蚀" };
const EVENT_TYPES = { transfer: "转移", mix: "混合", dispose: "废弃" };

let zones = [], chemicals = [], events = [], versions = [], rules = [];
let editingChemId = null, editingEventId = null, editingRuleId = null;
let selectedVersionId = null;

const $ = (s) => document.querySelector(s);
const tagLabel = (t) => (TAGS.find(x => x[0] === t) || [t, t])[1];
const zoneName = (id) => (zones.find(z => z.id === id) || {}).name || "—";
const chemName = (id) => (chemicals.find(c => c.id === id) || {}).name || `#${id}`;
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function toast(msg, isErr) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "show" + (isErr ? " error" : "");
  setTimeout(() => (t.className = ""), 2600);
}

async function api(path, method = "GET", body) {
  const opt = { method, headers: { "Content-Type": "application/json" } };
  if (body !== undefined) opt.body = JSON.stringify(body);
  const r = await fetch(path, opt);
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch (e) { /* ignore */ }
    throw new Error(msg);
  }
  return r.json();
}

/* ---------------- 标签页 ---------------- */
document.querySelectorAll("nav button").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("nav button").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    document.querySelectorAll("main > section").forEach(s => (s.hidden = true));
    $("#tab-" + btn.dataset.tab).hidden = false;
    if (btn.dataset.tab === "review") loadReviewTab();
    if (btn.dataset.tab === "rules") loadRulesTab();
  });
});

/* ---------------- 初始化下拉选项 ---------------- */
function fillSelect(sel, items, withEmpty) {
  sel.innerHTML = (withEmpty ? '<option value="">（未指定）</option>' : "") +
    items.map(([v, l]) => `<option value="${esc(v)}">${esc(l)}</option>`).join("");
}
function buildStaticOptions() {
  fillSelect($("#chem-material"), MATERIALS.map(m => [m, m]), true);
  fillSelect($("#ev-target-material"), MATERIALS.map(m => [m, m]), true);
  fillSelect($("#rule-tag-a"), TAGS, true);
  fillSelect($("#rule-tag-b"), TAGS, true);
  fillSelect($("#rule-tag-self"), TAGS, true);
  $("#chem-tags").innerHTML = TAGS.map(([v, l]) =>
    `<label><input type="checkbox" value="${v}"> ${l}</label>`).join("");
  $("#rule-materials").innerHTML = MATERIALS.map(m =>
    `<label><input type="checkbox" value="${m}"> ${m}</label>`).join("");
  $("#rule-event-types").innerHTML = Object.entries(EVENT_TYPES).map(([v, l]) =>
    `<label><input type="checkbox" value="${v}"> ${l}</label>`).join("");
}
function refreshZoneSelects() {
  const items = zones.map(z => [z.id, z.name]);
  fillSelect($("#chem-zone"), items, true);
  fillSelect($("#ev-target-zone"), items, true);
}
function refreshChemSelects() {
  const items = chemicals.map(c => [c.id, `${c.name}（${zoneName(c.zone_id)}）`]);
  fillSelect($("#ev-chem1"), items, false);
  fillSelect($("#ev-chem2"), items, true);
}

/* ---------------- 化学品 ---------------- */
async function loadChemicals() {
  chemicals = await api("/api/chemicals");
  const tb = $("#chem-table tbody");
  tb.innerHTML = chemicals.map(c => `<tr>
    <td>${c.id}</td><td>${esc(c.name)}</td><td>${esc(c.cas)}</td>
    <td>${c.tags.map(t => `<span class="badge badge-tag">${tagLabel(t)}</span>`).join("")}</td>
    <td>${c.concentration_pct ?? "—"}</td><td>${c.volume_ml ?? "—"}</td><td>${c.temperature_c ?? "—"}</td>
    <td>${esc(c.container_material) || "—"}</td><td>${esc(zoneName(c.zone_id))}</td>
    <td>
      <button class="small" onclick="editChem(${c.id})">编辑</button>
      <button class="small danger" onclick="delChem(${c.id})">删除</button>
    </td></tr>`).join("");
  refreshChemSelects();
}

function chemFormData() {
  return {
    name: $("#chem-name").value.trim(),
    cas: $("#chem-cas").value.trim(),
    tags: [...$("#chem-tags").querySelectorAll("input:checked")].map(i => i.value),
    concentration_pct: $("#chem-conc").value === "" ? null : +$("#chem-conc").value,
    volume_ml: $("#chem-vol").value === "" ? null : +$("#chem-vol").value,
    temperature_c: $("#chem-temp").value === "" ? null : +$("#chem-temp").value,
    container_material: $("#chem-material").value,
    zone_id: $("#chem-zone").value === "" ? null : +$("#chem-zone").value,
  };
}

function resetChemForm() {
  editingChemId = null;
  $("#chem-form").reset();
  $("#chem-form-title").textContent = "新增化学品";
  $("#chem-cancel").hidden = true;
}

$("#chem-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    const data = chemFormData();
    if (editingChemId) await api(`/api/chemicals/${editingChemId}`, "PUT", data);
    else await api("/api/chemicals", "POST", data);
    resetChemForm();
    await loadChemicals();
    toast("已保存");
  } catch (err) { toast(err.message, true); }
});
$("#chem-cancel").addEventListener("click", resetChemForm);

window.editChem = (id) => {
  const c = chemicals.find(x => x.id === id);
  if (!c) return;
  editingChemId = id;
  $("#chem-name").value = c.name;
  $("#chem-cas").value = c.cas;
  $("#chem-conc").value = c.concentration_pct ?? "";
  $("#chem-vol").value = c.volume_ml ?? "";
  $("#chem-temp").value = c.temperature_c ?? "";
  $("#chem-material").value = c.container_material || "";
  $("#chem-zone").value = c.zone_id ?? "";
  $("#chem-tags").querySelectorAll("input").forEach(i => (i.checked = c.tags.includes(i.value)));
  $("#chem-form-title").textContent = `编辑化学品 #${id}`;
  $("#chem-cancel").hidden = false;
  window.scrollTo(0, 0);
};

window.delChem = async (id) => {
  if (!confirm("确认删除该化学品？")) return;
  try { await api(`/api/chemicals/${id}`, "DELETE"); await loadChemicals(); toast("已删除"); }
  catch (err) { toast(err.message, true); }
};

/* ---------------- 分区 ---------------- */
async function loadZones() {
  zones = await api("/api/zones");
  $("#zone-table tbody").innerHTML = zones.map(z => {
    const n = chemicals.filter(c => c.zone_id === z.id).length;
    return `<tr><td>${z.id}</td><td>${esc(z.name)}</td><td>${esc(z.description)}</td><td>${n}</td>
      <td><button class="small danger" onclick="delZone(${z.id})">删除</button></td></tr>`;
  }).join("");
  refreshZoneSelects();
}

$("#zone-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api("/api/zones", "POST", { name: $("#zone-name").value.trim(), description: $("#zone-desc").value.trim() });
    $("#zone-form").reset();
    await loadZones();
    toast("已保存");
  } catch (err) { toast(err.message, true); }
});

window.delZone = async (id) => {
  if (!confirm("确认删除该分区？其中化学品将变为未分配。")) return;
  try { await api(`/api/zones/${id}`, "DELETE"); await loadChemicals(); await loadZones(); toast("已删除"); }
  catch (err) { toast(err.message, true); }
};

/* ---------------- 事件 ---------------- */
function toggleEventFields() {
  const t = $("#ev-type").value;
  $("#wrap-ev-chem2").style.display = t === "mix" ? "" : "none";
  $("#wrap-ev-target-zone").style.display = t === "mix" ? "none" : "";
  $("#wrap-ev-target-material").style.display = t === "transfer" ? "none" : "";
}
$("#ev-type").addEventListener("change", toggleEventFields);

async function loadEvents() {
  events = await api("/api/events");
  $("#event-table tbody").innerHTML = events.map(ev => {
    let detail = "";
    if (ev.event_type === "transfer") detail = `→ ${esc(zoneName(ev.target_zone_id))}`;
    if (ev.event_type === "mix") detail = `与 ${ev.chemical_id_2 ? esc(chemName(ev.chemical_id_2)) : "—"} 混合${ev.target_material ? "，容器：" + esc(ev.target_material) : ""}`;
    if (ev.event_type === "dispose") detail = `废弃至${ev.target_material ? esc(ev.target_material) + "容器" : "废液容器"}`;
    const status = ev.status === "pending"
      ? '<span class="badge badge-review">待执行</span>'
      : '<span class="badge badge-ok">已完成</span>';
    return `<tr><td>${ev.id}</td><td>${ev.seq}</td><td>${EVENT_TYPES[ev.event_type] || ev.event_type}</td>
      <td>${esc(chemName(ev.chemical_id))}</td><td>${detail}</td>
      <td>${esc((ev.planned_at || "").replace("T", " "))}</td><td>${status}</td><td>${esc(ev.note)}</td>
      <td>
        <button class="small" onclick="toggleEvent(${ev.id})">${ev.status === "pending" ? "标记完成" : "重新待办"}</button>
        <button class="small danger" onclick="delEvent(${ev.id})">删除</button>
      </td></tr>`;
  }).join("");
}

function eventFormData() {
  return {
    event_type: $("#ev-type").value,
    chemical_id: +$("#ev-chem1").value,
    chemical_id_2: $("#ev-chem2").value === "" ? null : +$("#ev-chem2").value,
    target_zone_id: $("#ev-target-zone").value === "" ? null : +$("#ev-target-zone").value,
    target_material: $("#ev-target-material").value,
    quantity_ml: $("#ev-qty").value === "" ? null : +$("#ev-qty").value,
    planned_at: $("#ev-planned").value.replace("T", " "),
    seq: +$("#ev-seq").value || 0,
    note: $("#ev-note").value.trim(),
    status: editingEventId ? (events.find(x => x.id === editingEventId) || {}).status || "pending" : "pending",
  };
}

function resetEventForm() {
  editingEventId = null;
  $("#event-form").reset();
  $("#event-form-title").textContent = "登记事件";
  $("#event-cancel").hidden = true;
  toggleEventFields();
}

$("#event-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    const data = eventFormData();
    if (editingEventId) await api(`/api/events/${editingEventId}`, "PUT", data);
    else await api("/api/events", "POST", data);
    resetEventForm();
    await loadEvents();
    toast("已保存");
  } catch (err) { toast(err.message, true); }
});
$("#event-cancel").addEventListener("click", resetEventForm);

window.toggleEvent = async (id) => {
  const ev = events.find(x => x.id === id);
  if (!ev) return;
  try {
    await api(`/api/events/${id}`, "PUT", { ...ev, status: ev.status === "pending" ? "done" : "pending" });
    await loadEvents();
  } catch (err) { toast(err.message, true); }
};

window.delEvent = async (id) => {
  if (!confirm("确认删除该事件？")) return;
  try { await api(`/api/events/${id}`, "DELETE"); await loadEvents(); toast("已删除"); }
  catch (err) { toast(err.message, true); }
};

/* ---------------- 规则 ---------------- */
async function loadRulesTab() {
  versions = await api("/api/rule-versions");
  const active = versions.find(v => v.is_active) || versions[versions.length - 1];
  if (!selectedVersionId || !versions.some(v => v.id === selectedVersionId)) selectedVersionId = active.id;
  renderVersionBar();
  await loadRules();
}

function renderVersionBar() {
  const sel = $("#version-select");
  sel.innerHTML = versions.map(v =>
    `<option value="${v.id}" ${v.id === selectedVersionId ? "selected" : ""}>v${v.version}${v.is_active ? "（当前）" : ""}${v.is_sealed ? "（已封存）" : ""}</option>`).join("");
  const v = versions.find(x => x.id === selectedVersionId);
  $("#version-status").innerHTML = v
    ? `${v.is_active ? '<span class="badge badge-active">当前版本</span>' : ""}${v.is_sealed ? '<span class="badge badge-sealed">已封存·只读</span>' : ""} 共 ${v.rule_count} 条规则`
    : "";
  $("#rule-edit-card").style.display = v && !v.is_sealed ? "" : "none";
}
$("#version-select").addEventListener("change", async () => {
  selectedVersionId = +$("#version-select").value;
  renderVersionBar();
  await loadRules();
});
$("#btn-activate").addEventListener("click", async () => {
  try {
    await api(`/api/rule-versions/${selectedVersionId}/activate`, "POST");
    await loadRulesTab();
    toast("已切换当前版本");
  } catch (err) { toast(err.message, true); }
});
$("#btn-seal").addEventListener("click", async () => {
  if (!confirm("封存当前版本并以其副本新建可编辑版本？")) return;
  try {
    const v = await api("/api/rule-versions/seal", "POST");
    selectedVersionId = v.id;
    await loadRulesTab();
    toast(`已新建版本 v${v.version}`);
  } catch (err) { toast(err.message, true); }
});

function condText(cond) {
  const parts = [];
  if (cond.tag_a && cond.tag_b) parts.push(`${tagLabel(cond.tag_a)} × ${tagLabel(cond.tag_b)}`);
  if (cond.tag_self) parts.push(`含「${tagLabel(cond.tag_self)}」标签`);
  if (cond.min_concentration_pct != null) parts.push(`浓度≥${cond.min_concentration_pct}%`);
  if (cond.min_temperature_c != null) parts.push(`温度≥${cond.min_temperature_c}°C`);
  if (cond.materials && cond.materials.length) parts.push(`材质∈{${cond.materials.join("、")}}`);
  if (cond.event_types && cond.event_types.length) parts.push(`事件∈{${cond.event_types.map(t => EVENT_TYPES[t]).join("、")}}`);
  return parts.join("；") || "（无条件）";
}

async function loadRules() {
  rules = await api(`/api/rules?version_id=${selectedVersionId}`);
  const v = versions.find(x => x.id === selectedVersionId);
  const ro = v && v.is_sealed;
  $("#rule-table tbody").innerHTML = rules.map(r => `<tr>
    <td>${r.id}</td><td><span class="badge badge-cat">${CATEGORIES[r.category] || r.category}</span></td>
    <td>${esc(r.name)}</td>
    <td>${r.action === "forbid" ? '<span class="badge badge-forbid">禁止</span>' : '<span class="badge badge-review">需复核</span>'}</td>
    <td>${esc(condText(r.cond))}</td><td>${esc(r.message)}</td>
    <td>${ro ? "—" : `<button class="small" onclick="editRule(${r.id})">编辑</button>
      <button class="small danger" onclick="delRule(${r.id})">删除</button>`}</td></tr>`).join("");
}

function ruleFormData() {
  const cond = {};
  if ($("#rule-tag-a").value) cond.tag_a = $("#rule-tag-a").value;
  if ($("#rule-tag-b").value) cond.tag_b = $("#rule-tag-b").value;
  if ($("#rule-tag-self").value) cond.tag_self = $("#rule-tag-self").value;
  if ($("#rule-min-conc").value !== "") cond.min_concentration_pct = +$("#rule-min-conc").value;
  if ($("#rule-min-temp").value !== "") cond.min_temperature_c = +$("#rule-min-temp").value;
  const mats = [...$("#rule-materials").querySelectorAll("input:checked")].map(i => i.value);
  if (mats.length) cond.materials = mats;
  const evs = [...$("#rule-event-types").querySelectorAll("input:checked")].map(i => i.value);
  if (evs.length) cond.event_types = evs;
  return {
    name: $("#rule-name").value.trim(),
    category: $("#rule-category").value,
    action: $("#rule-action").value,
    cond,
    message: $("#rule-message").value.trim(),
  };
}

function resetRuleForm() {
  editingRuleId = null;
  $("#rule-form").reset();
  $("#rule-form-title").textContent = "新增规则";
  $("#rule-cancel").hidden = true;
}

$("#rule-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const data = ruleFormData();
  if (!data.cond.tag_self && !(data.cond.tag_a && data.cond.tag_b)) {
    toast("请填写「标签 A + 标签 B」（成对规则）或「单化学品标签」（腐蚀类）", true);
    return;
  }
  try {
    if (editingRuleId) await api(`/api/rules/${editingRuleId}`, "PUT", data);
    else await api("/api/rules", "POST", data);
    resetRuleForm();
    await loadRulesTab();
    toast("规则已保存");
  } catch (err) { toast(err.message, true); }
});
$("#rule-cancel").addEventListener("click", resetRuleForm);

window.editRule = (id) => {
  const r = rules.find(x => x.id === id);
  if (!r) return;
  editingRuleId = id;
  $("#rule-name").value = r.name;
  $("#rule-category").value = r.category;
  $("#rule-action").value = r.action;
  $("#rule-tag-a").value = r.cond.tag_a || "";
  $("#rule-tag-b").value = r.cond.tag_b || "";
  $("#rule-tag-self").value = r.cond.tag_self || "";
  $("#rule-min-conc").value = r.cond.min_concentration_pct ?? "";
  $("#rule-min-temp").value = r.cond.min_temperature_c ?? "";
  $("#rule-message").value = r.message || "";
  $("#rule-materials").querySelectorAll("input").forEach(i => (i.checked = (r.cond.materials || []).includes(i.value)));
  $("#rule-event-types").querySelectorAll("input").forEach(i => (i.checked = (r.cond.event_types || []).includes(i.value)));
  $("#rule-form-title").textContent = `编辑规则 #${id}`;
  $("#rule-cancel").hidden = false;
};

window.delRule = async (id) => {
  if (!confirm("确认删除该规则？")) return;
  try { await api(`/api/rules/${id}`, "DELETE"); await loadRulesTab(); toast("已删除"); }
  catch (err) { toast(err.message, true); }
};

/* ---------------- 审查 ---------------- */
async function loadReviewTab() {
  versions = await api("/api/rule-versions");
  const active = versions.find(v => v.is_active);
  $("#review-version").innerHTML = versions.map(v =>
    `<option value="${v.id}" ${active && v.id === active.id ? "selected" : ""}>v${v.version}${v.is_active ? "（当前）" : ""}${v.is_sealed ? "（已封存）" : ""}</option>`).join("");
  await loadReviewHistory();
}

async function loadReviewHistory() {
  const list = await api("/api/reviews");
  $("#review-history tbody").innerHTML = list.map(r => `<tr>
    <td>${r.id}</td><td>v${r.version}</td><td>${esc(r.created_at)}</td>
    <td><span class="badge badge-forbid">${r.summary.forbid}</span></td>
    <td><span class="badge badge-review">${r.summary.review}</span></td>
    <td><button class="small" onclick="showReview(${r.id})">查看</button></td></tr>`).join("");
}

$("#btn-run-review").addEventListener("click", async () => {
  try {
    const res = await api("/api/reviews", "POST", { version_id: +$("#review-version").value });
    renderReview(res);
    await loadReviewHistory();
    toast("审查完成");
  } catch (err) { toast(err.message, true); }
});

window.showReview = async (id) => {
  try {
    const res = await api(`/api/reviews/${id}`);
    renderReview(res);
    window.scrollTo(0, 0);
  } catch (err) { toast(err.message, true); }
};

function scopeText(f) {
  if (f.scope === "zone") return `分区「${f.zone}」现状`;
  if (f.scope === "container") return `分区「${f.zone}」容器`;
  if (f.scope === "event" && f.event)
    return `事件 #${f.event.id}（${EVENT_TYPES[f.event.event_type] || f.event.event_type}，顺序${f.event.seq}）后`;
  return "—";
}

function renderReview(res) {
  const s = res.summary;
  let html = `<div class="card"><h2>审查结果（规则版本 v${res.version}${res.review_id ? `，记录 #${res.review_id}` : ""}）</h2>
    <div class="summary-cards">
      <div class="summary-card danger"><div class="num">${s.forbid}</div><div class="lbl">禁止项</div></div>
      <div class="summary-card warn"><div class="num">${s.review}</div><div class="lbl">需人工复核</div></div>
      <div class="summary-card"><div class="num">${s.events_checked}</div><div class="lbl">检查事件</div></div>
      <div class="summary-card"><div class="num">${s.chemicals_checked}</div><div class="lbl">检查化学品</div></div>
    </div>`;

  if (res.earliest_conflict) {
    const ec = res.earliest_conflict;
    html += `<div class="banner danger">⚠️ <b>最早冲突：</b>${esc(ec.chemicals.join(" + "))}
      触发「${esc(ec.rule_name)}」（${esc(ec.category_label)}）—— ${esc(scopeText(ec))}。${esc(ec.reason)}</div>`;
  } else {
    html += `<div class="banner ok">✅ 未发现禁止项冲突。</div>`;
  }

  if (res.isolation && res.isolation.length) {
    html += `<h3>需隔离对象（${res.isolation.length}）</h3><div>` +
      res.isolation.map(i => `<span class="iso-chip"><b>${esc(i.name)}</b><small>${i.reasons.map(esc).join("；")}</small></span>`).join("") + `</div>`;
  }

  html += `<h3>逐项判定明细（${res.findings.length}）</h3>
    <table><thead><tr><th>判定</th><th>类别</th><th>规则</th><th>涉及化学品</th><th>范围/阶段</th><th>触发条件说明</th></tr></thead><tbody>` +
    res.findings.map(f => `<tr>
      <td>${f.action === "forbid" ? '<span class="badge badge-forbid">禁止</span>' : '<span class="badge badge-review">需复核</span>'}</td>
      <td><span class="badge badge-cat">${esc(f.category_label)}</span></td>
      <td>${esc(f.rule_name)}</td>
      <td>${esc(f.chemicals.join(" + "))}</td>
      <td>${esc(scopeText(f))}</td>
      <td>${esc(f.reason)}</td></tr>`).join("") +
    `</tbody></table></div>`;
  $("#review-result").innerHTML = html;
}

/* ---------------- 启动 ---------------- */
(async function init() {
  buildStaticOptions();
  toggleEventFields();
  try {
    await loadChemicals();
    await loadZones();
    await loadEvents();
  } catch (err) { toast(err.message, true); }
})();
