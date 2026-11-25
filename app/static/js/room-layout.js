// Only viewport changes resize the table; game state never changes its geometry.
export function setupRoomLayout(app) {
  const viewport = app.querySelector('.table-viewport');
  if (!viewport) return;
  const table = app.querySelector('#table-surface');
  const mobile = matchMedia('(max-width: 690px)');
  function fit() {
    const portraitLayout = mobile.matches;
    const availableWidth = viewport.clientWidth - (portraitLayout ? 4 : 16);
    const availableHeight = viewport.clientHeight - (portraitLayout ? 20 : 32);
    if (availableWidth <= 0 || availableHeight <= 0) return;
    const height = portraitLayout ? Math.max(520, availableHeight) : 720;
    const scale = portraitLayout ? availableHeight / height :
      Math.min(availableWidth / 1200, availableHeight / height);
    // Short screens still use the full table width after scaling the cards and seats.
    const width = portraitLayout ? availableWidth / scale : 1200;
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
  const fullscreen = app.querySelector('#fullscreen-toggle');
  if (document.fullscreenEnabled) {
    fullscreen.hidden = false;
    document.addEventListener('fullscreenchange', () => {
      fullscreen.textContent = document.fullscreenElement ? '退出全屏' : '全屏';
    });
    fullscreen.addEventListener('click', async () => {
      try {
        if (document.fullscreenElement) await document.exitFullscreen();
        else await document.documentElement.requestFullscreen();
      } catch {
        const feedback = app.querySelector('#room-feedback');
        feedback.textContent = '浏览器未能切换全屏，请重试。';
        feedback.hidden = false;
      }
    });
  }
  function positionTools() {
    const target = mobile.matches ? mobileTools : dock;
    target.append(settlementTools, historyButton);
  }
  mobile.addEventListener('change', positionTools);
  positionTools();
  historyButton.addEventListener('click', () => history.showModal());
  app.querySelector('#history-close').addEventListener('click', () => history.close());
}
