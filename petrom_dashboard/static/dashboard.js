// Dashboard page: loads the rows for the chosen period from /date (this month by default),
// then sorts, searches and pages them in the browser. Also runs the filters, the clock,
// the full-screen button and the "Rulează" button.
"use strict";

const ZILE = ["Duminică", "Luni", "Marți", "Miercuri", "Joi", "Vineri", "Sâmbătă"];
const NUMERIC = new Set(["total_bani", "max_bani", "procent"]);
const NULLS_LAST = new Set(["max_bani", "procent"]); // "Max nesetat" rows: always at the bottom

// Default sort per view: by % in a month, by amount in a date range (it has no %).
const DEFAULT_SORT = {
  luna: { col: "procent", dir: "desc" },
  perioada: { col: "total_bani", dir: "desc" },
};

const state = {
  rows: [],
  // The filter in use. luna: null = this month, and it follows the clock past midnight.
  // Others: { tip: "zile", zile: 7 } or { tip: "calendar", de: "2026-10-01", pana: "…" }.
  filter: { tip: "luna", luna: null },
  tip: "luna", // what the server last showed: "luna" or "perioada"
  day: null, // today as "YYYY-MM-DD" on this computer, to notice midnight
  sort: { ...DEFAULT_SORT.luna },
  search: "",
  page: 1,
};

const $ = (id) => document.getElementById(id);
const tbody = document.querySelector("#tabel tbody");
let lastRequest = 0; // only the newest answer is drawn, if quick clicks overlap

// ---------- data ----------

function queryFor(filter) {
  if (filter.tip === "zile") return `?zile=${filter.zile}`;
  if (filter.tip === "calendar") {
    return `?${new URLSearchParams({ de: filter.de, pana: filter.pana })}`;
  }
  return filter.luna ? `?luna=${filter.luna}` : "";
}

async function loadRows(filter = state.filter, newFilter = false) {
  // Loads the rows for `filter`. The filter is kept only if the server accepts it, so a
  // refused calendar range leaves the table (and later reloads) on the previous filter.
  // `newFilter`: she chose a filter, so an accepted answer starts again on page 1.
  const request = ++lastRequest;
  try {
    const response = await fetch(`/date${queryFor(filter)}`);
    const body = await response.json();
    if (request !== lastRequest) return;
    if (!body.ok) {
      if (response.status === 400) showFilterError(body.mesaj);
      else showResult(body.mesaj, "eroare");
      return;
    }
    showFilterError("");
    if (body.tip !== state.tip) state.sort = { ...DEFAULT_SORT[body.tip] };
    if (newFilter || body.tip !== state.tip) state.page = 1;
    state.filter = filter;
    state.tip = body.tip;
    state.rows = body.firme;
    drawFilters(body);
    render();
    setArchivedCount(body.arhivate); // firme.js: the "Firme arhivate (N)" link under the table
  } catch (err) {
    if (request === lastRequest) {
      showResult("Nu am putut citi datele: serverul nu răspunde.", "eroare");
    }
  }
}

function applyFilter(filter) {
  loadRows(filter, true);
}

// ---------- filters ----------

function showFilterError(text) {
  const box = $("filtru-eroare");
  box.textContent = text;
  box.hidden = !text;
}

function drawFilters(body) {
  const filter = state.filter;
  $("luna").textContent = body.titlu;
  $("tabel").dataset.tip = body.tip;
  $("tabel").setAttribute("aria-label", `Firme, ${body.titlu}`);
  $("titlu-suma").textContent = body.tip === "luna" ? "Suma lunii" : "Suma perioadei";
  $("nota-perioada").hidden = body.tip === "luna";

  const select = $("alege-luna");
  const placeholder = new Option("Alege luna…", "");
  placeholder.disabled = true;
  select.replaceChildren(placeholder, ...body.luni.map((m) => new Option(m.text, m.luna)));
  select.value = body.tip === "luna" ? body.luna : "";

  const thisMonth = body.tip === "luna" && body.luna === body.luni[0].luna;
  for (const button of document.querySelectorAll("[data-filtru]")) {
    const pressed =
      button.dataset.filtru === "luna"
        ? thisMonth
        : filter.tip === "zile" && String(filter.zile) === button.dataset.filtru;
    button.setAttribute("aria-pressed", String(pressed));
  }
  // A past month shows as the picked month in the list; a range as the filled date boxes.
  select.parentElement.toggleAttribute("data-activ", body.tip === "luna" && !thisMonth);
  $("form-calendar").toggleAttribute("data-activ", filter.tip === "calendar");
}

function pickMonth() {
  const luna = $("alege-luna").value;
  const thisMonth = $("alege-luna").options[1]?.value;
  // Picking this month is the same as "Luna curentă": it follows the clock at midnight.
  applyFilter({ tip: "luna", luna: luna === thisMonth ? null : luna });
}

function applyCalendar(event) {
  event.preventDefault();
  applyFilter({ tip: "calendar", de: $("data-de").value, pana: $("data-pana").value });
}

