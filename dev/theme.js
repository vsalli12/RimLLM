(() => {
  const key = 'rimchronicle-theme';
  let saved;
  try { saved = localStorage.getItem(key); } catch (_) {}
  let dark = saved === 'dark' || (!saved && matchMedia('(prefers-color-scheme: dark)').matches);
  function apply() {
    document.documentElement.dataset.theme = dark ? 'dark' : 'light';
    const button = document.getElementById('theme-toggle');
    if (button) {
      button.textContent = dark ? 'Day mode' : 'Night mode';
      button.setAttribute('aria-pressed', String(dark));
      button.setAttribute('aria-label', dark ? 'Switch to day mode' : 'Switch to night mode');
    }
  }
  apply();
  document.addEventListener('DOMContentLoaded', () => {
    apply();
    document.getElementById('theme-toggle')?.addEventListener('click', () => {
      dark = !dark;
      try { localStorage.setItem(key, dark ? 'dark' : 'light'); } catch (_) {}
      apply();
    });
  });
  addEventListener('storage', event => {
    if (event.key === key) { dark = event.newValue === 'dark'; apply(); }
  });
})();
