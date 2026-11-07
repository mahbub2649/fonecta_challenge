// The owner's page: one tap, no login. Everything is built with textContent, so no data can inject markup.
const token = location.pathname.split("/").pop();
const api = `/api/o/${token}`;
const app = document.getElementById("app");
let view = null;
let open = {}; // Which card is showing its edit or decline form: {itemId: "edit" | "decline"}.
let hideOffer = false;
let busy = false;
let tell = {state: "idle", text: ""}; // The "in your own words" box: idle, recording, busy, confirm, question, unavailable or nomic.
let recorder = null;
let spokenReply = false; // Connect only talks back to someone who spoke to it.
const captions = new URLSearchParams(location.search).get("captions") === "1"; // For reviewers. Owners see only their own language.

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "on") node.addEventListener("click", value);
    else if (key === "cls") node.className = value;
    else if (value !== null && value !== undefined) node[key] = value;
  }
  for (const child of children) if (child !== null && child !== undefined) node.append(child);
  return node;
}

function englishFor() {
  const map = new Map();
  const sameHours = (a, b) => a.replaceAll(".", ":") === b.replaceAll(".", ":"); // 7.30–13 and 7:30–13 need no caption.
  const add = (text, english) => { if (text && english && !sameHours(text, english)) map.set(text, english); };
  for (const [key, text] of Object.entries(view.ui)) add(text, view.ui_en[key]);
  const count = String(pendingItems().length);
  add(view.ui.approve_all_n.replace("{n}", count), view.ui_en.approve_all_n.replace("{n}", count));
  for (const item of view.items) {
    for (const key of ["day", "date", "shown", "proposed_label", "reason", "final_label"]) add(item[key], item.en[key]);
    if (item.final_label) add(`✓ ${item.final_label}`, `✓ ${item.en.final_label}`);
    if (item.views) add(view.ui.views.replace("{n}", item.views), view.ui_en.views.replace("{n}", item.views));
    if (item.alternative) add(view.ui.alternative.replace("{hours}", item.alternative_label), view.ui_en.alternative.replace("{hours}", item.en.alternative_label));
  }
  for (const listing of view.listings) add(listing.eta, listing.eta_en);
  for (const update of view.regular_updates) { add(update.days, update.days_en); add(update.hours, update.hours_en); }
  for (const row of tell.rows || []) { add(row.label, row.label_en); add(row.before, row.before_en); add(row.after, row.after_en); }
  if (tell.question) add(tell.question, tell.question_en);
  if (tell.text) add(tell.text, tell.reply_en);
  return map;
}

// Puts a small English line under any text that has a translation. It doesn't change what the buttons do.
function addCaptions(root) {
  if (!captions || !view || view.language === "en") return;
  const map = englishFor();
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  for (const node of nodes) {
    const english = map.get(node.textContent.trim());
    if (!english || node.parentElement.classList.contains("caption") || node.nextSibling?.classList?.contains("caption")) continue;
    node.after(el("small", {cls: "caption", textContent: english}));
  }
}

