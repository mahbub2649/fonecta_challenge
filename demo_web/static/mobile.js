// The owner's view on a phone: pick a business, and Connect's messages arrive in one chat.
const app = document.getElementById("app");
const OPEN = {fi: "Avaa ja päätä", sv: "Öppna och bestäm", nb: "Åpne og bestem", en: "Open and decide"};
const CHECK = "Check my hours";
const NEXT = "Check the next dates";
let captions = true;
try { captions = localStorage.getItem("connect-captions") !== "off"; } catch { /* Stored settings can be blocked. */ }
let current = null;
let notes = [];
let typing = false;
let sheet = null;
let shown = "";

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

async function call(path, body) {
  const options = body === undefined ? {} : {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)};
  const response = await fetch(path, options);
  if (response.status === 404 && path.startsWith("/api/") && !path.startsWith("/api/business/")) location.reload();
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "That didn't work");
  return data;
}

const initials = (name) => name.split(/\s+/).slice(0, 2).map((w) => w[0]).join("").toUpperCase();

async function showList() {
  current = null;
  notes = [];
  shown = "";
  const list = await call("/api/businesses");
  app.replaceChildren(
    el("header", {cls: "top"}, el("div", {cls: "avatar", textContent: "C", ariaHidden: "true"}),
      el("div", {cls: "grow"}, el("h1", {textContent: "Connect"}), el("p", {textContent: "You're a business owner today"}))),
    el("main", {cls: "scroll"},
      el("p", {cls: "intro", textContent: "Pick a business. These are synthetic demo businesses, so nothing here is real."}),
      ...list.map((b) => el("button", {type: "button", cls: "biz", on: () => openBusiness(b.id)},
        el("div", {cls: "avatar", textContent: initials(b.name), ariaHidden: "true"}),
        el("div", {cls: "grow"}, el("b", {textContent: b.name}), el("small", {textContent: b.city})),
        b.status ? el("span", {cls: `badge${b.status === "DONE" ? " done" : ""}`, textContent: b.status === "DONE" ? "Updated" : "Waiting"}) : null)),
      el("div", {cls: "tools"},
        el("label", {}, el("input", {type: "checkbox", checked: captions, onchange: (e) => {
          captions = e.target.checked;
          try { localStorage.setItem("connect-captions", captions ? "on" : "off"); } catch { /* It still works for this visit. */ }
        }}), "English captions"),
        el("a", {cls: "link", href: "/future", textContent: "Future plans"}),
        el("button", {type: "button", cls: "link", textContent: "Reset demo", on: async () => {
          if (confirm("Reset the demo for everyone using it?")) { await call("/api/reset", {}); showList(); }
        }}))));
}

async function openBusiness(id) {
  current = await call(`/api/business/${id}`);
  renderChat();
  if (!current.cases.length) checkHours();
}

function messageNodes() {
  const nodes = [];
  for (const kase of current.cases) {
    for (const m of kase.messages) {
      const parts = kase.link && m.body.includes(kase.link) ? m.body.split(kase.link) : [m.body];
      const english = (m.body_en || "").split(kase.link || "\0").join("").trim();
      nodes.push(el("div", {cls: "meta", textContent: m.channel}),
        el("div", {cls: "bubble"}, parts.join("").trim(),
          captions && m.language !== "en" && english ? el("div", {cls: "english", textContent: english}) : null,
          parts.length > 1 && !["DONE", "EXPIRED"].includes(kase.status) || (parts.length > 1 && m.kind !== "OFFER")
            ? el("button", {type: "button", cls: "open", textContent: OPEN[m.language] || OPEN.en, on: () => openOwner(kase.link)}) : null));
    }
  }
  for (const note of notes) nodes.push(el("div", {cls: `note${note.human ? " human" : ""}`, textContent: note.text}));
  if (typing) nodes.push(el("div", {}, el("div", {cls: "typing", ariaLabel: "Connect is writing"}, el("i"), el("i"), el("i"))));
  if (!nodes.length) nodes.push(el("p", {cls: "empty", textContent: "No messages yet."}));
  return nodes;
}

function renderChat() {
  const scroll = el("main", {cls: "scroll"}, ...messageNodes());
  const started = current.cases.length > 0;
  app.replaceChildren(
    el("header", {cls: "top"},
      el("button", {type: "button", cls: "icon", textContent: "←", ariaLabel: "All businesses", on: showList}),
      el("div", {cls: "avatar", textContent: initials(current.name), ariaHidden: "true"}),
      el("div", {cls: "grow"}, el("h1", {textContent: current.name}), el("p", {textContent: `Messages from Connect · ${current.city}`}))),
    scroll,
    el("footer", {cls: "bar"}, el("button", {type: "button", cls: "main", disabled: typing, textContent: started ? NEXT : CHECK, on: checkHours})));
  const signature = JSON.stringify([current.cases.map((c) => c.messages.length), notes.length, typing]);
  if (signature !== shown) scroll.scrollTop = scroll.scrollHeight;
  shown = signature;
}

async function checkHours() {
  typing = true;
  renderChat();
  const id = current.id;
  try {
    const result = await call(`/api/business/${id}/detect`, {});
    await new Promise((resolve) => { setTimeout(resolve, 700); });
    if (result.result === "CASE") await call(`/api/case/${result.case_id}/send`, {});
    else if (result.result === "OPEN_CASE") notes.push({text: "You still have a message waiting for an answer."});
    else if (result.result === "FLAG") notes.push({text: "This business looks closed for good, so Connect passed it to a person. No message to the owner.", human: true});
    else notes.push({text: "Nothing to change. Connect stays quiet unless something needs doing."});
    current = await call(`/api/business/${id}`);
  } catch (error) {
    notes.push({text: error.message, human: true});
  }
  typing = false;
  if (current?.id === id && !sheet) renderChat();
}

function openOwner(link) {
  const path = new URL(link).pathname + (captions ? "?captions=1" : "");
  sheet = el("div", {cls: "sheet"}, el("div", {},
    el("header", {cls: "top"},
      el("button", {type: "button", cls: "icon", textContent: "←", ariaLabel: "Back to messages", on: closeOwner}),
      el("div", {cls: "grow"}, el("h1", {textContent: current.name}), el("p", {textContent: "No login. You always decide."}))),
    el("iframe", {src: path, title: "Approval page", allow: "microphone"})));
  document.body.append(sheet);
}

async function closeOwner() {
  sheet?.remove();
  sheet = null;
  current = await call(`/api/business/${current.id}`);
  renderChat();
}

showList().catch(() => app.replaceChildren(el("p", {cls: "empty", textContent: "Couldn't load the demo. Refresh to try again."})));
setInterval(async () => {
  if (!current || sheet || typing) return;
  try {
    const fresh = await call(`/api/business/${current.id}`);
    if (JSON.stringify(fresh.cases) !== JSON.stringify(current.cases)) { current = fresh; renderChat(); }
  } catch { /* The next poll tries again. */ }
}, 4000);
