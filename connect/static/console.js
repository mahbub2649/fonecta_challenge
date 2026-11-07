// The demo console: all five steps for one business, next to the owner's phone.
const $ = (id) => document.getElementById(id);
let businesses = [];
let currentId = null;
let current = null;
let chosenCase = null;
let lastPayload = "";
let quietResult = {};
let phoneLink = null;
let phoneTab = "message";
let shownMessages = 0;

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

async function call(path, method = "GET") {
  const options = method === "POST" ? {method, headers: {"Content-Type": "application/json"}, body: "{}"} : {};
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Request failed");
  return data;
}

const BASIS = {
  LAST_YEAR: "Owner's own entry last year (audit log)",
  SHOPPING_CENTRE: "Shopping centre's published hours",
  PEERS: "Peer benchmark: similar businesses",
  YOUR_CHOICE: "The owner's earlier choice",
  OLDER_YEAR: "Owner's entry two years ago (audit log)",
  REVIEW_TIME: "Customer review with a closing time, read by the model",
  REVIEW_CLOSED: "Customer reviews about a closed door, read by the model",
  REVIEW_WEEK: "Customer review with new weekly hours",
  PATTERN: "Model: traces of past days and similar businesses",
};
const STATUS = {DETECTED: "Detected", SENT: "Waiting for owner", DONE: "Done", NEEDS_HUMAN: "Needs a person", BLOCKED_OPT_OUT: "Opted out"};

const hoursText = (h) => (h === "closed" ? "closed" : (h || "").replaceAll(":00", "").replaceAll("-", "–"));

function evidenceText(item) {
  const e = item.evidence || {};
  if (item.basis === "LAST_YEAR") return `On ${e.last_date} the owner entered ${hoursText(e.last_hours)}.`;
  if (item.basis === "SHOPPING_CENTRE") return `${e.mall} has published ${hoursText(e.mall_hours)}.`;
  if (item.basis === "PEERS") return `${Math.round(e.peer_share * 100)}% of similar businesses that entered this day were closed (${e.peer_count} business-days).`;
  if (item.basis === "YOUR_CHOICE") return `The owner chose ${hoursText(e.your_hours)} earlier.`;
  if (item.basis === "OLDER_YEAR") return `On ${e.older_date} the owner entered ${hoursText(e.older_hours)}.`;
  if (item.basis === "REVIEW_TIME") return `A review says it closed at ${e.close_time} on this day last year.`;
  if (item.basis === "REVIEW_WEEK") return `A review gives new regular hours: ${hoursText(e.week_hours)} on this weekday.`;
  if (item.basis === "REVIEW_CLOSED") return `Reviews after ${e.last_date} describe a closed door.`;
  if (item.basis === "PATTERN") return "No direct record for this day. The model estimates it from traces of past days and similar businesses.";
  return "";
}

function step(number, name, sub, active, ...body) {
  return el("section", {cls: `step${active ? "" : " idle"}`},
    el("h3", {}, el("i", {textContent: number}), name, el("span", {textContent: sub})), ...body);
}

function renderOverview(o) {
  $("target").textContent = o.sandbox_active ? "Writes to: Yext sandbox" : "Writes to: local mock";
  const stat = (value, label) => el("div", {}, el("b", {textContent: value.toLocaleString("en-US")}), label);
  $("overview").replaceChildren(
    stat(o.businesses, "businesses checked"),
    stat(o.owners_to_contact, "owners to contact"),
    stat(o.suggestions, "date suggestions"),
    stat(o.quiet_days, "days left quiet"),
    stat(o.flagged_businesses, "sent to a person"),
    stat(o.views_at_stake, "search views at stake"),
    stat(o.standing_permission, "with standing permission"),
    stat(o.opted_out, "opted out, never messaged"));
}

function renderList() {
  $("list").replaceChildren(...businesses.map((b) => el("button", {
    cls: `biz${b.id === currentId ? " on" : ""}`, on: () => select(b.id)},
    el("b", {}, b.name, b.status ? el("span", {cls: `tag ${b.status}`, textContent: STATUS[b.status] || b.status}) : null),
    el("small", {textContent: `${b.city} · ${b.storyline}`}))));
}

