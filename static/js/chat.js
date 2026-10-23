document.addEventListener('DOMContentLoaded', function () {
  const form = document.getElementById('chat-form');
  const input = document.getElementById('chat-input');
  const windowEl = document.getElementById('chat-window');

  function appendMessage(role, text) {
    const wrapper = document.createElement('div');
    wrapper.className = 'chat-message ' + (role === 'user' ? 'user' : 'assistant');

    const label = document.createElement('div');
    label.className = 'chat-label';
    label.textContent = role === 'user' ? 'You' : 'StudyBuddyAI';

    const bubble = document.createElement('div');
    bubble.className = 'chat-bubble';
    bubble.textContent = text;

    wrapper.appendChild(label);
    wrapper.appendChild(bubble);
    windowEl.appendChild(wrapper);
    windowEl.scrollTop = windowEl.scrollHeight;
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    const message = input.value.trim();
    if (!message) return;

    appendMessage('user', message);
    input.value = '';
    input.focus();

    appendMessage('assistant', 'Thinking...');

    fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message })
    })
      .then(r => r.json())
      .then(data => {
        // remove the 'Thinking...' bubble
        const last = windowEl.querySelector('.chat-message.assistant:last-child');
        if (last) last.remove();
        if (data.error) {
          appendMessage('assistant', data.error);
        } else {
          appendMessage('assistant', data.reply);
        }
      })
      .catch(err => {
        console.error(err);
        const last = windowEl.querySelector('.chat-message.assistant:last-child');
        if (last) last.remove();
        appendMessage('assistant', 'Error contacting AI.');
      });
  });
});