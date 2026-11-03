/* ============================================================
   应用入口：登录 → 角色路由 → 视图渲染 → 事件委托
   ============================================================ */
/* ---------------------------------------------------------------
   错题汇总的筛选条件：放在 App 外面，家长端视图与动作共用同一份状态，
   切页面回来时不会丢。
   --------------------------------------------------------------- */
const WBK = {
  kid_id: 0, subject: '', status: 'pending', ids: [], variants: 0, answers: 1,
  set(kid_id) { if (kid_id && kid_id !== this.kid_id) this.kid_id = kid_id; },
  q() {
    const p = new URLSearchParams({ kid_id: this.kid_id, status: this.status,
      answers: this.answers, variants: this.variants });
    if (this.subject) p.set('subject', this.subject);
    if (this.ids.length) p.set('ids', this.ids.join(','));
    return p.toString();
  },
  query() { return { kid_id: this.kid_id, subject: this.subject, status: this.status }; },
};

/* ---------------------------------------------------------------
   孩子端错题本的筛选（科目 / 排序），同理单独存放
   --------------------------------------------------------------- */
const WB_FILTER = { subject: '', order: 'recent' };

const App = (() => {

  const LOGIN_STATE = { tab: 'parent', families: [], fid: 0, kid: 0, pin: '' };
  const BRAND = { name: '星星成长记', subtitle: '让好习惯看得见', logo: '⭐' };

  const state = {
    role: null,            // child | parent
    user: null,
    view: 'home',
    child: {
      home: null, wishes: null, me: null, wrong: null,
      garden: null, focus: null, word: null, pet: null, family: null,
      books: null, readings: null,
    },
    parent: {
      overview: null, pending: null, tasks: null, wishes: null,
      members: null, rules: null, school: null, wrong: null,
      books: null, readings: null, catalog: null,
    },
    // 内置教材库的筛选条件，切页面回来不丢
    catFilter: { stage: '小学', subject: '', version: '', grade: '', q: '' },
    booted: false,
  };

  function applyBrand() {
    document.title = BRAND.name || '星星成长记';
  }

  function brandBar() {
    const who = state.user ? state.user.name : '';
    return `<div class="topbar">
      <span class="tb-logo">${UI.esc(BRAND.logo)}</span>
      <span class="tb-name">${UI.esc(BRAND.name)}</span>
      ${who ? `<span class="tb-sub">${UI.esc(who)}</span>` : ''}
    </div>`;
  }

  /* ------------------------------------------------ 登录 */
  function loginView() {
    const families = LOGIN_STATE.families;
    const fam = families.find(f => f.id === LOGIN_STATE.fid) || families[0] || { kids: [] };

    if (LOGIN_STATE.tab === 'child') {
      return `
        <div class="login-wrap">
          <div class="logo">${UI.esc(BRAND.logo)}</div>
          <h1>${UI.esc(BRAND.name)}</h1>
          <p class="muted">点自己的头像，输入口令</p>
          <div class="login-box">
            <div class="seg">
              <button data-act="tab" data-v="parent">家长登录</button>
              <button class="on" data-act="tab" data-v="child">我是小朋友</button>
            </div>
            ${families.length ? `
            <div class="kid-picker">
              ${fam.kids.map(k => `
                <button class="av ${LOGIN_STATE.kid === k.id ? 'on' : ''}" data-act="pick-kid" data-id="${k.id}">
                  <div class="face">${UI.avatar(k.avatar)}</div>
                  <div class="nm">${UI.esc(k.name)}</div>
                </button>`).join('')}
            </div>` : '<p class="muted">还没有创建孩子账号，请先用家长登录</p>'}
            ${LOGIN_STATE.kid ? pinPad() : ''}
          </div>
        </div>`;
    }

    return `
      <div class="login-wrap">
        <div class="logo">${UI.esc(BRAND.logo)}</div>
        <h1>${UI.esc(BRAND.name)}</h1>
        <p class="muted">${UI.esc(BRAND.subtitle)}</p>
        <div class="login-box">
          <div class="seg">
            <button class="on" data-act="tab" data-v="parent">家长登录</button>
            <button data-act="tab" data-v="child">我是小朋友</button>
          </div>
          <div class="card" style="text-align:left">
            <label class="f"><span>用户名</span><input id="pUser" placeholder="dad" autocomplete="username"></label>
            <label class="f"><span>口令</span><input id="pPin" type="password" placeholder="演示账号 1234"></label>
            <button class="btn primary block lg" data-act="do-parent-login">登录</button>
            <p class="small muted" style="margin-top:10px">
              演示账号： dad / 1234（爸爸）、 mom / 1234（妈妈）。多名家长可以同时登录，谁看到谁审批。
            </p>
          </div>
        </div>
      </div>`;
  }

  function pinPad() {
    return `
      <div class="card">
        <div class="pindots">${[0, 1, 2, 3].map(i => `<i class="${LOGIN_STATE.pin.length > i ? 'on' : ''}"></i>`).join('')}</div>
        <div class="pinpad">
          ${[1, 2, 3, 4, 5, 6, 7, 8, 9].map(n => `<button data-act="pin" data-n="${n}">${n}</button>`).join('')}
          <button data-act="pin-clear">清空</button>
          <button data-act="pin" data-n="0">0</button>
          <button data-act="pin-del">⌫</button>
        </div>
      </div>`;
  }

  /* ------------------------------------------------ 数据加载 */
  async function load(view = state.view) {
    try {
      if (state.role === 'child') {
        state.child.home = await API.get('/api/child/home');
        if (view === 'wishes') state.child.wishes = await API.get('/api/child/wishes');
        if (view === 'me') state.child.me = await API.get('/api/child/me/detail');
        if (view === 'wrong') state.child.wrong = await API.get(
          '/api/child/wrong' + (WB_FILTER.subject ? '?subject=' + encodeURIComponent(WB_FILTER.subject) : '')
          + (WB_FILTER.order ? (WB_FILTER.subject ? '&' : '?') + 'order=' + WB_FILTER.order : ''));
        if (view === 'garden') state.child.garden = await API.get('/api/child/garden');
        if (view === 'focus') state.child.focus = await API.get('/api/child/focus');
        if (view === 'word') state.child.word = await API.get('/api/child/word/today');
        if (view === 'pet') state.child.pet = await API.get('/api/child/pet');
        if (view === 'family') state.child.family = await API.get('/api/child/family');
        if (view === 'books') {
          state.child.books = await API.get('/api/child/textbooks');
          state.child.readings = await API.get('/api/child/readings');
        }
      } else {
        if (view === 'school') state.parent.school = await API.get('/api/parent/school');
        if (view === 'wrongbook') {
          const q = WBK.query();
          state.parent.wrong = await API.get('/api/parent/wrong/summary?kid_id=' + q.kid_id + '&status=' + q.status
            + (q.subject ? '&subject=' + encodeURIComponent(q.subject) : '')
            + (WBK.variants ? '&variants=1' : ''));
          state.parent.wrongStats = await API.get('/api/parent/wrong/stats?kid_id=' + q.kid_id);
        }
        if (view === 'todo') {
          state.parent.overview = await API.get('/api/parent/overview');
          state.parent.pending = await API.get('/api/parent/pending');
        } else if (view === 'tasks') {
          if (!state.parent.tasks) state.parent.tasks = await API.get('/api/parent/tasks');
          else state.parent.tasks = await API.get('/api/parent/tasks');
        } else if (view === 'wishes') {
          state.parent.wishes = await API.get('/api/parent/wishes');
        } else if (view === 'more') {
          state.parent.members = await API.get('/api/parent/members');
          state.parent.overview = await API.get('/api/parent/overview');
          state.parent.rules = await API.get('/api/parent/rules');
        } else if (view === 'rules') {
          state.parent.rules = await API.get('/api/parent/rules');
        } else if (view === 'library') {
          state.parent.books = await API.get('/api/parent/textbooks');
          state.parent.readings = await API.get('/api/parent/readings');
          if (!state.parent.members) state.parent.members = await API.get('/api/parent/members');
          BookAdmin.startPoll();
        } else if (view === 'catalog') {
          const f = state.catFilter || {};
          const p = new URLSearchParams({ limit: 200 });
          ['stage', 'subject', 'version', 'grade', 'q'].forEach(k => { if (f[k]) p.set(k, f[k]); });
          state.parent.catalog = await API.get('/api/parent/textbooks/catalog?' + p.toString());
          if (!state.parent.books) state.parent.books = await API.get('/api/parent/textbooks');
        }
      }
    } catch (e) {
      if (e.status === 401) { API.clear(); location.reload(); return; }
      UI.toast(e.message, 'err');
    }
    render();
  }

  /* ------------------------------------------------ 渲染 */
  function render() {
    const root = document.getElementById('app');

    if (!API.has() || !state.role) {
      root.className = 'app';
      root.innerHTML = loginView();
      return;
    }

    root.className = 'app' + (state.role === 'parent' ? ' wide' : '');
    let body = '';

    if (state.role === 'child') {
      const d = state.child;
      if (state.view === 'home') body = ChildViews.home(d.home);
      else if (state.view === 'wishes') body = ChildViews.wishes(d.wishes || { wishes: d.home.wishes });
      else if (state.view === 'game') body = ChildViews.game(d.home);
      else if (state.view === 'wrong') body = ChildViews.wrong(d.wrong);
      else if (state.view === 'garden') body = ChildViews.garden(d.garden);
      else if (state.view === 'focus') body = ChildViews.focus(d.focus);
      else if (state.view === 'word') body = ChildViews.word(d.word);
      else if (state.view === 'pet') body = ChildViews.pet(d.pet);
      else if (state.view === 'family') body = ChildViews.family(d.family);
      else if (state.view === 'books') body = BookViews.shelf(d.books, d.readings);
      else if (state.view === 'me') body = ChildViews.me(d.me);
    } else {
      const p = state.parent;
      if (state.view === 'todo') body = ParentViews.todo(p);
      else if (state.view === 'tasks') body = ParentViews.tasks(p);
      else if (state.view === 'wishes') body = ParentViews.wishes(p);
      else if (state.view === 'school') body = ParentViews.school(p);
      else if (state.view === 'wrongbook') body = ParentViews.wrongbook(p);
      else if (state.view === 'more') body = ParentViews.more(p);
      else if (state.view === 'rules') body = ParentViews.rules(p);
      else if (state.view === 'library') {
        const kids = ((p.members && p.members.members) || []).filter(m => m.role === 'child');
        body = BookAdmin.library(p.books, kids);
      } else if (state.view === 'catalog') body = BookAdmin.catalogView(p.catalog);
    }

    root.innerHTML = brandBar() + body + tabbar();
    document.body.className = state.role === 'child'
      ? 'mode-' + (state.user.ui_mode || 'childish') : '';
  }

  function tabbar() {
    const tabs = state.role === 'child'
      ? [['home', '🏠', '首页'], ['wishes', '🌈', '愿望'], ['game', '🎮', '闯关'],
         ['books', '📚', '教材'], ['me', '🏅', '我的']]
      : [['todo', '🔔', '待办'], ['tasks', '📋', '任务'], ['wishes', '🌈', '愿望'], ['more', '⚙️', '管理']];

    const badge = state.role === 'parent' && state.parent.overview
      ? state.parent.overview.counts.total : 0;

    return `<nav class="tabbar"><div class="in">
      ${tabs.map(([k, i, n]) => `
        <button class="${state.view === k ? 'on' : ''}" data-act="go" data-v="${k}">
          <span class="ti">${i}</span>
          ${k === 'todo' && badge ? `<span class="dot">${badge}</span>` : ''}
          ${n}
        </button>`).join('')}
    </div></nav>`;
  }

  /* ------------------------------------------------ 启动 */
  async function boot() {
    try { LOGIN_STATE.families = await API.get('/api/auth/roster'); } catch (e) { }
    if (LOGIN_STATE.families.length) LOGIN_STATE.fid = LOGIN_STATE.families[0].id;

    // 标题栏文案：没登录也要显示，所以是公开接口
    try {
      const info = await API.get('/api/app-info');
      Object.assign(BRAND, info || {});
    } catch (e) { }
    applyBrand();

    if (!API.has()) { render(); return; }
    try {
      const me = await API.get('/api/auth/me');
      state.user = me;
      state.role = me.role === 'child' ? 'child' : 'parent';
      state.view = state.role === 'child' ? 'home' : 'todo';
      await load();
    } catch (e) {
      API.clear();
      render();
    }
  }

  /* ------------------------------------------------ 行为 */
  const globalActions = {
    go(el) {
      state.view = el.dataset.v;
      load(state.view);
    },

    tab(el) {
      LOGIN_STATE.tab = el.dataset.v;
      LOGIN_STATE.pin = '';
      render();
    },

    'pick-kid'(el) {
      LOGIN_STATE.kid = +el.dataset.id;
      LOGIN_STATE.pin = '';
      render();
    },

    'pin'(el) {
      LOGIN_STATE.pin = (LOGIN_STATE.pin + el.dataset.n).slice(0, 4);
      render();
      if (LOGIN_STATE.pin.length === 4) doChildLogin();
    },

    'pin-del'() { LOGIN_STATE.pin = LOGIN_STATE.pin.slice(0, -1); render(); },
    'pin-clear'() { LOGIN_STATE.pin = ''; render(); },

    async 'do-parent-login'() {
      const username = document.getElementById('pUser').value.trim();
      const pin = document.getElementById('pPin').value;
      if (!username || !pin) { UI.toast('请输入用户名和口令', 'err'); return; }
      try {
        const r = await API.post('/api/auth/parent-login', { username, pin });
        API.set(r.token);
        state.user = r.user;
        state.role = 'parent';
        state.view = 'todo';
        await load();
      } catch (e) { UI.toast(e.message, 'err'); }
    },

    logout() {
      API.clear();
      state.role = null; state.user = null;
      LOGIN_STATE.pin = ''; LOGIN_STATE.kid = 0;
      LOGIN_STATE.tab = state.role === 'child' ? 'child' : 'parent';
      render();
    },
  };

  async function doChildLogin() {
    try {
      const r = await API.post('/api/auth/child-login',
        { child_id: LOGIN_STATE.kid, pin: LOGIN_STATE.pin });
      API.set(r.token);
      state.user = r.user;
      state.role = 'child';
      state.view = 'home';
      LOGIN_STATE.pin = '';
      await load();
    } catch (e) {
      UI.toast(e.message, 'err');
      LOGIN_STATE.pin = '';
      render();
    }
  }

  /* 事件委托：所有按钮走同一条路径 */
  function bind() {
    const ALL = Object.assign({}, globalActions,
      ChildViews.actions, ParentViews.actions,
      BookViews.actions, BookAdmin.actions);

    document.addEventListener('click', async (e) => {
      const el = e.target.closest('[data-act]');
      if (!el) return;
      const fn = ALL[el.dataset.act];
      if (!fn) return;
      e.preventDefault();
      try { await fn(el, e); } catch (err) { UI.toast(err.message || '出错了', 'err'); }
    });

    // 下拉控件的事件是 change，不是 click —— 走同一套动作表
    document.addEventListener('change', async (e) => {
      const el = e.target.closest('[data-act]');
      if (!el) return;
      const fn = ALL[el.dataset.act];
      if (!fn) return;
      try { await fn(el, e); } catch (err) { UI.toast(err.message || '出错了', 'err'); }
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && LOGIN_STATE.tab === 'parent' && !API.has()) {
        globalActions['do-parent-login']();
      }
    });
  }

  return { state, boot, render, load, bind, LOGIN_STATE, BRAND, applyBrand };
})();

App.bind();
App.boot();
