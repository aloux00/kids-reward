/* ============================================================
   教材：孩子端书架 + 自建 PDF 阅读器；家长端教材库 + 布置阅读作业

   为什么自己写阅读器而不是 <iframe src="x.pdf">：
   iframe 用的是浏览器自带 PDF 插件，我们拿不到"当前第几页"，
   而"上次读到第 12 页"恰恰是这个功能对孩子最有用的地方。
   所以用本地自托管（不是 CDN）的 pdf.js 渲染到 canvas，页码完全自己掌握。
   ============================================================ */

const SUBJ_ICON = {
  chinese: '📕', math: '🔢', english: '🔤', science: '🔬', morality: '🤝',
  music: '🎵', art: '🎨', pe: '⚽', calligraphy: '✍️', other: '📘',
};

const SUBJ_NAME = {
  chinese: '语文', math: '数学', english: '英语', science: '科学', morality: '道德与法治',
  music: '音乐', art: '美术', pe: '体育与健康', calligraphy: '书法', other: '其它',
};

function _st(state) {
  return (state === 'ready') ? '' : state;
}

/* ============================================================
   孩子端
   ============================================================ */
const BookViews = (() => {

  function cover(b, big) {
    const ico = SUBJ_ICON[b.subject] || '📘';
    const cls = `bk-cover c-${b.subject || 'other'}${big ? ' big' : ''}`;
    if (b.cover) {
      return `<div class="${cls}"><img src="${UI.esc(b.cover)}" alt=""></div>`;
    }
    return `<div class="${cls}">
      <span class="bk-ico">${ico}</span>
      ${b.grade ? `<span class="bk-grade">${UI.esc(b.grade)}${UI.esc(b.term || '')}</span>` : ''}
    </div>`;
  }

  function pct(b) {
    if (!b.page_count) return 0;
    return Math.min(100, Math.round((b.last_page / b.page_count) * 100));
  }

  function bookCard(b) {
    const p = pct(b);
    return `<button class="bk-card" data-act="bk-open" data-id="${b.id}">
      ${cover(b)}
      <div class="bk-meta">
        <div class="bk-title">${UI.esc(b.title)}</div>
        <div class="bk-sub">${UI.esc(b.version || b.subject_name)}${b.page_count ? ` · 共 ${b.page_count} 页` : ''}</div>
        ${p ? `<div class="bk-bar"><i style="width:${p}%"></i></div>
               <div class="bk-page">读到第 ${b.last_page} 页</div>`
            : `<div class="bk-page muted">还没开始读</div>`}
      </div>
    </button>`;
  }

  function assignCard(r) {
    return `<div class="rd-card">
      <div class="rd-h">
        <span class="rd-ico">📖</span>
        <div>
          <div class="rd-t">读《${UI.esc(r.title)}》</div>
          <div class="rd-s">第 ${r.page_from}–${r.page_to} 页 · 共 ${r.pages} 页 · ${r.points} ⭐</div>
        </div>
      </div>
      ${r.note ? `<p class="rd-note">${UI.esc(r.note)}</p>` : ''}
      <div class="rd-acts">
        ${r.readable ? `<button class="btn ghost sm" data-act="bk-open" data-id="${r.textbook_id}" data-page="${r.page_from}">打开教材</button>` : ''}
        <button class="btn primary sm" data-act="rd-done" data-id="${r.id}">我读完啦</button>
      </div>
    </div>`;
  }

  function shelf(d, readings) {
    if (!d) return '<div class="empty">正在打开书柜…</div>';
    const books = d.books || [];
    const rs = (readings && readings.items) || [];

    if (!books.length) {
      return `<div class="page">
        <h2 class="page-h">📚 我的教材</h2>
        <div class="empty" style="padding-top:40px">
          书架还是空的<br>
          <span class="muted small">请爸爸妈妈在「管理 → 📚 教材库」里添加课本</span>
        </div>
      </div>`;
    }

    const groups = d.groups || [];
    return `<div class="page">
      <h2 class="page-h">📚 我的教材</h2>

      ${rs.length ? `<div class="sec-t">今天要读的书</div>${rs.map(assignCard).join('')}` : ''}

      ${groups.map(g => `
        <div class="sec-t">${SUBJ_ICON[(g.books[0] || {}).subject] || '📘'} ${UI.esc(g.subject)}</div>
        <div class="shelf">${g.books.map(bookCard).join('')}</div>
      `).join('')}
    </div>`;
  }

  /* ---------------------------------------------------------
     阅读器
     --------------------------------------------------------- */
  const R = {
    lib: null, doc: null, id: 0, page: 1, pages: 0, zoom: 1,
    t0: 0, saveTimer: 0, renderToken: 0, busy: false, api: 1,
  };

  async function lib() {
    if (!R.lib) {
      // pdf.js 是 ESM，普通 <script> 里只能用动态 import
      R.lib = await import('/static/vendor/pdfjs/pdf.min.mjs');
      R.lib.GlobalWorkerOptions.workerSrc = '/static/vendor/pdfjs/pdf.worker.min.mjs';
    }
    return R.lib;
  }

  function readerShell(title, sub) {
    const host = document.getElementById('modalRoot');
    host.innerHTML = `<div class="read-mask">
      <div class="read-top">
        <button class="rd-close" data-act="rd-close">✕</button>
        <div class="rd-tt">
          <div class="rd-tt1">${UI.esc(title)}</div>
          <div class="rd-tt2">${UI.esc(sub || '')}</div>
        </div>
      </div>
      <div class="read-stage" id="rdStage">
        <canvas id="rdCanvas"></canvas>
        <div class="rd-loading" id="rdLoading">正在打开…</div>
      </div>
      <div class="read-bar">
        <button class="rd-nav" data-act="rd-prev">‹</button>
        <div class="rd-pager">
          <input id="rdPage" type="number" min="1" value="1" inputmode="numeric">
          <span>/ <b id="rdTotal">-</b></span>
        </div>
        <button class="rd-nav" data-act="rd-next">›</button>
        <button class="rd-zoom" data-act="rd-zoomout">－</button>
        <button class="rd-zoom" data-act="rd-zoomin">＋</button>
      </div>
    </div>`;
    return host.querySelector('.read-mask');
  }

  async function open(book, startPage) {
    if (R.doc) closeReader(false);

    const shell = readerShell(book.title,
      [book.version, book.grade && (book.grade + (book.term || '')), book.subject_name]
        .filter(Boolean).join(' · '));

    const loading = shell.querySelector('#rdLoading');
    try {
      const p = await lib();
      R.doc = await p.getDocument({
        url: book.file_url,
        // 这个接口要鉴权，pdf.js 自己发的请求带不上 API 里的默认头
        httpHeaders: { Authorization: 'Bearer ' + API.getToken() },
        withCredentials: false,
        // 中文课本大量使用 CID 字体，不给 cMap 的话字会渲染成空白 ——
        // 这不是"锦上添花的优化"，是能不能看见字的问题。
        cMapUrl: '/static/vendor/pdfjs/cmaps/',
        cMapPacked: true,
        standardFontDataUrl: '/static/vendor/pdfjs/standard_fonts/',
      }).promise;
    } catch (e) {
      loading.innerHTML = '这本教材打不开 😢<br><span class="small">可能是文件没下载完整，让爸爸妈妈在教材库里点一下「重试」</span>';
      return;
    }

    R.id = book.id;
    R.pages = R.doc.numPages;
    R.page = Math.min(Math.max(1, +startPage || book.last_page || 1), R.pages);
    R.zoom = 1;
    R.t0 = Date.now();
    loading.style.display = 'none';

    shell.querySelector('#rdTotal').textContent = R.pages;
    shell.querySelector('#rdPage').value = R.page;
    await render();

    // 第一次打开顺手把总页数回写给后端，以后家长布置作业就知道这本书有多少页
    if (!book.page_count) {
      API.put(`/api/child/textbook/${R.id}/progress`, {
        last_page: R.page, page_count: R.pages, seconds: 0,
      }).catch(() => { });
    }

    bindReaderGestures(shell);
    shell.querySelector('#rdPage').addEventListener('change', (e) => {
      goto(+e.target.value);
    });
  }

  async function render() {
    if (!R.doc) return;
    const token = ++R.renderToken;
    const canvas = document.getElementById('rdCanvas');
    const stage = document.getElementById('rdStage');
    if (!canvas || !stage) return;

    const page = await R.doc.getPage(R.page);
    if (token !== R.renderToken) return;

    const base = page.getViewport({ scale: 1 });
    const availW = Math.max(200, stage.clientWidth - 20);
    const scale = (availW / base.width) * R.zoom;
    const vp = page.getViewport({ scale });

    // 手机屏 DPR 高，按 DPR 放大画布才能看清字
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.floor(vp.width * dpr);
    canvas.height = Math.floor(vp.height * dpr);
    canvas.style.width = Math.floor(vp.width) + 'px';
    canvas.style.height = Math.floor(vp.height) + 'px';

    const ctx = canvas.getContext('2d');
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    R.busy = true;
    try {
      await page.render({
        canvasContext: ctx,
        viewport: vp,
        transform: dpr !== 1 ? [dpr, 0, 0, dpr, 0, 0] : null,
      }).promise;
    } catch (e) {
      /* 快速翻页时 pdf.js 会抛 RenderingCancelledException，忽略即可 */
    }
    R.busy = false;

    const inp = document.getElementById('rdPage');
    if (inp) inp.value = R.page;
    scheduleSave();
  }

  function scheduleSave() {
    clearTimeout(R.saveTimer);
    R.saveTimer = setTimeout(save, 1200);
  }

  function save(extraSeconds) {
    if (!R.id) return;
    const seconds = extraSeconds || 0;
    API.put(`/api/child/textbook/${R.id}/progress`, {
      last_page: R.page, page_count: R.pages, seconds,
    }).catch(() => { });
  }

  function goto(n) {
    if (!R.doc) return;
    const p = Math.min(Math.max(1, Math.round(n) || 1), R.pages);
    if (p === R.page) return;
    R.page = p;
    render();
  }

  function closeReader(reload) {
    clearTimeout(R.saveTimer);
    if (R.id) {
      const secs = R.t0 ? Math.round((Date.now() - R.t0) / 1000) : 0;
      save(secs);
    }
    if (R.onKey) { document.removeEventListener('keydown', R.onKey); R.onKey = null; }
    if (R.doc) { try { R.doc.destroy(); } catch (e) { } }
    R.doc = null; R.id = 0; R.t0 = 0;
    UI.close();
    if (reload !== false) App.load();
  }

  function bindReaderGestures(shell) {
    const stage = shell.querySelector('#rdStage');
    let x0 = 0, y0 = 0, moved = false;
    stage.addEventListener('touchstart', (e) => {
      if (e.touches.length !== 1) return;
      x0 = e.touches[0].clientX; y0 = e.touches[0].clientY; moved = false;
    }, { passive: true });
    stage.addEventListener('touchmove', () => { moved = true; }, { passive: true });
    stage.addEventListener('touchend', (e) => {
      if (!moved || !e.changedTouches.length) return;
      const dx = e.changedTouches[0].clientX - x0;
      const dy = e.changedTouches[0].clientY - y0;
      if (Math.abs(dx) < 50 || Math.abs(dx) < Math.abs(dy)) return;
      if (dx > 0) R.page > 1 && goto(R.page - 1);
      else goto(R.page + 1);
    }, { passive: true });

    const onKey = (e) => {
      if (!R.doc) return;
      if (e.key === 'ArrowLeft') goto(R.page - 1);
      if (e.key === 'ArrowRight') goto(R.page + 1);
      if (e.key === 'Escape') closeReader();
    };
    document.addEventListener('keydown', onKey);
    R.onKey = onKey;
  }

  /* ---------------------------------------------------------
     动作表
     --------------------------------------------------------- */
  const actions = {
    async 'bk-open'(el) {
      const id = +el.dataset.id;
      const d = App.state.child.books || {};
      const book = (d.books || []).find(b => b.id === id);
      if (!book) { UI.toast('这本书不在书架上', 'err'); return; }
      if (!book.readable) { UI.toast('这本书还没准备好哦', 'err'); return; }
      await open(book, +el.dataset.page || 0);
    },

    'rd-close'() { closeReader(); },
    'rd-prev'() { goto(R.page - 1); },
    'rd-next'() { goto(R.page + 1); },
    'rd-zoomin'() { R.zoom = Math.min(3, R.zoom + 0.2); render(); },
    'rd-zoomout'() { R.zoom = Math.max(0.6, R.zoom - 0.2); render(); },

    async 'rd-done'(el) {
      const id = +el.dataset.id;
      const w = UI.sheet({
        title: '读完了吗？',
        body: `<label class="f"><span>想说点什么（可以不填）</span>
                 <input id="rdNote" placeholder="比如：这篇课文讲的是小蝌蚪找妈妈"></label>`,
        okText: '交作业',
        async onOk(wrap) {
          const evidence_text = wrap.querySelector('#rdNote').value.trim();
          try {
            await API.post(`/api/child/reading/${id}/done`, { evidence_text });
            UI.close();
            UI.toast('交给爸爸妈妈啦，等他们确认 ⭐');
            App.load();
          } catch (e) { UI.toast(e.message, 'err'); return false; }
        },
      });
      return w;
    },
  };

  return { shelf, open, closeReader, actions, R };
})();