async function post(path, body) {
  if (busy) return;
  busy = true;
  // Nothing redraws while saving, so a form keeps what the owner typed if the save fails.
  const notice = el("div", {cls: "saving", role: "status", textContent: view.ui.saving});
  addCaptions(notice);
  document.body.append(notice);
  app.inert = true;
  let errorText = null;
  try {
    const response = await fetch(`${api}${path}`, {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error === "expired" ? view.ui.expired : (data.error || view.ui.failed));
    view = data;
    open = {};
    if (spokenReply) playSpeech(data.speech_id);
  } catch (error) {
    errorText = error.message;
  }
  busy = false;
  app.inert = false;
  notice.remove();
  if (errorText) {
    const problem = el("p", {cls: "error", role: "alert", textContent: errorText});
    addCaptions(problem);
    app.prepend(problem);
    window.scrollTo(0, 0);
  } else {
    render();
  }
}

const decide = (decisions) => post("/decide", {decisions});

function pendingItems() {
  return view.items.filter((i) => i.decision === "PENDING" || i.decision === "NO_REPLY");
}

function editForm(item) {
  const ui = view.ui;
  const existing = item.proposed === "closed" ? [] : item.proposed.split(",").map((p) => p.split("-"));
  let periods = existing.length ? existing.slice(0, 2) : [["10:00", "16:00"]];
  let closed = item.proposed === "closed";
  const body = el("div");
  const message = el("p", {cls: "error", hidden: true});

  function paint() {
    const inputs = closed ? null : el("div", {},
      ...periods.map((period, index) => el("div", {cls: "times"},
        el("label", {}, ui.from, el("input", {type: "time", value: period[0], required: true,
          oninput: (e) => { periods[index][0] = e.target.value; }})),
        el("label", {}, ui.to, el("input", {type: "time", value: period[1], required: true,
          oninput: (e) => { periods[index][1] = e.target.value; }})))),
      periods.length === 1
        ? el("button", {type: "button", cls: "link", textContent: ui.add_period,
            on: () => { periods.push(["17:00", "22:00"]); paint(); }})
        : el("button", {type: "button", cls: "link", textContent: ui.remove_period,
            on: () => { periods = periods.slice(0, 1); paint(); }}));
    body.replaceChildren(
      el("label", {cls: "check"},
        el("input", {type: "checkbox", checked: closed, onchange: (e) => { closed = e.target.checked; paint(); }}),
        ui.closed_toggle),
      inputs ?? "");
    addCaptions(body);
  }
  paint();

  return el("form", {
    onsubmit: (event) => {
      event.preventDefault();
      const hours = closed ? "closed" : periods.map((p) => `${p[0]}-${p[1]}`).join(",");
      if (!closed && periods.some((p) => !p[0] || !p[1])) {
        message.textContent = ui.invalid;
        message.hidden = false;
        return;
      }
      decide([{item: item.id, action: "edit", hours}]);
    },
  }, body, message, el("div", {cls: "row"},
    el("button", {type: "submit", cls: "primary", textContent: ui.save}),
    el("button", {type: "button", cls: "quiet", textContent: ui.cancel, on: () => { delete open[item.id]; render(); }})));
}

function declineForm(item) {
  const ui = view.ui;
  const choice = (reason, label) => el("button", {type: "button", textContent: label,
    on: () => decide([{item: item.id, action: "decline", reason}])});
  return el("div", {cls: "reasons"},
    el("p", {textContent: ui.why_decline}),
    choice("open_as_usual", ui.r_open_as_usual),
    choice("dont_ask", ui.r_dont_ask),
    choice("wrong", ui.r_wrong),
    choice("stop", ui.r_stop),
    choice("", ui.skip));
}

async function playSpeech(speechId) {
  if (!speechId) return;
  try {
    const response = await fetch(`${api}/speak`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({speech_id: speechId})});
    if (!response.ok) return;
    const audio = new Audio(URL.createObjectURL(await response.blob()));
    await audio.play();
  } catch { /* A phone can block playback. The words are on screen, and Listen tries again. */ }
}

function canRecord() {
  return view.voice_enabled && navigator.mediaDevices?.getUserMedia && window.MediaRecorder;
}

async function startRecording() {
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({audio: true});
  } catch {
    tell = {state: "nomic", text: ""};
    render();
    return;
  }
  const chunks = [];
  recorder = new MediaRecorder(stream);
  recorder.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
  recorder.onstop = () => {
    stream.getTracks().forEach((track) => track.stop());
    clearTimeout(recorder.limit);
    const type = (recorder.mimeType || "audio/webm").split(";")[0];
    recorder = null;
    sendRecording(new Blob(chunks, {type}), type);
  };
  recorder.limit = setTimeout(() => { if (recorder?.state === "recording") recorder.stop(); }, 20000);
  recorder.start();
  tell = {state: "recording", text: ""};
  render();
}

async function sendRecording(blob, type) {
  tell = {state: "busy", text: ""};
  render();
  try {
    const response = await fetch(`${api}/transcribe`, {method: "POST", headers: {"Content-Type": type}, body: blob});
    const data = await response.json();
    if (!response.ok || data.status !== "heard") throw new Error();
    spokenReply = true;
    await askAgent(data.text);
  } catch {
    tell = {state: "unavailable", text: ""};
    render();
  }
}

async function askAgent(text) {
  tell = {state: "busy", text};
  render();
  try {
    const response = await fetch(`${api}/interpret`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({text})});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error);
    tell = {state: data.status, text, ...data};
  } catch {
    tell = {state: "unavailable", text};
  }
  render();
  if (spokenReply) playSpeech(tell.speech_id);
}

