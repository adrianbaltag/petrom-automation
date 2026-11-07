// Shared by the dashboard and the Setări page: talking to the server, and the result box
// (green = worked, orange = worked with problems, red = failed). Loaded first on both pages.
"use strict";

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

// ---------- the result box (#rezultat) ----------

function showResult(headline, kind, details = []) {
  // kind: "ok" (green), "atentie" (orange) or "eroare" (red). details: extra lines.
  const box = document.getElementById("rezultat");
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
