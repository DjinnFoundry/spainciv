// Keyboard & mouse cheat-sheet.
import { icon } from "../ui/icon.js";
import { country } from "./country.js";
import { esc } from "../format.js";
import { t } from "../i18n.js";

const isMac = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent || "");
const MOD = isMac ? "⌘" : "Ctrl";

const rows = () => [
  [t("core.help.move"), [
    [[t("core.help.key.drag"), "←↑→↓", "WASD"], t("core.help.pan")],
    [[t("core.help.key.scroll"), "+", "–"], t("core.help.zoom")],
    [[t("core.help.key.doubleClick")], t("core.help.zoomSpot")],
    [[t("core.help.key.twoFingers")], t("core.help.pinch")],
    [[t("core.help.key.minimap")], t("core.help.jump")],
  ]],
  [t("core.help.explore"), [
    [[t("core.help.key.clickCity")], t("core.help.openCity")],
    [[t("core.help.key.clickLand")], t("core.help.openState")],
    [["/", `${MOD} K`], t("core.help.search")],
    [["L", t("core.help.key.shiftL")], t("core.help.lens")],
    [[t("core.help.key.legend")], t("core.lens.scaleHint")],
    [["R"], t("core.help.resources")],
  ]],
  [t("core.help.panels"), [
    [["?"], t("core.help.help")],
    [["Esc"], t("core.help.esc")],
  ]],
];

export function initHelp() {
  const modal = document.getElementById("help");
  if (!modal) return { open() {}, close() {}, get isOpen() { return false; } };
  const card = modal.querySelector(".help-card");
  let restore = null;
  card.innerHTML = `
    <button class="icon-btn help-close" data-close aria-label="${t("core.help.close")}">${icon("close", "✕", { size: 13 })}</button>
    <h2 id="help-title">${icon("help", "?", { size: 22 })}<span>${t("core.help.title")}</span></h2>
    <div class="help-cols">${rows().map(([title, items]) => `
      <section><h3>${title}</h3>${items.map(([keys, what]) => `
        <div class="help-row"><span class="keys">${keys.map((k) => `<kbd>${k}</kbd>`).join("")}</span><span>${what}</span></div>`).join("")}
      </section>`).join("")}</div>
    <p class="help-foot">${t("core.help.foot", { zip: `<a href="${country().product}-source.zip" download>${country().product}-source.zip</a>` })}${country().product === "usaciv" ? "" : t("core.help.basedOn", {
      product: esc(country().product), usaciv: '<a href="https://karpathy.ai/usaciv/" target="_blank" rel="noopener">usaciv</a>' })}${country().play ? t("core.help.play", {
      link: `<a href="${esc(country().play)}">${t("core.help.playLink")}</a>` }) : ""}</p>`;

  const close = () => {
    if (modal.hidden) return;
    modal.hidden = true;
    if (restore && document.contains(restore)) restore.focus();
    restore = null;
  };
  modal.addEventListener("click", (e) => {
    if (e.target === modal || e.target.closest("[data-close]")) close();
  });
  modal.addEventListener("keydown", (e) => {
    if (e.key !== "Tab") return;
    e.preventDefault(); // the only focusable control is the close button
    card.querySelector("[data-close]").focus();
  });

  return {
    open() {
      if (!modal.hidden) return;
      restore = document.activeElement;
      modal.hidden = false;
      card.querySelector("[data-close]").focus();
    },
    close,
    toggle() { modal.hidden ? this.open() : close(); },
    get isOpen() { return !modal.hidden; },
  };
}
