// Simple, safe markdown renderer for **bold**, *italic*, and newlines.
function renderMarkdown(text) {
  if (!text) return '';

  // 1) Escape HTML so user/model can't inject tags
  let out = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');

  // 2) Bold: **text**
  out = out.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

  // 3) Italic: *text*
  // (run after bold; by then **...** are gone, so this doesn't clash)
  out = out.replace(/\*(.+?)\*/g, '<em>$1</em>');

  // 4) Keep newlines; CSS `white-space: pre-wrap` will render them as line breaks
  return out;
}