function detectStep(biz, kase) {
  const quiet = quietResult[biz.id];
  if (!kase) {
    return step(1, "Detect", "What tells Connect the hours need to change?", true,
      quiet ? el("div", {cls: "callout good", textContent: quiet.summary}) : el("p", {textContent: "Connect compares what Google shows with the audit log, shopping centres, peers, reviews and user edits, for each special day to 6 Jan 2027."}),
      el("div", {cls: "actions"}, el("button", {textContent: "Run detection", on: () => detect(biz.id)})));
  }
  if (kase.kind === "FLAG") {
    const signals = kase.items[0]?.evidence?.signals || [];
    return step(1, "Detect", "Looks closed for good", true,
      el("div", {cls: "callout", textContent: "Connect doesn't suggest holiday hours here. It goes to a person, and the owner gets no message."}),
      ...signals.map((s) => el("p", {cls: "signal", textContent: `${s.source}, ${s.date}: "${s.text}"`})));
  }
  return step(1, "Detect", "What tells Connect the hours need to change?", true,
    el("table", {},
      el("thead", {}, el("tr", {}, ...["Day", "Google shows", "Evidence"].map((t) => el("th", {textContent: t})))),
      el("tbody", {}, ...kase.items.map((i) => el("tr", {},
        el("td", {}, i.day_name_local, el("div", {cls: "sub", textContent: i.date})),
        el("td", {cls: "num", textContent: hoursText(i.shown)}),
        el("td", {}, el("b", {textContent: BASIS[i.basis] || i.basis}), el("div", {textContent: evidenceText(i)}),
          ...(i.evidence.signals || []).map((s) => el("div", {cls: "signal", textContent: `${s.source}, ${s.date}: "${s.text}"`}))))))));
}

function suggestStep(kase) {
  if (!kase || kase.kind === "FLAG") return step(2, "Suggest", "Which hours, and why exactly those?", false);
  return step(2, "Suggest", "Which hours, and why exactly those?", true,
    el("table", {},
      el("thead", {}, el("tr", {}, ...["Day", "Suggestion", "How it's worded", "Confidence", "Views at stake"].map((t) => el("th", {textContent: t})))),
      el("tbody", {}, ...kase.items.map((i) => el("tr", {},
        el("td", {textContent: i.date}),
        el("td", {cls: "proposed", textContent: hoursText(i.proposed)}),
        el("td", {textContent: i.mode === "ASK" ? "Asked as a question" : "Stated"}),
        el("td", {cls: "num", textContent: `${Math.round(i.confidence * 100)}%`}),
        el("td", {cls: "num", textContent: i.expected_views})))),
    ),
    ...kase.items.flatMap((i) => i.learning_notes.map((note) => el("div", {cls: "callout brand", textContent: `Learned: ${note}`}))),
    el("p", {cls: "sub", textContent: "Confidence is the model's estimated chance that this is right, checked on businesses it never saw. Below 90%, the owner gets a question."}));
}

function contactStep(biz, kase) {
  if (!kase || kase.kind === "FLAG") return step(3, "Contact", "How does it reach the owner?", false);
  if (kase.status === "BLOCKED_OPT_OUT") {
    return step(3, "Contact", "How does it reach the owner?", true, el("div", {cls: "callout", textContent: "This owner has opted out. No message, and nothing written."}));
  }
  const firstMessage = kase.messages[0];
  const header = `${biz.channel} · ${biz.language} · contact window ${biz.window} · ${biz.preferences.standing ? "standing permission on" : "no standing permission"}`;
  if (kase.status === "DETECTED") {
    return step(3, "Contact", header, true,
      el("div", {cls: "actions"}, el("button", {textContent: `Send by ${biz.channel}`, on: () => act(`/api/case/${kase.id}/send`)})));
  }
  return step(3, "Contact", header, true,
    el("p", {cls: "sub", textContent: "The message is on the phone. It states the suggestion and the reason."}),
    firstMessage && firstMessage.language !== "en" ? el("details", {}, el("summary", {textContent: "English translation, for reviewers"}), el("pre", {cls: "msg", textContent: firstMessage.body_en})) : null);
}

function decisionText(item) {
  return {PENDING: "Waiting", NO_REPLY: "No reply. Nothing written.", APPROVED: `Approved: ${hoursText(item.final_hours)}`,
    EDITED: `Edited to ${hoursText(item.final_hours)}`, DECLINED: `Declined${item.decline_reason ? ` (${item.decline_reason.replaceAll("_", " ")})` : ""}. Nothing written.`,
    AUTO: `Standing permission: ${hoursText(item.final_hours)}`, UNDONE: "Owner undid it."}[item.decision] || item.decision;
}