/* ============================================================
   家长端：教材库 + 布置阅读作业
   ============================================================ */
const BookAdmin = (() => {

  let pollTimer = 0;

  function coverSmall(b) {
    const ico = SUBJ_ICON[b.subject] || '📘';
    return `<div class="bk-cover sm c-${b.subject || 'other'}"><span class="bk-ico">${ico}</span></div>`;
  }

  function statusChip(b) {
    if (b.status === 'download') return `<span class="chip on">下载中…</span>`;
    if (b.status === 'failed') return `<span class="chip r" title="${UI.esc(b.error || '')}">下载失败</span>`;
    if (b.status === 'link') return `<span class="chip">外部链接</span>`;
    return `<span class="chip ok">${b.size_mb} MB</span>`;
  }

  function row(b) {
    return `<div class="tb-row">
      ${coverSmall(b)}
      <div class="tb-main">
        <div class="tb-t">${UI.esc(b.title)}${b.is_current ? ' <span class="chip ok">在用</span>' : ''}</div>
        <div class="tb-s">${UI.esc(b.subject_name)}${b.version ? ' · ' + UI.esc(b.version) : ''}${b.grade ? ' · ' + UI.esc(b.grade + (b.term || '')) : ''}</div>
        <div class="tb-s">${statusChip(b)}${b.page_count ? ` <span class="muted small">${b.page_count} 页</span>` : ''}
          ${b.error ? `<span class="muted small">${UI.esc(b.error)}</span>` : ''}</div>
      </div>
      <div class="tb-acts">
        ${b.status === 'failed' ? `<button class="btn ghost xs" data-act="tb-retry" data-id="${b.id}">重试</button>` : ''}
        ${b.status === 'ready' ? `<button class="btn ghost xs" data-act="tb-current" data-id="${b.id}">${b.is_current ? '取消在用' : '设为在用'}</button>` : ''}
        <button class="btn ghost xs" data-act="tb-edit" data-id="${b.id}">编辑</button>
        <button class="btn ghost xs r" data-act="tb-del" data-id="${b.id}">删除</button>
      </div>
    </div>`;
  }

  function library(d, kids) {
    if (!d) return '<div class="empty">正在清点教材…</div>';
    const books = d.books || [];
    const readyCount = books.filter(b => b.ready).length;

    return `<div class="page">
      <h2 class="page-h">📚 教材库</h2>
      <p class="muted small">教材下载到本地后，孩子翻开是瞬开，断网也能看书。</p>

      <div class="card">
        <div class="btn-row">
          <button class="btn primary" data-act="tb-upload">📤 上传 PDF</button>
          <button class="btn ghost" data-act="tb-url">🔗 远程地址</button>
          <button class="btn ghost" data-act="tb-catalog">📥 内置教材库</button>
        </div>
        <p class="small muted" style="margin:10px 0 0">
          已上架 <b>${readyCount}</b> 本可读教材${books.length !== readyCount ? `（另有 ${books.length - readyCount} 本待处理）` : ''}。
          内置教材库来自开源项目 ChinaTextbook，挑中的书会下载到本机，之后不再联网。
        </p>
      </div>

      ${books.length ? `<div class="sec-t">书架</div><div class="tb-list">${books.map(row).join('')}</div>`
        : `<div class="empty" style="padding:36px 0">还没有教材，点上面的按钮加一本吧</div>`}

      <div class="sec-t">布置阅读作业</div>
      <div class="card">
        ${(kids || []).length ? `
          <label class="f"><span>读哪本书</span>
            <select id="raBook">
              <option value="">请选择教材</option>
              ${books.filter(b => b.ready).map(b => `<option value="${b.id}">${UI.esc(b.title)}${b.grade ? ' · ' + UI.esc(b.grade + (b.term || '')) : ''}</option>`).join('')}
            </select>
          </label>
          <label class="f"><span>读给谁</span>
            <select id="raKid">
              ${(kids || []).map(k => `<option value="${k.id}">${UI.esc(k.name)}</option>`).join('')}
            </select>
          </label>
          <div class="grid2">
            <label class="f"><span>从第几页</span><input id="raFrom" type="number" min="1" value="1" inputmode="numeric"></label>
            <label class="f"><span>到第几页</span><input id="raTo" type="number" min="1" value="4" inputmode="numeric"></label>
          </div>
          <div class="grid2">
            <label class="f"><span>奖励星星</span><input id="raPts" type="number" min="0" max="50" value="5" inputmode="numeric"></label>
            <label class="f"><span>最晚哪天</span><input id="raDue" type="date"></label>
          </div>
          <label class="f"><span>一句话交代（可不填）</span><input id="raNote" placeholder="读完讲讲小蝌蚪是怎么变成青蛙的"></label>
          <button class="btn primary block" data-act="ra-create">布置下去</button>
        ` : `<p class="muted small">还没有孩子账号，先在「家庭成员」里添加一个。</p>`}
      </div>

      <div class="sec-t">最近布置的阅读</div>
      <div id="raList">${readingsHtml(App.state.parent.readings)}</div>
    </div>`;
  }

  function readingsHtml(d) {
    const items = (d && d.items) || [];
    if (!items.length) return '<div class="empty" style="padding:24px 0">还没布置过阅读作业</div>';
    return items.map(r => `
      <div class="ra-item s-${r.status}">
        <div class="ra-l">
          <div class="ra-t">${UI.esc(r.title)}</div>
          <div class="ra-s">第 ${r.page_from}–${r.page_to} 页 · ${r.points} ⭐ · ${stName(r.status)}</div>
          ${r.evidence_text ? `<div class="ra-note">孩子说：${UI.esc(r.evidence_text)}</div>` : ''}
          ${r.reject_reason ? `<div class="ra-note">批注：${UI.esc(r.reject_reason)}</div>` : ''}
        </div>
        <div class="ra-acts">
          ${r.status === 'done' ? `
            <button class="btn primary xs" data-act="ra-approve" data-id="${r.id}">确认 +${r.points}⭐</button>
            <button class="btn ghost xs" data-act="ra-reject" data-id="${r.id}">退回</button>` : ''}
          <button class="btn ghost xs r" data-act="ra-del" data-id="${r.id}">删除</button>
        </div>
      </div>`).join('');
  }

  function stName(s) {
    return { pending: '等孩子读', done: '待确认', approved: '已通过', rejected: '已退回' }[s] || s;
  }

  /* ---------------- 内置教材库 ---------------- */
  function catalogView(c) {
    if (!c) return '<div class="empty">正在读目录…</div>';
    return `<div class="page">
      <h2 class="page-h">📥 内置教材库</h2>
      <p class="muted small">
        共收录 <b>${c.total_available || 0}</b> 本，本机已下载 <b>${c.local_count || 0}</b> 本。
        索引存在本地，只有真的点下载时才需要联网。
      </p>

      <div class="card">
        <div class="grid2">
          <label class="f"><span>学段</span>
            <select data-act="cat-stage">
              <option value="">全部</option>
              ${(c.stages || []).map(s => `<option value="${s}" ${App.state.catFilter.stage === s ? 'selected' : ''}>${s}</option>`).join('')}
            </select>
          </label>
          <label class="f"><span>学科</span>
            <select data-act="cat-subject">
              <option value="">全部</option>
              ${Object.keys(SUBJ_NAME).map(k => `<option value="${k}" ${App.state.catFilter.subject === k ? 'selected' : ''}>${SUBJ_NAME[k]}</option>`).join('')}
            </select>
          </label>
        </div>
        <div class="grid2">
          <label class="f"><span>版本</span>
            <select data-act="cat-version">
              <option value="">全部</option>
              ${(c.versions || []).map(v => `<option value="${v}" ${App.state.catFilter.version === v ? 'selected' : ''}>${v}</option>`).join('')}
            </select>
          </label>
          <label class="f"><span>年级</span>
            <select data-act="cat-grade">
              <option value="">全部</option>
              ${['一年级', '二年级', '三年级', '四年级', '五年级', '六年级'].map(g => `<option value="${g}" ${App.state.catFilter.grade === g ? 'selected' : ''}>${g}</option>`).join('')}
            </select>
          </label>
        </div>
        <label class="f"><span>搜索</span><input id="catQ" data-act="cat-q" placeholder="输入书名关键字，如 语文 或 数学" value="${UI.esc(App.state.catFilter.q || '')}"></label>
      </div>

      <div class="sec-t">找到 ${c.count} 本
        <button class="btn ghost xs" data-act="cat-back">返回教材库</button>
      </div>

      <div class="tb-list">
        ${(c.books || []).map(b => `
          <label class="cat-row ${b.added ? 'done' : ''}">
            <input type="checkbox" class="cat-pick" value="${UI.esc(b.path)}" ${b.added ? 'disabled' : ''}>
            <div class="cat-main">
              <div class="tb-t">${UI.esc(b.title)}</div>
              <div class="tb-s">${UI.esc(b.subject_name)} · ${UI.esc(b.version)} · ${UI.esc(b.grade)}${UI.esc(b.term)} · ${b.size_mb} MB</div>
            </div>
            <span class="chip ${b.added ? 'ok' : ''}">${b.added ? (b.status === 'ready' ? '已在书架' : '已加入') : '可加入'}</span>
          </label>`).join('') || '<div class="empty" style="padding:24px 0">没有匹配的教材</div>'}
      </div>

      <div class="sticky-foot">
        <button class="btn primary block" data-act="cat-add">加入书架并下载</button>
      </div>
    </div>`;
  }

  /* ---------------- 下载进度轮询 ---------------- */
  function startPoll() {
    stopPoll();
    pollTimer = setInterval(async () => {
      const books = (App.state.parent.books && App.state.parent.books.books) || [];
      const busy = books.filter(b => b.status === 'download');
      if (!busy.length) { stopPoll(); return; }
      let changed = false;
      for (const b of busy) {
        try {
          const s = await API.get(`/api/parent/textbook/${b.id}/status`);
          if (s.status !== 'download') { changed = true; }
        } catch (e) { }
      }
      if (changed) App.load();
    }, 3000);
  }

  function stopPoll() { clearInterval(pollTimer); pollTimer = 0; }

  /* ---------------- 动作 ---------------- */
  const actions = {
    'tb-upload'() {
      const inp = document.createElement('input');
      inp.type = 'file';
      inp.accept = 'application/pdf,.pdf';
      inp.addEventListener('change', async () => {
        const f = inp.files && inp.files[0];
        if (!f) return;
        if (!/\.pdf$/i.test(f.name)) { UI.toast('请选择 PDF 文件', 'err'); return; }
        UI.sheet({
          title: '这本是什么教材？',
          body: `
            <label class="f"><span>书名</span><input id="upTitle" value="${UI.esc(f.name.replace(/\.pdf$/i, ''))}"></label>
            <label class="f"><span>学科</span><select id="upSubj">
              ${Object.keys(SUBJ_NAME).map(k => `<option value="${k}" ${k === 'chinese' ? 'selected' : ''}>${SUBJ_NAME[k]}</option>`).join('')}
            </select></label>
            <div class="grid2">
              <label class="f"><span>年级</span><input id="upGrade" placeholder="一年级"></label>
              <label class="f"><span>册次</span><input id="upTerm" placeholder="上册"></label>
            </div>
            <p class="small muted">${(f.size / 1048576).toFixed(1)} MB，上传后保存在本机，不上传到任何外部服务器。</p>`,
          okText: '上传',
          async onOk(wrap) {
            const fields = {
              title: wrap.querySelector('#upTitle').value.trim(),
              subject: wrap.querySelector('#upSubj').value,
              grade: wrap.querySelector('#upGrade').value.trim(),
              term: wrap.querySelector('#upTerm').value.trim(),
              version: '家长上传',
            };
            UI.toast('正在上传…');
            try {
              await API.uploadWith('/api/parent/textbooks/upload', f, fields);
              UI.close();
              UI.toast('教材已上架 📚');
              App.load();
            } catch (e) { UI.toast(e.message, 'err'); return false; }
          },
        });
      });
      inp.click();
    },

    'tb-url'() {
      UI.sheet({
        title: '从远程地址添加',
        body: `
          <label class="f"><span>教材地址（PDF 直链）</span>
            <input id="uUrl" placeholder="https://example.com/book.pdf"></label>
          <label class="f"><span>书名</span><input id="uTitle" placeholder="不填就用文件名"></label>
          <label class="f"><span>学科</span><select id="uSubj">
            ${Object.keys(SUBJ_NAME).map(k => `<option value="${k}" ${k === 'chinese' ? 'selected' : ''}>${SUBJ_NAME[k]}</option>`).join('')}
          </select></label>
          <label class="f row-inline"><input id="uDl" type="checkbox" checked>
            <span>下载到本机（推荐，之后打开不再联网）</span></label>
          <p class="small muted">不勾选则只记一条链接，每次打开都要能访问那个地址。</p>`,
        okText: '添加',
        async onOk(wrap) {
          const body = {
            url: wrap.querySelector('#uUrl').value.trim(),
            title: wrap.querySelector('#uTitle').value.trim(),
            subject: wrap.querySelector('#uSubj').value,
            download: wrap.querySelector('#uDl').checked,
          };
          if (!body.url) { UI.toast('请填写地址', 'err'); return false; }
          try {
            const r = await API.post('/api/parent/textbooks/link', body);
            UI.close();
            UI.toast(body.download ? '正在下载…' : '已加入书架');
            App.load();
          } catch (e) { UI.toast(e.message, 'err'); return false; }
        },
      });
    },

    'tb-catalog'() {
      App.state.catFilter = App.state.catFilter || { stage: '小学', subject: '', version: '', grade: '', q: '' };
      App.state.view = 'catalog';
      App.load();
    },

    'cat-back'() { App.state.view = 'library'; App.load(); },

    'tb-current'(el) {
      const id = +el.dataset.id;
      const b = ((App.state.parent.books || {}).books || []).find(x => x.id === id);
      API.patch(`/api/parent/textbook/${id}`, { is_current: !(b && b.is_current) })
        .then(() => App.load()).catch(e => UI.toast(e.message, 'err'));
    },

    'tb-retry'(el) {
      API.post(`/api/parent/textbook/${el.dataset.id}/retry`, {})
        .then(() => { UI.toast('重新下载中…'); App.load(); })
        .catch(e => UI.toast(e.message, 'err'));
    },

    'tb-del'(el) {
      const id = +el.dataset.id;
      UI.confirm('删除这本教材？', '文件会从本机删除，阅读进度也一起没了。', true).then(ok => {
        if (!ok) return;
        API.del(`/api/parent/textbook/${id}`)
          .then(() => { UI.toast('已删除'); App.load(); })
          .catch(e => UI.toast(e.message, 'err'));
      });
    },

    'tb-edit'(el) {
      const id = +el.dataset.id;
      const b = ((App.state.parent.books || {}).books || []).find(x => x.id === id);
      if (!b) return;
      UI.sheet({
        title: '编辑教材信息',
        body: `
          <label class="f"><span>书名</span><input id="ebTitle" value="${UI.esc(b.title)}"></label>
          <label class="f"><span>学科</span><select id="ebSubj">
            ${Object.keys(SUBJ_NAME).map(k => `<option value="${k}" ${b.subject === k ? 'selected' : ''}>${SUBJ_NAME[k]}</option>`).join('')}
          </select></label>
          <div class="grid2">
            <label class="f"><span>年级</span><input id="ebGrade" value="${UI.esc(b.grade || '')}"></label>
            <label class="f"><span>册次</span><input id="ebTerm" value="${UI.esc(b.term || '')}"></label>
          </div>
          <label class="f"><span>版本</span><input id="ebVer" value="${UI.esc(b.version || '')}"></label>
          <label class="f"><span>备注</span><input id="ebNote" value="${UI.esc(b.note || '')}"></label>`,
        okText: '保存',
        async onOk(wrap) {
          try {
            await API.patch(`/api/parent/textbook/${id}`, {
              title: wrap.querySelector('#ebTitle').value.trim(),
              subject: wrap.querySelector('#ebSubj').value,
              grade: wrap.querySelector('#ebGrade').value.trim(),
              term: wrap.querySelector('#ebTerm').value.trim(),
              version: wrap.querySelector('#ebVer').value.trim(),
              note: wrap.querySelector('#ebNote').value.trim(),
            });
            UI.close(); UI.toast('已保存'); App.load();
          } catch (e) { UI.toast(e.message, 'err'); return false; }
        },
      });
    },

    /* ---- 目录筛选 ---- */
    'cat-stage'(el) { App.state.catFilter.stage = el.value; App.load(); },
    'cat-subject'(el) { App.state.catFilter.subject = el.value; App.state.catFilter.version = ''; App.load(); },
    'cat-version'(el) { App.state.catFilter.version = el.value; App.load(); },
    'cat-grade'(el) { App.state.catFilter.grade = el.value; App.load(); },
    'cat-q'(el) {
      // 只在真的变了才刷新：change 在失焦时也会触发，否则点个下拉就整页重建
      const v = el.value.trim();
      if (v === (App.state.catFilter.q || '')) return;
      clearTimeout(App._catq);
      App._catq = setTimeout(() => { App.state.catFilter.q = v; App.load(); }, 400);
    },

    async 'cat-add'() {
      const picks = [...document.querySelectorAll('.cat-pick:checked')].map(x => x.value);
      if (!picks.length) { UI.toast('先勾选几本教材'); return; }
      try {
        const r = await API.post('/api/parent/textbooks/fetch', { paths: picks });
        UI.toast(r.downloading ? `已加入 ${r.added} 本，正在下载 ${r.downloading} 本` : `已加入 ${r.added} 本`);
        App.state.view = 'library';
        App.load();
      } catch (e) { UI.toast(e.message, 'err'); }
    },

    /* ---- 阅读作业 ---- */
    async 'ra-create'() {
      const bookId = +(document.getElementById('raBook') || {}).value;
      const kidId = +(document.getElementById('raKid') || {}).value;
      if (!bookId) { UI.toast('先选一本教材'); return; }
      if (!kidId) { UI.toast('先选一个孩子'); return; }
      const body = {
        kid_id: kidId,
        textbook_id: bookId,
        page_from: +document.getElementById('raFrom').value || 1,
        page_to: +document.getElementById('raTo').value || 1,
        points: +document.getElementById('raPts').value || 5,
        due_date: document.getElementById('raDue').value || '',
        note: document.getElementById('raNote').value.trim(),
      };
      try {
        await API.post('/api/parent/reading', body);
        UI.toast('布置好啦，孩子打开教材就能看到 📖');
        App.load();
      } catch (e) { UI.toast(e.message, 'err'); }
    },

    'ra-approve'(el) {
      const id = +el.dataset.id;
      API.post('/api/parent/reading/review', { id, action: 'approve' })
        .then(r => {
          UI.toast(r.awarded ? `+${r.awarded} ⭐${r.note ? '，' + r.note : ''}` : (r.note || '已确认'));
          App.load();
        }).catch(e => UI.toast(e.message, 'err'));
    },

    'ra-reject'(el) {
      const id = +el.dataset.id;
      UI.sheet({
        title: '退回这份作业',
        body: `<label class="f"><span>说一句（孩子能看到）</span><input id="rjWhy" placeholder="再读一遍第 3 页，明天重新交"></label>`,
        okText: '退回', danger: true,
        async onOk(wrap) {
          try {
            await API.post('/api/parent/reading/review', {
              id, action: 'reject', reason: wrap.querySelector('#rjWhy').value.trim(),
            });
            UI.close(); UI.toast('已退回'); App.load();
          } catch (e) { UI.toast(e.message, 'err'); return false; }
        },
      });
    },

    'ra-del'(el) {
      UI.confirm('删除这份阅读作业？', '', true).then(ok => {
        if (!ok) return;
        API.del(`/api/parent/reading/${el.dataset.id}`)
          .then(() => App.load()).catch(e => UI.toast(e.message, 'err'));
      });
    },
  };

  return { library, catalogView, readingsHtml, actions, startPoll, stopPoll };
})();
