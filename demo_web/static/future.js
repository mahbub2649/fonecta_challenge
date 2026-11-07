// A concept mock of two future plans. It's scripted: no server calls, no AI, and nothing is saved.
const app = document.getElementById("app");
const SHOPS = [{"name": "Muoti Lyhty", "standing": false, "out": false}, {"name": "Apteekki Aalto", "standing": false, "out": false}, {"name": "Apteekki Koivu", "standing": false, "out": false}, {"name": "Apteekki Sisu", "standing": false, "out": false}, {"name": "Beauty Hilla", "standing": true, "out": false}, {"name": "Beauty Lyhty", "standing": false, "out": false}, {"name": "Hieronta Lumi", "standing": false, "out": false}, {"name": "Hieronta Lyhty", "standing": false, "out": false}, {"name": "Hieronta Napa", "standing": false, "out": false}, {"name": "Hierontapalvelu Aurora", "standing": false, "out": false}, {"name": "Hierontapalvelu Kallio", "standing": false, "out": false}, {"name": "Hierontapalvelu Kotikolo", "standing": true, "out": false}, {"name": "Hierontapalvelu Peltola", "standing": false, "out": false}, {"name": "Kahvila & Leipomo Kallio", "standing": false, "out": false}, {"name": "Kahvila & Leipomo Kanerva", "standing": false, "out": false}, {"name": "Kebab & Pizza Koivu", "standing": false, "out": false}, {"name": "Kebab & Pizza Onni", "standing": false, "out": false}, {"name": "Kebab & Pizza Revontuli", "standing": false, "out": false}, {"name": "Kebab & Pizza Tähti", "standing": false, "out": false}, {"name": "Kirjakauppa Otso", "standing": false, "out": false}, {"name": "Kukka-Kotikolo", "standing": false, "out": false}, {"name": "Kukkakauppa Kanerva", "standing": false, "out": false}, {"name": "Lemmikki Peltola", "standing": false, "out": false}, {"name": "Lähikauppa Koivu", "standing": false, "out": false}, {"name": "Lähikauppa Napa", "standing": false, "out": false}, {"name": "Muoti Kide", "standing": false, "out": false}, {"name": "Muoti Napa", "standing": false, "out": false}, {"name": "Optikko Joki", "standing": false, "out": false}, {"name": "Optikko Kanerva", "standing": false, "out": false}, {"name": "Optikko Rasti", "standing": false, "out": false}, {"name": "Parturi-Kampaamo Lehto", "standing": false, "out": false}, {"name": "Parturi-Kampaamo Peltola", "standing": false, "out": false}, {"name": "Parturi-Kampaamo Sisu", "standing": false, "out": false}, {"name": "Pizzeria Kanerva", "standing": false, "out": false}, {"name": "Pizzeria Koivu", "standing": false, "out": false}, {"name": "Rauta Mylly", "standing": false, "out": false}, {"name": "Rauta Otso", "standing": false, "out": false}, {"name": "Vaatehuone Joki", "standing": false, "out": false}];
let tab = "closed";
let scene = 0;

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
const go = (next) => () => { scene = next; render(); };
const step = (text, next, soft) => el("button", {type: "button", cls: `step${soft ? " soft" : ""}`, textContent: text, on: go(next)});
const change = (day, before, after) => el("div", {cls: "row"}, el("b", {textContent: day}),
  el("span", {cls: "was", textContent: before}), el("span", {cls: "was", textContent: "→", ariaHidden: "true"}), el("span", {cls: "now", textContent: after}));

function closedToday() {
  if (scene === 0) {
    return [el("section", {cls: "card"},
      el("h2", {textContent: "Friday morning. The owner is ill."}),
      el("p", {cls: "quiet", textContent: "Kahvila Aurora can't open today. The owner has no time to log in, and Google still says open."}),
      el("button", {type: "button", cls: "mic", textContent: "🎙", ariaLabel: "Speak", on: go(1)}),
      el("p", {cls: "quiet", style: "text-align:center", textContent: "Tap the mic. The owner starts the loop."}))];
  }
  if (scene === 1) {
    return [el("section", {cls: "card"},
      el("h2", {textContent: "Listening…"}),
      el("div", {cls: "wave", ariaHidden: "true"}, el("i"), el("i"), el("i"), el("i"), el("i")),
      el("p", {cls: "said"}, "“Suljettu tänään, palataan maanantaina.”", el("span", {cls: "en", textContent: "“Closed today, back on Monday.”"})),
      step("Connect understands", 2))];
  }
  if (scene === 2) {
    return [el("section", {cls: "card"},
      el("h2", {textContent: "Did I get that right?"}),
      el("p", {cls: "quiet", textContent: "Connect works out the dates. Nothing changes until the owner confirms."}),
      change("Today, Fri 6 Nov", "7:30–18", "Closed"),
      change("Sat 7 Nov", "9–18", "Closed"),
      change("Sun 8 Nov", "10–16", "Closed"),
      el("p", {cls: "quiet", style: "margin-top:8px", textContent: "Normal hours come back by themselves on Monday."}),
      step("Yes, save it", 3))];
  }
  return [el("section", {cls: "card"},
    el("h2", {cls: "ok", textContent: "✓ Done in one sentence"}),
    el("p", {textContent: "Customers won't walk to a closed door today."}),
    el("ul", {cls: "places"},
      el("li", {}, el("span", {textContent: "Google (Search & Maps)"}), el("span", {cls: "quiet", textContent: "about 2 min"})),
      el("li", {}, el("span", {textContent: "Finder.fi / Fonecta.fi"}), el("span", {cls: "quiet", textContent: "about 10 min"})),
      el("li", {}, el("span", {textContent: "Fonecta Caller"}), el("span", {cls: "quiet", textContent: "about 1 h"}))),
    step("Start again", 0, true))];
}

