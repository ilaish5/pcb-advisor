/* Applies the saved theme before the first paint (loaded in <head>); 'system' means no attribute. */
(function () {
  try {
    var v = localStorage.getItem('pcb_advisor_theme');
    if (v === 'light' || v === 'dark') document.documentElement.dataset.theme = v;
  } catch (e) {
    /* storage blocked: follow the system */
  }
})();
