// The Setări page (M7): folders, archived companies, backup, about.
// Loaded after common.js (postJson, showResult). All checks happen on the server.
"use strict";

const FOLDER_KEYS = ["noi", "procesate", "erori"];

function folderBoxes() {
  // What she typed in the three boxes, as the server expects it.
  const form = document.getElementById("form-foldere");
  return Object.fromEntries(FOLDER_KEYS.map((key) => [key, form.elements[key].value]));
}

function setBusy(busy) {
  // Grey out the folder buttons while the server answers, so nothing is sent twice.
  for (const button of document.querySelectorAll("#form-foldere .butoane button")) {
    button.disabled = busy;
  }
}

function clearState(key) {
  const state = document.getElementById(`folder-${key}-stare`);
  state.hidden = true;
  state.textContent = "";
  delete state.dataset.ok;
  document.getElementById(`folder-${key}`).removeAttribute("aria-invalid");
}

function drawChecks(results) {
  // One ✓ or ✗ line under each box. The sign carries the meaning, the colour only helps.
  for (const result of results) {
    const state = document.getElementById(`folder-${result.cheie}-stare`);
    state.textContent = `${result.ok ? "✓" : "✗"} ${result.mesaj}`;
    state.dataset.ok = result.ok ? "da" : "nu";
    state.hidden = false;
    const input = document.getElementById(`folder-${result.cheie}`);
    if (result.ok) input.removeAttribute("aria-invalid");
    else input.setAttribute("aria-invalid", "true");
  }
}

function fillBoxes(paths) {
  // After a save or reset: show the paths exactly as saved (quotes and spaces removed).
  for (const key of FOLDER_KEYS) {
    document.getElementById(`folder-${key}`).value = paths[key];
    clearState(key);
  }
}

function focusFirstBad(results) {
  const bad = results.find((result) => !result.ok);
  if (bad) document.getElementById(`folder-${bad.cheie}`).focus();
}

// ---------- folders ----------

async function checkFolders() {
  setBusy(true);
  const body = await postJson("/setari/foldere/verifica", folderBoxes());
  setBusy(false);
  if (body.foldere) drawChecks(body.foldere);
  showResult(body.mesaj, body.ok ? "ok" : "eroare");
}

function showSaved(body) {
  // Green, or orange when PDFs were left in the old Facturi-noi.
  fillBoxes(body.foldere);
  const warn = body.avertizari.length > 0;
  showResult(body.mesaj, warn ? "atentie" : "ok", [...body.avertizari, ...body.note]);
}

async function saveFolders(event) {
  event.preventDefault();
  setBusy(true);
  const body = await postJson("/setari/foldere", folderBoxes());
  setBusy(false);
  if (body.ok) {
    showSaved(body);
    return;
  }
  if (body.foldere) {
    drawChecks(body.foldere);
    focusFirstBad(body.foldere);
  }
  showResult(body.mesaj, "eroare");
}

async function resetFolders() {
  setBusy(true);
  const body = await postJson("/setari/foldere/desktop");
  setBusy(false);
  if (body.ok) showSaved(body);
  else showResult(body.mesaj, "eroare");
}

async function openFolder(name) {
  // Only the folder's name goes to the server, never a path.
  const body = await postJson(`/setari/deschide/${name}`);
  if (!body.ok) showResult(body.mesaj, "eroare");
}

// ---------- backup ----------

async function backupNow() {
  const button = document.getElementById("backup-acum");
  button.disabled = true;
  const body = await postJson("/setari/backup");
  button.disabled = false;
  if (body.ok) {
    document.getElementById("backup-rezumat").textContent = body.rezumat;
    showResult(body.mesaj, "ok");
  } else {
    showResult(body.mesaj, "eroare");
  }
}

// ---------- archived companies ----------

async function restoreCompany(button) {
  const { restaureaza: firmaId, nume } = button.dataset;
  button.disabled = true;
  const body = await postJson(`/firme/${firmaId}/restaureaza`);
  if (!body.ok) {
    button.disabled = false;
    showResult(body.mesaj, "eroare");
    return;
  }
  button.closest("li").remove();
  const left = document.querySelectorAll("#arhivate-lista li").length;
  const title = document.getElementById("arhivate-titlu");
  title.textContent = `Firme arhivate (${left})`;
  document.getElementById("arhivate-gol").hidden = left > 0;
  showResult(`Firma ${nume} a fost restaurată. Apare din nou în tabel.`, "ok");
  // The clicked button is gone: go to the next Restaurează, or to the section title.
  const next = document.querySelector("#arhivate-lista button");
  (next || title).focus();
}

// ---------- wiring ----------

function wireSetari() {
  document.getElementById("form-foldere").addEventListener("submit", saveFolders);
  document.getElementById("verifica").addEventListener("click", checkFolders);
  document.getElementById("revino-desktop").addEventListener("click", resetFolders);
  document.getElementById("backup-acum").addEventListener("click", backupNow);
  for (const key of FOLDER_KEYS) {
    // An old ✓/✗ no longer matches once she edits the box.
    document.getElementById(`folder-${key}`).addEventListener("input", () => clearState(key));
  }
  for (const button of document.querySelectorAll("[data-deschide]")) {
    button.addEventListener("click", () => openFolder(button.dataset.deschide));
  }
  for (const button of document.querySelectorAll("[data-restaureaza]")) {
    button.addEventListener("click", () => restoreCompany(button));
  }
}

wireSetari();

// The browser's own Back/Forward arrows can show this page from memory (back/forward cache),
// as it was before a change made on the dashboard (e.g. a company archived). Load it afresh.
window.addEventListener("pageshow", (event) => {
  if (event.persisted) window.location.reload();
});