function tellCard() {
  const ui = view.ui;
  if (!view.agent_enabled) return null;
  if (tell.state === "confirm") {
    return el("section", {cls: "card tell"},
      el("h2", {textContent: ui.tell_check}),
      el("p", {cls: "said"}, el("small", {textContent: ui.tell_you}), el("span", {textContent: tell.text})),
      el("div", {cls: "plan"}, ...tell.rows.map((row) => el("div", {cls: "plan-row"},
        el("div", {cls: "plan-day", textContent: row.label}),
        el("div", {cls: "plan-change"},
          el("span", {cls: "was", textContent: row.before}),
          el("span", {cls: "arrow", textContent: "→", ariaHidden: "true"}),
          el("strong", {textContent: row.after}))))),
      el("div", {cls: "row"},
        el("button", {type: "button", cls: "primary", textContent: ui.tell_yes, on: () => {
          const planId = tell.plan_id;
          tell = {state: "idle", text: ""};
          post("/confirm", {plan_id: planId});
        }}),
        el("button", {type: "button", cls: "quiet", textContent: ui.tell_wrong, on: () => { tell = {state: "idle", text: tell.text}; render(); }})),
      tell.speech_id ? el("button", {type: "button", cls: "link hear", textContent: `🔊 ${ui.tell_hear}`, on: () => playSpeech(tell.speech_id)}) : null);
  }
  if (tell.state === "recording") {
    return el("section", {cls: "card tell"},
      el("h2", {textContent: ui.tell_listening}),
      el("button", {type: "button", cls: "mic on", textContent: `■ ${ui.tell_stop}`, on: () => recorder?.stop()}));
  }
  const box = el("textarea", {rows: 2, maxLength: 500, placeholder: ui.tell_ph, value: tell.state === "question" ? "" : tell.text, disabled: tell.state === "busy", ariaLabel: ui.tell_title});
  return el("form", {cls: "card tell", onsubmit: (event) => {
    event.preventDefault();
    const text = box.value.trim();
    if (text) askAgent(text);
  }},
    el("h2", {textContent: ui.tell_title}),
    tell.state === "question" ? el("p", {cls: "ask", textContent: tell.question}) : null,
    tell.state === "question" && tell.speech_id ? el("button", {type: "button", cls: "link hear", textContent: `🔊 ${ui.tell_hear}`, on: () => playSpeech(tell.speech_id)}) : null,
    tell.state === "unavailable" ? el("p", {cls: "error", role: "alert", textContent: ui.tell_unavailable}) : null,
    tell.state === "nomic" ? el("p", {cls: "error", role: "alert", textContent: ui.tell_mic_off}) : null,
    canRecord() ? el("button", {type: "button", cls: "mic", disabled: tell.state === "busy", textContent: `🎙 ${ui.tell_speak}`, on: startRecording}) : null,
    box,
    el("button", {type: "submit", cls: "primary", disabled: tell.state === "busy", textContent: tell.state === "busy" ? ui.tell_busy : ui.tell_send, on: () => { spokenReply = false; }}));
}

function stateLine(item) {
  const ui = view.ui;
  if (item.decision === "DECLINED") return el("div", {cls: "state off"}, ui.decline);
  if (item.decision === "UNDONE") return el("div", {cls: "state off"}, ui.undone);
  if (item.write_status === "FAILED") return el("div", {cls: "state bad"}, ui.failed);
  if (item.write_status === "WRITTEN") {
    return el("div", {cls: "state ok"}, `✓ ${item.final_label}`,
      el("button", {type: "button", textContent: ui.undo,
        on: () => post("/undo", {item: item.id})}));
  }
  return el("div", {cls: "state off"}, ui.pending_write);
}