function centreChange() {
  const auto = SHOPS.filter((s) => s.standing && !s.out).length;
  const off = SHOPS.filter((s) => s.out).length;
  const ask = SHOPS.length - auto - off;
  const status = (shop, approved) => {
    if (shop.out) return el("span", {cls: "tag off", textContent: "Opted out"});
    if (shop.standing) return el("span", {cls: "tag done", textContent: "✓ Applied, told"});
    return approved && shop.name === "Muoti Lyhty" ? el("span", {cls: "tag done", textContent: "✓ Approved"}) : el("span", {cls: "tag", textContent: "One tap sent"});
  };
  const board = (approved) => el("ul", {cls: "shops"}, ...SHOPS.slice(0, 7).map((shop) => el("li", {}, el("span", {textContent: shop.name}), status(shop, approved))));
  if (scene === 0) {
    return [el("section", {cls: "card"},
      el("h2", {textContent: "The centre changes its hours"}),
      el("p", {cls: "quiet", textContent: "Kauppakeskus Revontuli decides to stay open longer on Christmas Eve."}),
      change("Christmas Eve, Thu 24 Dec", "10–13", "10–15"),
      el("p", {cls: "quiet", style: "margin-top:8px", textContent: "Every shop inside may now show the wrong hours."}),
      step("Connect notices", 1))];
  }
  if (scene === 1) {
    return [el("section", {cls: "card"},
      el("h2", {textContent: `One change, ${SHOPS.length} shops`}),
      el("p", {cls: "quiet", textContent: "Connect finds every shop in the centre, and respects each owner's choice."}),
      el("div", {cls: "stats"},
        el("div", {}, el("b", {textContent: auto}), el("small", {textContent: "applied, then told"})),
        el("div", {}, el("b", {textContent: ask}), el("small", {textContent: "get one tap"})),
        el("div", {}, el("b", {textContent: off}), el("small", {textContent: "opted out"}))),
      board(false),
      step("See it on one shop's phone", 2))];
  }
  if (scene === 2) {
    return [el("section", {cls: "card"},
      el("p", {cls: "quiet", textContent: "Muoti Lyhty · Message from Connect"}),
      el("h2", {textContent: "Kauppakeskus Revontuli changed its hours"}),
      change("Christmas Eve, Thu 24 Dec", "10–13", "10–15"),
      el("p", {cls: "quiet", style: "margin-top:8px", textContent: "Your shop usually follows the centre. Follow it this time too?"}),
      step("Approve", 3), step("Keep 10–13", 3, true))];
  }
  return [el("section", {cls: "card"},
    el("h2", {cls: "ok", textContent: "✓ The whole centre stays right"}),
    el("p", {textContent: "The owner taps once, and the centre's other shops are handled the same way."}),
    board(true),
    step("Start again", 0, true))];
}

function render() {
  app.replaceChildren(
    el("header", {cls: "top"}, el("div", {cls: "avatar", textContent: "C", ariaHidden: "true"}),
      el("div", {cls: "grow"}, el("h1", {textContent: "Future plans"}), el("p", {textContent: "The same loop, for other moments"}))),
    el("div", {cls: "concept", role: "note", textContent: "Concept mock with synthetic businesses. Not built yet, and nothing is saved."}),
    el("nav", {cls: "tabs"},
      el("button", {type: "button", cls: tab === "closed" ? "on" : "", textContent: "“We're closed today”", on: () => { tab = "closed"; scene = 0; render(); }}),
      el("button", {type: "button", cls: tab === "centre" ? "on" : "", textContent: "Centre changes hours", on: () => { tab = "centre"; scene = 0; render(); }})),
    el("main", {cls: "scroll"}, ...(tab === "closed" ? closedToday() : centreChange())));
}
render();
