// Changes by hand (M5): add a company, edit its name and max, list and delete this month's
// invoices, archive and restore. Loaded before dashboard.js, which calls wireFirme() and
// whose loadRows() / showResult() this file uses.
"use strict";

let editing = null; // the company open in the edit window: a row from /date
let archivedList = [];

// ---------- talking to the server ----------

async function readAnswer(response) {
  try {
    return await response.json();
  } catch (err) {
    return { ok: false, mesaj: "Răspuns neașteptat de la server (detalii în jurnal)." };
  }
}

async function getJson(url) {
  try {
    return await readAnswer(await fetch(url));
  } catch (err) {
    return { ok: false, mesaj: "Serverul nu răspunde." };
  }
}

async function postJson(url, data = {}) {
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    return await readAnswer(response);
  } catch (err) {
    return { ok: false, mesaj: "Serverul nu răspunde." };
  }
}

// ---------- small helpers ----------

function showFormError(holder, message, action = null) {
  const box = holder.querySelector(".form-eroare");
  const text = document.createElement("p");
  text.textContent = message;
  const parts = [text];
  if (action) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn btn-mic";
    button.textContent = action.label;
    button.addEventListener("click", action.onClick);
    parts.push(button);
  }
  box.replaceChildren(...parts);
  box.hidden = false;
}

function clearFormError(holder) {
  const box = holder.querySelector(".form-eroare");
  box.replaceChildren();
  box.hidden = true;
}

function setBusy(form, busy) {
  form.querySelector("[type=submit]").disabled = busy;
}

function focusCompany(firmaId) {
  // After the table is redrawn, put keyboard focus back on that company's Editează
  // button. Not on this page (or gone): fall back to "Adaugă firmă".
  const button = document.querySelector(`.btn-editeaza[data-firma="${firmaId}"]`);
  (button || document.getElementById("adauga")).focus();
}

function confirmBox(title, text, yesLabel) {
  // Our own "Are you sure?" window, in Romanian. Resolves true only on the yes button.
  const dlg = document.getElementById("dialog-confirma");
  document.getElementById("confirma-titlu").textContent = title;
  document.getElementById("confirma-text").textContent = text;
  document.getElementById("confirma-da").textContent = yesLabel;
  dlg.returnValue = "";
  dlg.showModal();
  return new Promise((resolve) => {
    dlg.addEventListener("close", () => resolve(dlg.returnValue === "da"), { once: true });
  });
}

// ---------- add ----------

function openAdd() {
  const dlg = document.getElementById("dialog-adauga");
  const form = document.getElementById("form-adauga");
  form.reset();
  clearFormError(form);
  dlg.showModal();
}

async function restoreFromAdd(firma) {
  // The max typed in the form is used; the name stays the one from the company's history.
  const form = document.getElementById("form-adauga");
  const body = await postJson(`/firme/${firma.id}/restaureaza`, { max: form.elements.max.value });
  if (!body.ok) {
    showFormError(form, body.mesaj);
    return;
  }
  document.getElementById("dialog-adauga").close();
  await loadRows();
  const newMax = body.max_text ? ` Max-ul nou: ${body.max_text}.` : "";
  showResult(`Firma ${firma.nume} a fost restaurată, cu istoricul ei.${newMax}`, "ok");
  focusCompany(firma.id);
}

async function submitAdd(event) {
  event.preventDefault();
  const form = event.target;
  const data = Object.fromEntries(new FormData(form));
  clearFormError(form);
  setBusy(form, true);
  const body = await postJson("/firme", data);
  setBusy(form, false);
  if (body.ok) {
    document.getElementById("dialog-adauga").close();
    await loadRows();
    showResult(`Firma ${data.nume.trim()} a fost adăugată.`, "ok");
    focusCompany(body.id);
  } else if (body.arhivata) {
    showFormError(form, body.mesaj, {
      label: "Restaurează",
      onClick: () => restoreFromAdd(body.arhivata),
    });
  } else {
    showFormError(form, body.mesaj);
  }
}

// ---------- edit ----------

function openEdit(row) {
  editing = row;
  const form = document.getElementById("form-firma");
  form.reset();
  clearFormError(form);
  form.elements.nume.value = row.nume;
  form.elements.max.value = row.max_input; // "5.000,00" from the server, "" if unset
  document.getElementById("firma-cui").textContent = row.cui;
  document.getElementById("facturi-stare").textContent = "";
  document.getElementById("facturi-lista").replaceChildren();
  document.getElementById("dialog-firma").showModal();
  loadInvoices();
}

async function submitEdit(event) {
  event.preventDefault();
  const form = event.target;
  const data = { nume: form.elements.nume.value, max: form.elements.max.value };
  clearFormError(form);
  setBusy(form, true);
  const firmaId = editing.id;
  const body = await postJson(`/firme/${firmaId}`, data);
  setBusy(form, false);
  if (!body.ok) {
    showFormError(form, body.mesaj);
    return;
  }
  document.getElementById("dialog-firma").close();
  await loadRows();
  showResult(`Modificările pentru ${data.nume.trim()} au fost salvate.`, "ok");
  focusCompany(firmaId);
}

async function loadInvoices() {
  const list = document.getElementById("facturi-lista");
  const firma = editing;
  if (!firma) return; // the window was closed meanwhile
  const body = await getJson(`/firme/${firma.id}/facturi`);
  if (editing !== firma) return; // the window was closed or another company opened meanwhile
  if (!body.ok) {
    document.getElementById("facturi-stare").textContent = body.mesaj;
    return;
  }
  document.getElementById("facturi-titlu").textContent = `Facturi, ${body.luna_text}`;
  if (!body.facturi.length) {
    const li = document.createElement("li");
    li.className = "ajutor";
    li.textContent = "Nicio factură luna aceasta.";
    list.replaceChildren(li);
    return;
  }
  list.replaceChildren(...body.facturi.map(makeInvoiceItem));
}

