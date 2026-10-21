// The privacy page: show the reader's language, count the page view like every other page.

import { install } from "./app/guard.js";
import { count } from "./app/stats.js";
import { LANGS, pickLanguage } from "./app/i18n.js";

install(window);

function show(lang) {
  document.documentElement.lang = lang;
  document.getElementById("ui-lang").value = lang;
  for (const a of document.querySelectorAll("article[data-lang]")) a.hidden = a.dataset.lang !== lang;
}

const select = document.getElementById("ui-lang");
select.addEventListener("change", () => {
  const lang = LANGS.includes(select.value) ? select.value : "en";
  try { localStorage.setItem("reflip.ui", lang); } catch {}
  show(lang);
});

show(pickLanguage());
count("page", "privacy");