function isoDay(date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function setDay(day) {
  // The date boxes can't go past today (the server refuses future dates too).
  state.day = day;
  $("data-de").max = day;
  $("data-pana").max = day;
}

// ---------- sort and search ----------

function plain(text) {
  // Lower case without diacritics, so "petrom" finds "PETROM" and "brasov" finds "Brașov".
  return text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

function compareRows(a, b) {
  const { col, dir } = state.sort;
  const x = a[col];
  const y = b[col];
  if (NULLS_LAST.has(col) && (x === null) !== (y === null)) {
    return x === null ? 1 : -1;
  }
  let result = 0;
  if (NUMERIC.has(col)) {
    result = (x ?? 0) - (y ?? 0);
  } else {
    result = String(x).localeCompare(String(y), "ro", { numeric: true });
  }
  if (dir === "desc") result = -result;
  return result || a.nume.localeCompare(b.nume, "ro");
}

function visibleRows() {
  const query = plain(state.search.trim());
  const rows = query
    ? state.rows.filter((r) => plain(r.nume).includes(query) || r.cui.includes(query))
    : state.rows.slice();
  return rows.sort(compareRows);
}

// ---------- drawing the table ----------

function makeNameCell(r) {
  // Company name, cut short with "…" when long, then the "✎ Editează" button (firme.js).
  const td = document.createElement("td");
  const box = document.createElement("div");
  box.className = "nume-cel";
  const name = document.createElement("span");
  name.className = "nume-text";
  name.textContent = r.nume;
  name.title = r.nume;
  const edit = document.createElement("button");
  edit.type = "button";
  edit.className = "btn btn-mic btn-editeaza";
  edit.setAttribute("aria-label", `Editează ${r.nume}`);
  edit.dataset.firma = String(r.id);
  const pencil = document.createElement("span");
  pencil.setAttribute("aria-hidden", "true");
  pencil.textContent = "✎";
  const word = document.createElement("span");
  word.className = "editeaza-text";
  word.textContent = "Editează";
  edit.append(pencil, word);
  edit.addEventListener("click", () => openEdit(r));
  box.append(name, edit);
  td.appendChild(box);
  return td;
}

function makeRow(r) {
  const tr = document.createElement("tr");
  tr.dataset.stare = r.stare;
  tr.appendChild(makeNameCell(r));
  const cells = [
    [r.cui, ""],
    [r.suma_text, "num"],
    [r.max_text, "num"],
    [r.procent_text, "num"],
    [r.eticheta, "stare"],
  ];
  for (const [text, cls] of cells) {
    const td = document.createElement("td");
    td.textContent = text;
    if (cls) td.className = cls;
    if (text) td.title = text; // full text on hover when a long name is cut short
    tr.appendChild(td);
  }
  return tr;
}

function rowsPerPage(sample) {
  // How many rows fit in the space left for the table: no page scroll, ever.
  const space = $("tabel-loc").clientHeight - document.querySelector("#tabel thead").offsetHeight;
  tbody.replaceChildren(makeRow(sample));
  const rowHeight = tbody.firstElementChild.getBoundingClientRect().height || 1;
  return Math.max(1, Math.floor(space / rowHeight));
}

function render() {
  // Redrawing replaces every row. If an Editează button had keyboard focus, give it back
  // to the same company's new button afterwards, so keyboard users keep their place.
  const focused = document.activeElement?.closest?.(".btn-editeaza")?.dataset.firma;
  const rows = visibleRows();
  const perPage = rows.length ? rowsPerPage(rows[0]) : 1;
  const pages = Math.max(1, Math.ceil(rows.length / perPage));
  state.page = Math.min(Math.max(1, state.page), pages);

  const start = (state.page - 1) * perPage;
  tbody.replaceChildren(...rows.slice(start, start + perPage).map(makeRow));
  if (focused) tbody.querySelector(`.btn-editeaza[data-firma="${focused}"]`)?.focus();

  const empty = $("gol");
  empty.hidden = rows.length > 0;
  empty.textContent = state.rows.length ? "Nicio firmă găsită." : "Nicio firmă încă.";

  drawPager(pages, rows.length);
  drawSortArrows();
}

function pageList(pages, current) {
  // All numbers when few; otherwise first, last and the ones next to the current page.
  if (pages <= 9) return Array.from({ length: pages }, (_, i) => i + 1);
  const keep = new Set([1, pages, current - 1, current, current + 1]);
  const list = [];
  for (let p = 1; p <= pages; p++) {
    if (keep.has(p)) list.push(p);
    else if (list[list.length - 1] !== "…") list.push("…");
  }
  return list;
}

function drawPager(pages, count) {
  const holder = $("numere-pagini");
  holder.replaceChildren();
  for (const p of pageList(pages, state.page)) {
    if (p === "…") {
      const gap = document.createElement("span");
      gap.textContent = "…";
      holder.appendChild(gap);
      continue;
    }
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn btn-mic";
    button.textContent = String(p);
    button.setAttribute("aria-label", `Pagina ${p}`);
    if (p === state.page) button.setAttribute("aria-current", "page");
    button.addEventListener("click", () => {
      state.page = p;
      render();
    });
    holder.appendChild(button);
  }
  $("inapoi").disabled = state.page <= 1;
  $("inainte").disabled = state.page >= pages;
  const firme = count === 1 ? "1 firmă" : `${count} firme`;
  $("paginare-info").textContent = `Pagina ${state.page} din ${pages} · ${firme}`;
}

function drawSortArrows() {
  for (const button of document.querySelectorAll("#tabel th button")) {
    const th = button.parentElement;
    const active = button.dataset.col === state.sort.col;
    th.setAttribute("aria-sort", active ? (state.sort.dir === "asc" ? "ascending" : "descending") : "none");
    button.querySelector(".sageata").textContent = active ? (state.sort.dir === "asc" ? " ▲" : " ▼") : "";
  }
}

// ---------- the run button ----------

function showResult(headline, kind, details = []) {
  const box = $("rezultat");
  box.dataset.tip = kind;
  const text = document.createElement("p");
  text.className = "rezultat-titlu";
  text.textContent = headline;
  const parts = [text];
  if (details.length) {
    const list = document.createElement("ul");
    for (const line of details) {
      const li = document.createElement("li");
      li.textContent = line;
      list.appendChild(li);
    }
    parts.push(list);
  }
  const close = document.createElement("button");
  close.type = "button";
  close.className = "btn btn-mic rezultat-inchide";
  close.textContent = "Închide";
  close.addEventListener("click", () => {
    box.hidden = true;
  });
  parts.push(close);
  box.replaceChildren(...parts);
  box.hidden = false;
}

async function runAutomation() {
  const button = $("ruleaza");
  button.disabled = true;
  button.textContent = "Rulează automatizarea…";
  try {
    const response = await fetch("/ruleaza", { method: "POST" });
    let body;
    try {
      body = await response.json();
    } catch (err) {
      body = { ok: false, mesaj: "Automatizarea s-a oprit din cauza unei erori neașteptate." };
    }
    if (body.ok) {
      const details = [
        ...body.erori.map((e) => `${e.fisier}: ${e.motiv}`),
        ...body.note,
      ];
      showResult(body.mesaj, body.erori.length ? "atentie" : "ok", details);
    } else {
      showResult(body.mesaj, "eroare");
    }
  } catch (err) {
    showResult("Nu am putut porni automatizarea: serverul nu răspunde.", "eroare");
  } finally {
    button.disabled = false;
    button.textContent = "Rulează automatizarea";
  }
  await loadRows();
}

// ---------- clock and full screen ----------

function pad(n) {
  return String(n).padStart(2, "0");
}

function tick() {
  const now = new Date();
  $("ceas").textContent =
    `${ZILE[now.getDay()]}, ${pad(now.getDate())}.${pad(now.getMonth() + 1)}.${now.getFullYear()}` +
    ` · ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
  // Left open past midnight: "Luna curentă" moves to a new month and 7 / 30 days move one
  // day forward. A picked month or calendar range stays; it is reloaded on a new month
  // only so the month list gains the new month.
  const day = isoDay(now);
  if (state.day && day !== state.day) {
    const newMonth = day.slice(0, 7) !== state.day.slice(0, 7);
    setDay(day);
    if (newMonth || state.filter.tip === "zile") loadRows();
  }
}

function toggleFullScreen() {
  if (document.fullscreenElement) {
    document.exitFullscreen();
  } else {
    document.documentElement.requestFullscreen().catch(() => {});
  }
}

document.addEventListener("fullscreenchange", () => {
  $("ecran").textContent = document.fullscreenElement ? "Ieși din ecran complet" : "Ecran complet";
});

// ---------- wiring ----------

for (const button of document.querySelectorAll("#tabel th button")) {
  button.addEventListener("click", () => {
    const col = button.dataset.col;
    if (state.sort.col === col) {
      state.sort.dir = state.sort.dir === "asc" ? "desc" : "asc";
    } else {
      state.sort = { col, dir: NUMERIC.has(col) ? "desc" : "asc" };
    }
    state.page = 1;
    render();
  });
}

$("cautare").addEventListener("input", (event) => {
  state.search = event.target.value;
  state.page = 1;
  render();
});
$("inapoi").addEventListener("click", () => {
  state.page -= 1;
  render();
});
$("inainte").addEventListener("click", () => {
  state.page += 1;
  render();
});
for (const button of document.querySelectorAll("[data-filtru]")) {
  button.addEventListener("click", () => {
    const which = button.dataset.filtru;
    applyFilter(which === "luna" ? { tip: "luna", luna: null } : { tip: "zile", zile: Number(which) });
  });
}
$("alege-luna").addEventListener("change", pickMonth);
$("form-calendar").addEventListener("submit", applyCalendar);
$("ruleaza").addEventListener("click", runAutomation);
$("ecran").addEventListener("click", toggleFullScreen);
wireFirme(); // firme.js: add, edit, archive and restore windows

// Window resized, or the result box opened or closed: re-fit the rows per page.
new ResizeObserver(() => render()).observe($("tabel-loc"));

setDay(isoDay(new Date()));
tick();
setInterval(tick, 1000);
loadRows();