function makeInvoiceItem(factura) {
  const li = document.createElement("li");
  const text = document.createElement("div");
  text.className = "lista-text";
  const main = document.createElement("span");
  main.textContent = `${factura.data_text} · ${factura.numar} · ${factura.total_text}`;
  const file = document.createElement("span");
  file.className = "ajutor";
  file.textContent = factura.fisier;
  file.title = factura.fisier;
  text.append(main, file);
  const button = document.createElement("button");
  button.type = "button";
  button.className = "btn btn-mic";
  button.textContent = "Șterge";
  button.setAttribute("aria-label", `Șterge factura ${factura.numar}`);
  button.addEventListener("click", () => deleteInvoice(factura));
  li.append(text, button);
  return li;
}

async function deleteInvoice(factura) {
  const firma = editing;
  const yes = await confirmBox(
    "Ștergi factura?",
    `Ștergi factura ${factura.numar} (${factura.total_text})? Suma lunii scade. ` +
      "PDF-ul rămâne în Facturi-procesate. Înainte se face o copie de siguranță a datelor.",
    "Da, șterge",
  );
  if (!yes) return;
  const body = await postJson(`/facturi/${factura.id}/sterge`);
  const message = body.ok ? `Factura ${factura.numar} a fost ștearsă.` : body.mesaj;
  await loadRows(); // first: the table must update even if the window was closed meanwhile
  if (editing !== firma) {
    // Closed, or another company opened meanwhile: say it on the page, not in that window.
    showResult(message, body.ok ? "ok" : "eroare");
    return;
  }
  document.getElementById("facturi-stare").textContent = message;
  await loadInvoices();
  document.getElementById("facturi-titlu").focus(); // the clicked button is gone
}

async function archiveCompany() {
  const firma = editing;
  const yes = await confirmBox(
    "Arhivezi firma?",
    `${firma.nume} dispare din tabel. Istoricul rămâne. ` +
      "Revine automat dacă vine o factură nouă pentru ea.",
    "Da, arhivează",
  );
  if (!yes) return;
  const body = await postJson(`/firme/${firma.id}/arhiveaza`);
  if (!body.ok) {
    showFormError(document.getElementById("form-firma"), body.mesaj);
    return;
  }
  document.getElementById("dialog-firma").close();
  await loadRows();
  showResult(`Firma ${firma.nume} a fost arhivată. O găsești la „Firme arhivate”, sub tabel.`, "ok");
  document.getElementById("arhivate").focus();
}

// ---------- archived companies ----------

function setArchivedCount(count) {
  // Called by loadRows() with the count from /date: the link shows only when N > 0.
  const link = document.getElementById("arhivate");
  link.hidden = !count;
  link.textContent = `Firme arhivate (${count})`;
}

async function refreshArchived() {
  // The list itself is fetched only for the "Firme arhivate" window.
  const dlg = document.getElementById("dialog-arhivate");
  const body = await getJson("/firme/arhivate");
  if (!body.ok) {
    // Keep the link and its count: the archived companies still exist.
    showFormError(dlg, body.mesaj);
    archivedList = [];
    return;
  }
  archivedList = body.firme;
  setArchivedCount(archivedList.length);
}

function drawArchived() {
  const list = document.getElementById("arhivate-lista");
  list.replaceChildren(
    ...archivedList.map((firma) => {
      const li = document.createElement("li");
      const text = document.createElement("div");
      text.className = "lista-text";
      const name = document.createElement("span");
      name.textContent = firma.nume;
      name.title = firma.nume;
      const cui = document.createElement("span");
      cui.className = "ajutor";
      cui.textContent = `CUI ${firma.cui}`;
      text.append(name, cui);
      const button = document.createElement("button");
      button.type = "button";
      button.className = "btn btn-mic";
      button.textContent = "Restaurează";
      button.setAttribute("aria-label", `Restaurează ${firma.nume}`);
      button.addEventListener("click", () => restoreCompany(firma));
      li.append(text, button);
      return li;
    }),
  );
}

async function openArchived() {
  const dlg = document.getElementById("dialog-arhivate");
  clearFormError(dlg);
  await refreshArchived();
  drawArchived();
  dlg.showModal();
}

async function restoreCompany(firma) {
  const dlg = document.getElementById("dialog-arhivate");
  const body = await postJson(`/firme/${firma.id}/restaureaza`);
  if (!body.ok) {
    showFormError(dlg, body.mesaj);
    return;
  }
  clearFormError(dlg);
  await loadRows();
  await refreshArchived();
  drawArchived();
  showResult(`Firma ${firma.nume} a fost restaurată.`, "ok");
  if (archivedList.length) {
    // The clicked button is gone: go to the first Restaurează left.
    dlg.querySelector("#arhivate-lista button").focus();
  } else {
    dlg.close();
    focusCompany(firma.id);
  }
}

// ---------- wiring (called once by dashboard.js) ----------

function wireFirme() {
  document.getElementById("adauga").addEventListener("click", openAdd);
  document.getElementById("form-adauga").addEventListener("submit", submitAdd);
  document.getElementById("form-firma").addEventListener("submit", submitEdit);
  document.getElementById("arhiveaza").addEventListener("click", archiveCompany);
  document.getElementById("arhivate").addEventListener("click", openArchived);
  document.getElementById("dialog-firma").addEventListener("close", () => {
    editing = null;
  });
  for (const button of document.querySelectorAll("[data-inchide]")) {
    button.addEventListener("click", () => button.closest("dialog").close());
  }
}