function decideStep(kase) {
  if (!kase || kase.kind === "FLAG" || !["SENT", "DONE"].includes(kase.status)) return step(4, "Decide", "Approve, edit or decline, with no login", false);
  const waiting = kase.items.some((i) => i.decision === "PENDING" || i.decision === "NO_REPLY");
  const reminded = kase.messages.some((m) => m.kind === "REMINDER");
  return step(4, "Decide", "Approve, edit or decline, with no login", true,
    el("table", {}, el("tbody", {}, ...kase.items.map((i) => el("tr", {},
      el("td", {textContent: i.date}),
      el("td", {cls: i.decision === "PENDING" ? "sub" : "", textContent: decisionText(i)}),
      el("td", {cls: "sub", textContent: i.decided_by ? `by ${i.decided_by.replaceAll("_", " ")}` : ""}))))),
    waiting ? el("p", {cls: "sub", textContent: "Tap on the phone, or let the challenge's owner simulator reply. It may not reply at all."}) : null,
    waiting ? el("div", {cls: "actions"},
      el("button", {cls: "alt", textContent: "Use owner simulator", on: () => act(`/api/case/${kase.id}/simulate`)}),
      kase.items.some((i) => i.decision === "NO_REPLY") && !reminded ? el("button", {cls: "alt", textContent: "Send the one reminder", on: () => act(`/api/case/${kase.id}/remind`)}) : null) : null);
}

function applyStep(biz, kase) {
  const touched = kase?.items?.filter((i) => ["WRITTEN", "FAILED", "UNDONE"].includes(i.write_status)) || [];
  if (!touched.length) return step(5, "Apply", "Written to Yext, and the owner told where it shows", false);
  const failed = touched.some((i) => i.write_status === "FAILED");
  const words = {WRITTEN: "Saved, and read-back matches", FAILED: "Write failed. Owner told nothing changed.", UNDONE: "Undone by owner"};
  return step(5, "Apply", "Written to Yext, and the owner told where it shows", true,
    el("table", {}, el("tbody", {}, ...touched.map((i) => el("tr", {},
      el("td", {textContent: i.date}),
      el("td", {cls: "proposed", textContent: hoursText(i.final_hours)}),
      el("td", {cls: {WRITTEN: "ok", FAILED: "bad", UNDONE: "sub"}[i.write_status], textContent: words[i.write_status]}),
      el("td", {cls: "sub", textContent: i.write_error || ""}))))),
    el("p", {cls: "sub", textContent: kase.sandbox_active
      ? `Written to the team's Yext sandbox as test business ${biz.sandbox_id}, and to Connect's record (local mock).`
      : "Written to the local Yext mock. Set YEXT_API_KEY to write to the sandbox too."}),
    failed ? el("div", {cls: "actions"}, el("button", {textContent: "Retry write", on: () => act(`/api/case/${kase.id}/retry`)})) : null,
    el("p", {textContent: "Owner is told: "},
      ...biz.listings.slice(0, 4).map((l, i) => `${i ? ", " : ""}${l.name} ${etaText(l.seconds)}`)),
    el("p", {cls: "sub", textContent: "Publisher timing comes from the challenge's simulated listings, because the sandbox has no live listings."}));
}

function etaText(seconds) {
  if (seconds < 3600) return `~${Math.round(seconds / 60)} min`;
  if (seconds < 86400) return `~${Math.round(seconds / 3600)} h`;
  return `~${Math.round(seconds / 86400)} days`;
}

function nextStep(biz, kase) {
  if (!kase || kase.status !== "DONE") return null;
  const learned = biz.events.filter((e) => e.step === "LEARN");
  return el("section", {cls: "step"},
    el("h3", {}, "Next message", el("span", {textContent: "Does the next suggestion use what the owner just said?"})),
    ...learned.slice(-4).map((e) => el("div", {cls: "callout brand", textContent: e.summary})),
    el("div", {cls: "actions"}, el("button", {textContent: "Detect the next dates", on: () => detect(biz.id)})),
    quietResult[biz.id] ? el("div", {cls: "callout good", textContent: quietResult[biz.id].summary}) : null);
}

