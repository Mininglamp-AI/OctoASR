// Mention Replacements — frontend logic
// Talks to the /v1/mentions API exposed by server.py.

const API = "/v1/mentions";

const tbody = document.getElementById("tbody");
const emptyEl = document.getElementById("empty");
const tableEl = document.getElementById("table");
const messageEl = document.getElementById("message");

let editingIndex = null; // index currently in inline-edit mode, or null

function showMessage(text, type) {
  messageEl.textContent = text;
  messageEl.className = "message " + type;
  messageEl.hidden = false;
  if (type === "success") {
    setTimeout(() => { messageEl.hidden = true; }, 2500);
  }
}

function clearMessage() {
  messageEl.hidden = true;
}

async function request(method, url, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(url, opts);
  let data = {};
  try { data = await res.json(); } catch (e) { /* ignore */ }
  if (!res.ok || data.ok === false) {
    const msg = (data && (data.error || data.msg)) ? (data.error || data.msg) : `Request failed (${res.status})`;
    throw new Error(msg);
  }
  return data;
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function render(items) {
  tbody.innerHTML = "";

  if (!items.length) {
    tableEl.hidden = true;
    emptyEl.hidden = false;
    return;
  }
  tableEl.hidden = false;
  emptyEl.hidden = true;

  items.forEach((item, index) => {
    const tr = document.createElement("tr");

    if (index === editingIndex) {
      tr.innerHTML = `
        <td><input class="row-input" id="edit-nick" value="${escapeHtml(item.nickname)}"></td>
        <td><input class="row-input" id="edit-canon" value="${escapeHtml(item.canonical_name)}"></td>
        <td class="actions">
          <button class="btn btn-primary btn-sm" data-act="save" data-i="${index}">Save</button>
          <button class="btn btn-secondary btn-sm" data-act="cancel">Cancel</button>
        </td>`;
    } else {
      tr.innerHTML = `
        <td>${escapeHtml(item.nickname)}</td>
        <td>${escapeHtml(item.canonical_name)}</td>
        <td class="actions">
          <button class="btn btn-secondary btn-sm" data-act="edit" data-i="${index}">Edit</button>
          <button class="btn btn-danger btn-sm" data-act="delete" data-i="${index}">Delete</button>
        </td>`;
    }
    tbody.appendChild(tr);
  });
}

async function load() {
  try {
    const data = await request("GET", API);
    render(data.items || []);
  } catch (e) {
    showMessage(e.message, "error");
  }
}

// Add
document.getElementById("add-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  clearMessage();
  const nickname = document.getElementById("add-nickname").value.trim();
  const canonical_name = document.getElementById("add-canonical").value.trim();
  if (!nickname || !canonical_name) {
    showMessage("Both fields are required.", "error");
    return;
  }
  try {
    const data = await request("POST", API, { nickname, canonical_name });
    document.getElementById("add-nickname").value = "";
    document.getElementById("add-canonical").value = "";
    showMessage("Added.", "success");
    render(data.items || []);
  } catch (e) {
    showMessage(e.message, "error");
  }
});

// Delegated actions for table buttons
tbody.addEventListener("click", async (e) => {
  const btn = e.target.closest("button");
  if (!btn) return;
  const act = btn.dataset.act;
  const i = btn.dataset.i !== undefined ? parseInt(btn.dataset.i, 10) : null;
  clearMessage();

  if (act === "edit") {
    editingIndex = i;
    load();
  } else if (act === "cancel") {
    editingIndex = null;
    load();
  } else if (act === "save") {
    const nickname = document.getElementById("edit-nick").value.trim();
    const canonical_name = document.getElementById("edit-canon").value.trim();
    if (!nickname || !canonical_name) {
      showMessage("Both fields are required.", "error");
      return;
    }
    try {
      const data = await request("PUT", `${API}/${i}`, { nickname, canonical_name });
      editingIndex = null;
      showMessage("Saved.", "success");
      render(data.items || []);
    } catch (err) {
      showMessage(err.message, "error");
    }
  } else if (act === "delete") {
    if (!confirm("Delete this replacement?")) return;
    try {
      const data = await request("DELETE", `${API}/${i}`);
      showMessage("Deleted.", "success");
      render(data.items || []);
    } catch (err) {
      showMessage(err.message, "error");
    }
  }
});

load();
