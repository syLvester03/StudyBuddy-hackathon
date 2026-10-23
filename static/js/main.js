document.addEventListener('DOMContentLoaded', () => {
  setupSearch();
  initTopicCheckboxes();
  initAssignmentToggles();
});

/* -------- Search bar logic -------- */

function setupSearch() {
  const searchInput = document.getElementById('global-search');
  if (!searchInput) return; // e.g. on chat page

  const performFilter = (query) => {
    const q = query.toLowerCase().trim();
    const items = document.querySelectorAll('.list-item, .card');

    items.forEach(item => {
      // allow opt‑out if ever needed
      if (item.dataset && item.dataset.noFilter === '1') {
        item.style.display = '';
        return;
      }
      const text = item.textContent.toLowerCase();
      item.style.display = !q || text.includes(q) ? '' : 'none';
    });
  };

  searchInput.addEventListener('input', e => performFilter(e.target.value));

  // Optional: Cmd/Ctrl + K focuses search
  document.addEventListener('keydown', e => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
      if (!searchInput) return;
      e.preventDefault();
      searchInput.focus();
      searchInput.select();
    }
  });
}

/* -------- Stop page refresh for toggles -------- */

/* Subject topics: nice checkboxes + AJAX toggle */
function initTopicCheckboxes() {
  const boxes = document.querySelectorAll('.topic-toggle-checkbox');
  boxes.forEach(cb => {
    cb.addEventListener('change', () => {
      const url = cb.dataset.toggleUrl;
      if (!url) return;

      const li = cb.closest('li');
      if (li) {
        if (cb.checked) li.classList.add('topic-completed');
        else li.classList.remove('topic-completed');
      }

      // Optimistic update – revert if request fails
      fetch(url, {
        method: 'POST',
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
      }).then(resp => {
        if (!resp.ok) throw new Error('Request failed');
      }).catch(err => {
        console.error(err);
        // revert
        cb.checked = !cb.checked;
        if (li) {
          if (cb.checked) li.classList.add('topic-completed');
          else li.classList.remove('topic-completed');
        }
      });
    });
  });
}

/* Assignment "Mark Done/Undone" – no full reload */
function initAssignmentToggles() {
  const forms = document.querySelectorAll('form.js-assignment-toggle-form');
  forms.forEach(form => {
    form.addEventListener('submit', e => {
      e.preventDefault();

      const url = form.action;
      const item = form.closest('.list-item');
      if (!item || !url) return;

      const currentlyDone = item.dataset.completed === '1';
      const newState = !currentlyDone;

      // Fire request, but don't wait for it to update UI
      fetch(url, {
        method: 'POST',
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
      }).catch(err => console.error(err));

      item.dataset.completed = newState ? '1' : '0';

      const titleEl = item.querySelector('.list-title');
      let doneTag = item.querySelector('.tag.tag-green');
      const btn = form.querySelector('button');

      if (newState) {
        if (!doneTag && titleEl) {
          doneTag = document.createElement('span');
          doneTag.className = 'tag tag-green';
          doneTag.textContent = 'Done';
          titleEl.appendChild(doneTag);
        }
        if (btn) btn.textContent = 'Mark Undone';
      } else {
        if (doneTag) doneTag.remove();
        if (btn) btn.textContent = 'Mark Done';
      }
    });
  });
}

/* -------- Markdown Renderer (used by chat + AI suggestions) -------- */

function renderMarkdown(text) {
  if (!text) return '';
  let out = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');

  out = out.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  out = out.replace(/\*(.+?)\*/g, '<em>$1</em>');

  return out;
}