/* ============================================================
   轻量 UI 工具：吐司、底部弹层、确认框、图片选择
   ============================================================ */
const UI = (() => {
  function toast(msg, type) {
    const box = document.getElementById('toastRoot');
    const el = document.createElement('div');
    el.className = 'toast ' + (type || '');
    el.textContent = msg;
    box.appendChild(el);
    setTimeout(() => {
      el.style.transition = 'opacity .3s'; el.style.opacity = '0';
      setTimeout(() => el.remove(), 320);
    }, 2000);
  }

  function close() { document.getElementById('modalRoot').innerHTML = ''; }

  /**
   * 通用弹层。opt = {title, body(html), okText, cancelText, onOk(el), danger}
   * onOk 返回 false 可阻止关闭。
   */
  function sheet(opt) {
    const root = document.getElementById('modalRoot');
    const wrap = document.createElement('div');
    wrap.className = 'mask';
    wrap.innerHTML = `
      <div class="sheet">
        <h3>${opt.title || ''}</h3>
        <div class="body">${opt.body || ''}</div>
        <div class="acts">
          <button class="btn ghost" data-x="cancel">${opt.cancelText || '取消'}</button>
          <button class="btn ${opt.danger ? 'r' : 'primary'}" data-x="ok">${opt.okText || '确定'}</button>
        </div>
      </div>`;
    wrap.addEventListener('click', (e) => {
      if (e.target === wrap) { close(); return; }
      const x = e.target.closest('[data-x]');
      if (!x) return;
      if (x.dataset.x === 'cancel') close();
      if (x.dataset.x === 'ok') {
        // onOk 大多是 async（里面要发请求），直接比较返回值拿到的永远是
        // Promise，校验失败时拦不住关闭。这里统一包成 Promise 来等结果。
        const btn = x;
        btn.disabled = true;
        Promise.resolve()
          .then(() => opt.onOk && opt.onOk(wrap))
          .then((r) => { btn.disabled = false; if (r !== false) close(); })
          .catch(() => { btn.disabled = false; });
      }
    });
    root.innerHTML = '';
    root.appendChild(wrap);
    const first = wrap.querySelector('input, textarea');
    if (first) setTimeout(() => first.focus(), 60);
    return wrap;
  }

  function confirm(title, msg, danger) {
    return new Promise((resolve) => {
      sheet({
        title,
        body: `<p class="muted">${msg || ''}</p>`,
        okText: '确定', danger,
        onOk: () => { resolve(true); },
      });
      // 取消时也要 resolve
      const root = document.getElementById('modalRoot');
      root.querySelector('[data-x="cancel"]').addEventListener('click', () => resolve(false));
    });
  }

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  /** 头像可能是 emoji，也可能是上传过的图片地址，这里统一渲染。
   *  px 为空表示放进已有的圆形容器（.ava / .face）里，由 CSS 决定大小。 */
  function avatar(a, px) {
    const v = String(a == null ? '' : a).trim();
    if (/^(\/uploads\/|https?:\/\/|data:image\/)/.test(v)) {
      const wh = px ? ` style="width:${px}px;height:${px}px"` : '';
      return `<img class="av-pic" src="${esc(v)}" alt=""${wh}>`;
    }
    return esc(v || '🙂');
  }

  function avatarBlock(a, px, cls) {
    return `<div class="ava ${cls || ''}" style="width:${px}px;height:${px}px;border-radius:50%;overflow:hidden;
      background:var(--gold-soft);display:grid;place-items:center;font-size:${Math.round(px * 0.6)}px">${avatar(a)}</div>`;
  }

  /** <option> 里放不了图片，所以这里退化成纯文本 */
  function avatarText(a) {
    const v = String(a == null ? '' : a).trim();
    if (/^(\/uploads\/|https?:\/\/|data:image\/)/.test(v)) return '🙂';
    return v || '🙂';
  }

  const EMOJIS = ['🙂', '😀', '😄', '😎', '🤩', '🥳', '😇', '🧐',
    '👦', '👧', '🧒', '🧑', '👩', '👨', '🧓', '🦸',
    '🐱', '🐶', '🐰', '🦊', '🐻', '🐼', '🐨', '🐯',
    '🦁', '🐷', '🐸', '🐵', '🐧', '🐳', '🦄', '🐉',
    '🚀', '⭐', '🌈', '🌻', '🍎', '⚽', '🏀', '🎨'];

  /**
   * 选头像：一排 emoji + 从相册上传。
   * onPick(url) 收到的是 emoji 或 /uploads/xxx。
   */
  function pickAvatar(current, onPick) {
    const wrap = sheet({
      title: '换个头像',
      body: `
        <div class="av-pick">${avatar(current, 64)}</div>
        <div class="av-grid">
          ${EMOJIS.map(e => `<button class="av-opt ${e === current ? 'on' : ''}"
             data-av="${e}">${e}</button>`).join('')}
        </div>
        <button class="btn ghost block" style="margin-top:12px" data-x="up">📷 从相册选一张</button>`,
      okText: '关闭'
    });

    wrap.addEventListener('click', (e) => {
      const b = e.target.closest('[data-av]');
      if (b) { onPick(b.dataset.av); close(); return; }
      if (e.target.closest('[data-x="up"]')) {
        pickImage((url) => { onPick(url); close(); });
      }
    });
    return wrap;
  }

  /** 图片选择：手机直接调起相机/相册，返回服务端 url */
  function pickImage(onUrl) {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.capture = 'environment';
    input.onchange = async () => {
      const f = input.files[0];
      if (!f) return;
      try {
        toast('正在上传…');
        const r = await API.upload(f);
        onUrl(r.url);
      } catch (e) { toast(e.message, 'err'); }
    };
    input.click();
  }

  function celebrate(emoji, title, sub) {
    const box = document.createElement('div');
    box.className = 'confetti';
    box.innerHTML = `<div class="box">
        <div class="big">${emoji}</div>
        <h3 style="margin:6px 0 2px">${esc(title)}</h3>
        <p class="muted small">${esc(sub || '')}</p>
        <button class="btn primary lg" style="margin-top:14px" data-x="ok" onclick="this.closest('.confetti').remove()">太棒啦</button>
      </div>`;
    box.addEventListener('click', (e) => { if (e.target === box) box.remove(); });
    document.body.appendChild(box);
    setTimeout(() => box.remove(), 6000);
  }

  function todayCn(d) {
    const t = d ? new Date(d) : new Date();
    const days = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
    return `${t.getMonth() + 1}月${t.getDate()}日 ${days[t.getDay()]}`;
  }

  return {
    toast, sheet, close, confirm, esc, pickImage, celebrate, todayCn,
    avatar, avatarBlock, avatarText, pickAvatar, EMOJIS,
  };
})();
