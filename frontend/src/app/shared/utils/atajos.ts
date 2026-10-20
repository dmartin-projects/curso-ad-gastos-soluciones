/**
 * ¿El foco está en algo donde se escribe? Entonces "n" o "/" son letras, no atajos.
 * Incluye los campos de Material (son <input>/<textarea> por dentro) y los contenteditable.
 */
export function esCampoDeTexto(destino: EventTarget | null): boolean {
  if (!(destino instanceof HTMLElement)) return false;
  // isContentEditable no existe en jsdom (los tests unitarios): el atributo, por si acaso
  if (
    destino.isContentEditable ||
    destino.closest('[contenteditable=""], [contenteditable="true"]')
  )
    return true;
  if (destino instanceof HTMLTextAreaElement || destino instanceof HTMLSelectElement) return true;
  if (destino instanceof HTMLInputElement) {
    // casillas, radios y botones no reciben texto: ahí los atajos sí valen
    return !['checkbox', 'radio', 'button', 'submit', 'reset', 'range', 'color', 'file'].includes(
      destino.type,
    );
  }
  return destino.getAttribute('role') === 'combobox' || destino.getAttribute('role') === 'textbox';
}