function card(item, multiple) {
  const ui = view.ui;
  const pending = item.decision === "PENDING" || item.decision === "NO_REPLY";
  const form = open[item.id];
  return el("section", {cls: "card"},
    el("div", {cls: "day"}, item.day, el("span", {cls: "date", textContent: item.date})),
    pending ? el("div", {cls: "change"},
      el("div", {cls: "was"}, el("small", {textContent: ui.shown}), item.shown),
      el("div", {cls: "arrow", textContent: "→", ariaHidden: "true"}),
      el("div", {}, el("small", {textContent: ui.suggest}), el("div", {cls: "now", textContent: item.proposed_label}))) : null,
    pending && item.reason ? el("p", {cls: "why", textContent: item.reason}) : null,
    pending && item.mode === "ASK" ? el("p", {cls: "ask", textContent: ui.ask}) : null,
    pending && item.views ? el("p", {cls: "views", textContent: ui.views.replace("{n}", item.views)}) : null,
    !pending ? stateLine(item) : null,
    pending && form === "edit" ? editForm(item) : null,
    pending && form === "decline" ? declineForm(item) : null,
    pending && !form && item.alternative ? el("button", {type: "button", cls: "alternative",
      textContent: ui.alternative.replace("{hours}", item.alternative_label),
      on: () => decide([{item: item.id, action: "edit", hours: item.alternative}])}) : null,
    pending && !form ? el("div", {cls: "row"},
      multiple ? el("button", {type: "button", textContent: ui.approve,
        on: () => decide([{item: item.id, action: "approve"}])}) : null,
      el("button", {type: "button", textContent: ui.edit, on: () => { open[item.id] = "edit"; render(); }}),
      el("button", {type: "button", cls: "quiet", textContent: ui.decline,
        on: () => { open[item.id] = "decline"; render(); }})) : null);
}

function render() {
  if (!view) return;
  const ui = view.ui;
  document.documentElement.lang = view.language === "nb" ? "nb" : view.language;
  document.title = `${ui.title}: ${view.business}`;
  if (view.expired) {
    app.replaceChildren(el("p", {cls: "center", textContent: ui.expired}));
    addCaptions(app);
    return;
  }
  const pending = pendingItems();
  const written = view.items.some((i) => i.write_status === "WRITTEN");
  const allDeclined = !pending.length && !written && !view.items.some((i) => i.write_status === "FAILED");
  const nodes = [el("header", {cls: "head"},
    el("p", {textContent: view.business}),
    el("h1", {textContent: ui.title}),
    el("p", {textContent: ui.no_login}))];

  if (written && !pending.length) nodes.push(el("section", {cls: "card done"}, el("h2", {textContent: ui.done_title})));
  if (allDeclined) {
    nodes.push(el("section", {cls: "card done"},
      el("h2", {textContent: view.opted_out ? ui.stopped : ui.declined_title})));
  }

  nodes.push(tellCard());
  if (view.regular_updates.length) {
    nodes.push(el("section", {cls: "card done"}, el("h2", {textContent: ui.tell_regular}),
      el("ul", {cls: "regular"}, ...view.regular_updates.map((update) => el("li", {},
        el("span", {textContent: update.days}), el("strong", {textContent: update.hours}))))));
  }
  view.items.forEach((item) => nodes.push(card(item, pending.length > 1)));

  if (written && view.listings.length) {
    nodes.push(el("section", {cls: "card panel"}, el("h2", {textContent: ui.where}),
      el("ul", {}, ...view.listings.slice(0, 5).map((x) => el("li", {},
        el("span", {textContent: x.name}), el("span", {textContent: x.eta}))))));
  }
  if (written && !hideOffer && !view.standing && !view.opted_out) {
    nodes.push(el("section", {cls: "card offer"},
      el("h2", {textContent: ui.standing_q}),
      el("p", {textContent: ui.standing_d}),
      el("div", {cls: "row"},
        el("button", {type: "button", cls: "primary", textContent: ui.standing_yes,
          on: () => post("/standing", {enabled: true})}),
        el("button", {type: "button", cls: "quiet", textContent: ui.standing_no, on: () => { hideOffer = true; render(); }}))));
  }
  if (written && view.standing) {
    nodes.push(el("section", {cls: "card offer"},
      el("p", {textContent: ui.standing_on}),
      el("div", {cls: "row"}, el("button", {type: "button", cls: "quiet", textContent: ui.standing_off,
        on: () => post("/standing", {enabled: false})}))));
  }
  // While the owner checks their own words, "approve all" would mean something else, so it steps aside.
  if (pending.length && !pending.some((i) => open[i.id]) && !["confirm", "recording"].includes(tell.state)) {
    nodes.push(el("div", {cls: "sticky"}, el("div", {},
      el("button", {type: "button", cls: "primary",
        textContent: pending.length > 1 ? ui.approve_all_n.replace("{n}", pending.length) : ui.approve_all,
        on: () => decide(pending.map((i) => ({item: i.id, action: "approve"})))}))));
  }
  app.replaceChildren(...nodes.filter(Boolean));
  addCaptions(app);
}

fetch(api).then((r) => (r.ok ? r.json() : Promise.reject())).then((data) => { view = data; render(); })
  .catch(() => app.replaceChildren(el("p", {cls: "center", textContent: "This link is no longer valid."})));
