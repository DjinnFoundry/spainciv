// The language switch of a country published in several languages (page settings `langs`, app/country.js): a small
// button at the end of the top bar per other language, and the language in the shareable URL (#lang=en), so a link
// opens in the sender's language. Picking one reloads the page in it. A country in one language (the US) gets none.
import { country, switchLang } from "../../app/country.js";

// Each button is written in the language it switches to, so a reader of that language finds it.
const OFFER = { en: "Read in English", es: "Ver en español" };

export function install(app) {
  const c = country();
  const others = Object.keys(c.langs || {}).filter((l) => l !== c.lang);
  if (!others.length) return;
  app.hash.register("lang", { get: () => country().lang, set: (v) => v && switchLang(v) });
  app.hash.soon?.();
  const host = document.querySelector("#topbar .tb-buttons");
  for (const lang of others) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "btn btn-icon btn-lang";
    b.lang = lang;
    b.textContent = lang.toUpperCase();
    b.title = OFFER[lang] ?? lang;
    b.setAttribute("aria-label", b.title);
    b.addEventListener("click", () => switchLang(lang));
    host?.appendChild(b);
  }
}
