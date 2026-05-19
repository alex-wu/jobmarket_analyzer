import {html} from "npm:htl";

// Wraps any chart cell in a card with an expand button that opens a
// <dialog> modal containing a larger re-render. Web-standard, accessible
// (Esc closes, autofocus on close button), no external deps.
//
//   title:       string heading shown on the card and modal
//   inlineNode:  DOM element rendered in the card (caller wraps with resize())
//   modalRender: (width, height) => DOM element for the modal body
export function expandable(title, inlineNode, modalRender) {
  const dialogBody = html`<div></div>`;
  const dialog = html`<dialog style="width:90vw;max-width:1400px;border:1px solid var(--theme-foreground-faintest, #ccc);border-radius:8px;padding:1rem;background:var(--theme-background, #fff);color:var(--theme-foreground, #000)">
    <form method="dialog" style="margin:0 0 0.5rem;text-align:right">
      <button autofocus title="Close" aria-label="Close" style="border:none;background:transparent;font-size:1.25rem;cursor:pointer">✕</button>
    </form>
    <h2 style="margin:0 0 0.75rem">${title}</h2>
    ${dialogBody}
  </dialog>`;

  const btn = html`<button title="Expand" aria-label="Expand ${title}" style="border:none;background:transparent;font-size:1.1rem;cursor:pointer;padding:0 0.25rem">⧉</button>`;
  btn.onclick = () => {
    const w = Math.min(1300, Math.floor(window.innerWidth * 0.85));
    const h = Math.floor(window.innerHeight * 0.65);
    dialogBody.replaceChildren(modalRender(w, h));
    dialog.showModal();
  };

  return html`<div class="card">
    <div style="display:flex;justify-content:space-between;align-items:baseline;gap:0.5rem">
      <h2 style="margin:0">${title}</h2>
      ${btn}
    </div>
    ${inlineNode}
    ${dialog}
  </div>`;
}