function renderDetail() {
  const biz = current;
  if (!biz) return;
  const kase = biz.cases.find((c) => c.id === chosenCase) || biz.cases[biz.cases.length - 1];
  const history = biz.has_history ? null : el("div", {cls: "callout brand", textContent: `New customer since ${biz.customer_since}: no exception history and no earlier decisions. Connect only has peers to go on, so it asks instead of stating.`});
  const sections = [
    el("div", {cls: "title"},
      el("div", {}, el("h2", {textContent: biz.name}), el("p", {textContent: `${biz.city} · ${biz.storyline}`})),
      el("div", {cls: "facts"}, biz.id, el("br"), `Customer since ${biz.customer_since}`)),
    history,
    biz.cases.length > 1 ? el("div", {cls: "chips"}, ...biz.cases.map((c, n) => el("button", {
      cls: c.id === kase.id ? "on" : "", textContent: `Message ${n + 1}`, on: () => { chosenCase = c.id; renderDetail(); renderPhone(); }}))) : null,
    detectStep(biz, kase), suggestStep(kase), contactStep(biz, kase), decideStep(kase), applyStep(biz, kase), nextStep(biz, kase),
    biz.events.length ? el("details", {}, el("summary", {textContent: `Audit trail (${biz.events.length})`}),
      el("ul", {cls: "log"}, ...biz.events.map((e) => el("li", {}, el("b", {textContent: e.step}), `${e.summary}${e.actor !== "connect" ? ` (${e.actor.replaceAll("_", " ")})` : ""}`)))) : null];
  $("detail").replaceChildren(...sections.filter(Boolean));
}

function linkedText(text, link) {
  if (!link || !text.includes(link)) return [text];
  const [before, after] = text.split(link);
  return [before, el("a", {href: link, textContent: link, on: (event) => { event.preventDefault(); showTab("page"); }}), after];
}

function renderPhone() {
  const biz = current;
  const kase = biz?.cases.find((c) => c.id === chosenCase) || biz?.cases[biz.cases.length - 1];
  const screen = $("phone-message");
  const sent = kase?.messages || [];
  if (!sent.length) {
    screen.replaceChildren(el("p", {cls: "empty", textContent: "No message. Connect stays quiet unless something needs doing."}));
  } else {
    screen.replaceChildren(...sent.flatMap((m) => [
      el("div", {cls: "bubble-meta", textContent: `${m.channel} · ${m.kind.replaceAll("_", " ").toLowerCase()}`}),
      el("div", {cls: "bubble"}, ...linkedText(m.body, kase.link))]));
    if (sent.length !== shownMessages) screen.scrollTop = screen.scrollHeight;
  }
  shownMessages = sent.length;
  const link = kase?.status !== "DETECTED" && kase?.link ? kase.link : null;
  if (link !== phoneLink) {
    phoneLink = link;
    $("phone-page").src = link || "about:blank";
  }
  if (!link && phoneTab === "page") showTab("message");
}

function showTab(tab) {
  phoneTab = tab;
  $("tab-message").classList.toggle("on", tab === "message");
  $("tab-page").classList.toggle("on", tab === "page");
  $("phone-message").hidden = tab !== "message";
  $("phone-page").hidden = tab !== "page";
}

async function refresh(force = false) {
  if (!currentId) return;
  const data = await call(`/api/business/${currentId}`);
  const payload = JSON.stringify(data);
  if (!force && payload === lastPayload) return;
  lastPayload = payload;
  current = data;
  renderDetail();
  renderPhone();
  businesses = await call("/api/businesses");
  renderList();
}

async function select(id) {
  currentId = id;
  chosenCase = null;
  lastPayload = "";
  showTab("message");
  await refresh(true);
  renderList();
}

async function act(path) {
  await call(path, "POST").catch((error) => alert(error.message));
  await refresh(true);
  if (current?.cases.length && phoneLink) showTab("message");
}

async function detect(id) {
  try {
    const result = await call(`/api/business/${id}/detect`, "POST");
    if (result.result === "QUIET") quietResult[id] = result;
    else delete quietResult[id];
    chosenCase = result.case_id ?? null;
  } catch (error) {
    alert(error.message);
  }
  await refresh(true);
}

$("tab-message").addEventListener("click", () => showTab("message"));
$("tab-page").addEventListener("click", () => { if (phoneLink) showTab("page"); });
$("reset").addEventListener("click", async () => {
  await call("/api/reset", "POST");
  quietResult = {};
  chosenCase = null;
  phoneLink = null;
  $("phone-page").src = "about:blank";
  await refresh(true);
  businesses = await call("/api/businesses");
  renderList();
});

(async function start() {
  businesses = await call("/api/businesses");
  await select(businesses[0].id);
  const overview = await call("/api/overview");
  renderOverview(overview);
  setInterval(() => refresh().catch(() => {}), 2000);
})();
