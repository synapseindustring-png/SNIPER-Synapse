(() => {
  const form = document.getElementById('opportunity-form');
  if (!form) return;
  const state = form.querySelector('[name="state"]');
  const submit = form.querySelector('button[type="submit"]');
  const status = document.getElementById('options-status');
  let revision = 0;
  let controller;
  let loadedState = state.value;
  let loadedTarget = form.querySelector('[name="target"]:checked').value;

  function renderOptions(containerId, name, items, preserve) {
    const container = document.getElementById(containerId);
    const selected = new Set(preserve
      ? Array.from(container.querySelectorAll('input:checked'), input => input.value)
      : []);
    const nodes = items.map(item => {
      const label = document.createElement('label');
      const input = document.createElement('input');
      input.type = name === 'initiative' ? 'radio' : 'checkbox';
      input.name = name;
      input.value = item.value;
      input.checked = selected.has(item.value);
      if (name === 'initiative') {
        label.className = 'choice-card';
        input.required = true;
      }
      const caption = document.createElement('span');
      caption.textContent = item.label;
      label.append(input, caption);
      return label;
    });
    container.replaceChildren(...nodes);
  }

  async function refresh() {
    const current = ++revision;
    controller?.abort();
    controller = new AbortController();
    const requestedState = state.value;
    const requestedTarget = form.querySelector('[name="target"]:checked').value;
    submit.disabled = true;
    form.setAttribute('aria-busy', 'true');
    status.textContent = 'Atualizando opções…';
    try {
      const params = new URLSearchParams({state: requestedState, target: requestedTarget});
      const response = await fetch(`${form.dataset.optionsUrl}?${params}`, {signal: controller.signal});
      if (!response.ok) throw new Error('Options unavailable');
      const data = await response.json();
      if (current !== revision) return;
      renderOptions('regions-options', 'regions', data.regions, loadedState === requestedState);
      renderOptions('segments-options', 'segments', data.segments, loadedTarget === requestedTarget);
      renderOptions('initiatives-options', 'initiative', data.initiatives, loadedTarget === requestedTarget);
      loadedState = requestedState;
      loadedTarget = requestedTarget;
      status.textContent = '';
      submit.disabled = false;
    } catch (error) {
      if (current !== revision) return;
      status.textContent = 'Não foi possível atualizar as opções. ';
      const retry = document.createElement('button');
      retry.type = 'button';
      retry.className = 'button secondary';
      retry.textContent = 'Tentar novamente';
      retry.addEventListener('click', refresh);
      status.append(retry);
    } finally {
      if (current === revision) form.removeAttribute('aria-busy');
    }
  }
  state.addEventListener('change', refresh);
  form.querySelectorAll('[name="target"]').forEach(input => input.addEventListener('change', refresh));
  form.addEventListener('submit', event => {
    if (submit.disabled) event.preventDefault();
  });
})();
