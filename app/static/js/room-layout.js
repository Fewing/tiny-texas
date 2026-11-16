// Only viewport changes resize the table; game state never changes its geometry.
export function setupRoomLayout(app) {
  const viewport = app.querySelector('.table-viewport');
  if (!viewport) return;
  const table = app.querySelector('#table-surface');
  const mobile = matchMedia('(max-width: 690px)');
  function fit() {
    const width = mobile.matches ? viewport.clientWidth - 16 : 1200;
    const height = mobile.matches ? Math.max(540, viewport.clientHeight - 32) : 720;
    // Keep a small gutter for card outlines and reveal animations above top seats.
    const scale = Math.min((viewport.clientWidth - 16) / width, (viewport.clientHeight - 32) / height);
    table.style.width = `${width}px`;
    table.style.height = `${height}px`;
    table.style.transform = `translate(-50%, -50%) scale(${scale})`;
  }
  new ResizeObserver(fit).observe(viewport);
  mobile.addEventListener('change', fit);
  fit();
  const history = app.querySelector('#history-modal');
  const historyButton = app.querySelector('#history-open');
  const settlementTools = app.querySelector('#settlement-tools');
  const dock = app.querySelector('.action-dock');
  const mobileTools = app.querySelector('.mobile-room-tools');
  function positionTools() {
    const target = mobile.matches ? mobileTools : dock;
    target.append(settlementTools, historyButton);
  }
  mobile.addEventListener('change', positionTools);
  positionTools();
  historyButton.addEventListener('click', () => history.showModal());
  app.querySelector('#history-close').addEventListener('click', () => history.close());
}
