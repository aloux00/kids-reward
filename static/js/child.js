/* ============================================================
   孩子端视图。字段严格按后端返回，不含累计获得总数。
   ============================================================ */
const ChildViews = (() => {

  const CAT = { study: { n: '学习', c: '📚' }, exercise: { n: '运动', c: '🏃' },
                chore: { n: '家务', c: '🧹' }, habit: { n: '习惯', c: '⏰' },
                game: { n: '游戏', c: '🎮' } };

  const TOOLS = [
    ['garden', '🌱', '星星花园', '种下去慢慢等'],
    ['focus', '🍅', '专注番茄', '专心就有星'],
    ['word', '📖', '每日识字', '今天认几个字'],
    ['pet', '🐾', '我的伙伴', '和你一起长大'],
    ['family', '👨‍👩‍👧', '家庭共学', '看看爸妈陪了多久'],
  ];

  /* ------------------------------------------------ 首页 */
  function home(d) {
    const p = d.profile, coin = d.coin, exp = d.exp;
    const doneCount = d.today_tasks.filter(t => t.status === 'approved').length;

    return `
      ${hero(p)}
      ${coinCard(coin)}
      ${wishSection(d.wishes)}

      <div class="sec-title">
        <h3>📋 今日任务</h3>
        <span class="hint">${doneCount}/${d.today_tasks.length} 已完成 · 今天还能赚 ${coin.daily_remain} 星</span>
      </div>
      <div>${d.today_tasks.length ? d.today_tasks.map(taskRow).join('') : emptyBox('今天没有任务，休息一下 🙂')}</div>

      <div class="sec-title">
        <h3>✨ 额外任务</h3>
        <span class="hint">多劳多得，不做不扣星</span>
      </div>
      <div>${d.extra_tasks.length ? d.extra_tasks.map(taskRow).join('') : emptyBox('暂时没有额外机会，明天再来看看')}</div>

      <div class="sec-title"><h3>🚀 我的小工具</h3><span class="hint">慢慢玩，都是给你准备的</span></div>
      <div class="tool-grid">
        ${TOOLS.map(t => `
          <button class="tool" data-act="go" data-v="${t[0]}">
            <span class="ti">${t[1]}</span>
            <b>${t[2]}</b>
            <span class="small muted">${t[3]}</span>
          </button>`).join('')}
      </div>

      <button class="btn gold block lg" style="margin-top:16px" data-act="apply-open">
        💡 我今天还想加分
      </button>
      <p class="small muted" style="text-align:center;margin-top:8px">
        每天最多申请 2 次，单次最多 10 星 · 要写一句话或拍张照片
      </p>
    `;
  }

  function hero(p) {
    return `
      <div style="height:14px"></div>
      <div class="hero">
        <div class="row spread">
          <div class="row">
            <div class="ava">${UI.avatar(p.avatar)}</div>
            <div>
              <div class="nm">${UI.esc(p.name)}</div>
              <div class="lv">Lv${p.level} ${UI.esc(p.level_title)} ${p.display_title ? '· ' + UI.esc(p.display_title) : ''}</div>
            </div>
          </div>
          <span class="streak">🔥 连续 ${p.streak_days} 天</span>
        </div>
        ${p.level_perk ? `<div class="lv" style="margin-top:10px;opacity:.95">🎖️ 已解锁：${UI.esc(p.level_perk)}</div>` : ''}
      </div>`;
  }

  function coinCard(c) {
    return `
      <div class="coin-card">
        <div class="row spread">
          <div>
            <div class="unit">我的星星币</div>
            <div class="row" style="align-items:baseline;gap:6px">
              <div class="big">${c.available}</div>
              <div class="unit">🌟 可用</div>
            </div>
          </div>
          <div style="text-align:right">
            <div class="unit">今天已领</div>
            <div style="font-size:22px;font-weight:900">${c.today_earned}</div>
          </div>
        </div>
        <div class="sub">
          ${c.frozen > 0 ? `另有 ${c.frozen} 星兑换中 · ` : ''}今天还能再赚 ${c.daily_remain} 星
        </div>
      </div>`;
  }

  function wishSection(wishes) {
    return `
      <div class="sec-title">
        <h3>🌈 我的愿望</h3>
        <span class="hint">${wishes.length ? '左右滑动查看' : ''}</span>
      </div>
      ${wishes.length ? `
        <div class="wish-scroll">
          ${wishes.map(wishCard).join('')}
          <div class="wish-card" style="display:flex;align-items:center;justify-content:center;min-height:150px;box-shadow:none;border:2px dashed #E3DDD4;background:transparent">
            <button class="btn ghost" data-act="wish-new">＋ 许个愿</button>
          </div>
        </div>` : `
        <div class="card">${emptyBox('还没有愿望。想一想你最想要什么？')}
          <button class="btn gold block lg" style="margin-top:10px" data-act="wish-new">＋ 许下第一个愿望</button>
        </div>`}`;
  }

  function wishCard(w) {
    const doing = w.status === 'pending';
    // 星星币由家长定价；priced 为 false 时还没有价格，别显示进度和差额
    return `
      <div class="wish-card ${w.is_primary ? 'primary' : ''}">
        ${w.is_primary ? '<div class="flag">主目标</div>' : ''}
        <div class="cover">${w.cover ? `<img src="${UI.esc(w.cover)}" alt="">` : (w.priced ? (w.cost >= 300 ? '🎡' : w.cost >= 150 ? '🧩' : '🍦') : '🎁')}</div>
        <div class="tt">${UI.esc(w.title)}</div>
        <div class="small muted">${!w.priced ? '等爸爸妈妈定星星币' : (w.gap > 0 ? `还差 ${w.gap} 星` : '可以兑换啦！')}</div>
        ${w.priced ? `<div class="bar"><i style="width:${w.progress}%"></i></div>
        <div class="row spread">
          <span class="small muted">${w.progress}% · ${w.cost} 星</span>
          ${w.eta_days ? `<span class="small muted">约 ${w.eta_days} 天</span>` : ''}
        </div>` : `<div class="row spread"><span class="small muted">⭐ 星星币待定</span></div>`}
        <div class="row" style="margin-top:9px;gap:6px">
          ${w.priced && w.gap === 0 && !doing && w.frozen_here === 0
            ? `<button class="btn gold sm" data-act="redeem" data-id="${w.id}">🎁 兑换</button>`
            : `<button class="btn ghost sm" data-act="wish-primary" data-id="${w.id}">${w.is_primary ? '当前主目标' : '设为主目标'}</button>`}
          <button class="btn ghost sm" data-act="wish-edit" data-id="${w.id}">编辑</button>
          <button class="btn ghost sm" data-act="wish-drop" data-id="${w.id}">放弃</button>
        </div>
      </div>`;
  }

  function taskRow(t) {
    const cls = t.status === 'approved' ? 'done' : (t.status === 'pending' ? 'wait' : '');
    let right = '';
    if (t.status === 'todo') {
      right = `<button class="btn primary sm" data-act="checkin" data-id="${t.template_id}"
                 data-need="${t.need_photo ? 1 : 0}" data-nm="${UI.esc(t.name)}">
                 ${t.need_photo ? '📷 ' : ''}打卡 +${t.points}</button>`;
    } else if (t.status === 'pending') {
      right = `<span class="tag a">等爸妈确认 +${t.points}</span>`;
    } else if (t.status === 'approved') {
      right = `<span class="tag g">✓ 已完成 ${t.awarded_coin ? '+' + t.awarded_coin : ''}</span>`;
    } else {
      right = `<button class="btn ghost sm" data-act="checkin" data-id="${t.template_id}"
                 data-need="${t.need_photo ? 1 : 0}" data-nm="${UI.esc(t.name)}">重做</button>`;
    }
    return `
      <div class="task ${cls}">
        <div class="ico">${UI.esc(t.icon || '✅')}</div>
        <div style="flex:1;min-width:0">
          <div class="nm">${UI.esc(t.name)}</div>
          <div class="mt">
            ${(CAT[t.category] || {}).n || ''}
            ${t.status === 'rejected' && t.reject_reason ? ' · ' + UI.esc(t.reject_reason) : ''}
            ${t.awarded_coin === 0 && t.status === 'approved' ? ' · 今天这类已达上限' : ''}
          </div>
        </div>
        ${right}
      </div>`;
  }

  function emptyBox(msg) {
    return `<div class="empty"><span class="ico">🌤️</span>${UI.esc(msg)}</div>`;
  }

  /* ------------------------------------------------ 愿望页 */
  function wishes(d) {
    const list = d.wishes || [];
    return `
      <div class="sec-title"><h3>🌈 我的愿望</h3><span class="hint">${UI.todayCn()}</span></div>
      <div class="grid2">
        ${list.length ? list.map(wishFull).join('') : `<div class="card">${emptyBox('还没有愿望')}</div>`}
      </div>
      <button class="btn gold block lg" style="margin-top:14px" data-act="wish-new">＋ 许个新愿望</button>`;
  }

  function wishFull(w) {
    return `
      <div class="card">
        <div class="row spread">
          <div class="row">
            <div class="cover" style="width:58px;height:58px;border-radius:14px;background:linear-gradient(135deg,#FFEFD6,#FFE0B8);display:grid;place-items:center;font-size:30px">
              ${w.cover ? `<img src="${UI.esc(w.cover)}" style="width:100%;height:100%;object-fit:cover;border-radius:14px">` : '🎁'}
            </div>
            <div>
              <div style="font-weight:800">${UI.esc(w.title)}</div>
              <div class="small muted">${w.is_primary ? '主目标 · ' : ''}${w.priced ? `${w.cost} 星` : '⭐ 星星币待爸爸妈妈定'}</div>
            </div>
          </div>
          ${w.status === 'pending' ? '<span class="tag a">待确认</span>' : ''}
        </div>
        ${w.note ? `<p class="small muted" style="margin-top:8px">${UI.esc(w.note)}</p>` : ''}
        ${w.priced ? `
        <div class="bar"><i style="width:${w.progress}%"></i></div>
        <div class="row spread">
          <span class="small muted">${w.gap > 0 ? `还差 ${w.gap} 星` : '星星够了！'}</span>
          <span class="small muted">${w.eta_days ? `按现在的速度约 ${w.eta_days} 天达成` : ''}</span>
        </div>` : `
        <div class="row spread" style="margin-top:6px">
          <span class="small muted">等爸爸妈妈定好星星币，就可以开始攒啦</span>
        </div>`}
        <div class="row" style="margin-top:10px;gap:8px">
          ${w.priced && w.gap === 0 && w.status === 'active' && w.frozen_here === 0
            ? `<button class="btn gold" data-act="redeem" data-id="${w.id}">🎁 兑换它</button>` : ''}
          ${w.is_primary ? '' : `<button class="btn ghost sm" data-act="wish-primary" data-id="${w.id}">设为主目标</button>`}
          <button class="btn ghost sm" data-act="wish-edit" data-id="${w.id}">编辑</button>
          <button class="btn ghost sm" data-act="wish-drop" data-id="${w.id}">放弃</button>
        </div>
      </div>`;
  }

  /* ------------------------------------------------ 小游戏 */
  const G = { round: null, idx: 0, answers: [], t0: 0, timer: null, left: 0 };

  function game(d) {
    const g = d.game;
    if (!g.enabled) return `<div class="card">${emptyBox('小游戏没有开启 🔒')}</div>`;

    if (G.round) return gamePlaying();

    return `
      <div class="sec-title"><h3>🎮 益智闯关</h3><span class="hint">每天 ${g.limit} 局</span></div>
      <div class="card" style="text-align:center">
        <div style="font-size:56px">${g.icon}</div>
        <h3 style="margin:6px 0 4px">${UI.esc(g.name)}</h3>
        <p class="muted small">答对越多，星星越多；全部答对还有额外奖励</p>
        <div class="stat-row" style="margin-top:14px">
          <div class="s"><b>${g.played_today}</b><span>今天已玩</span></div>
          <div class="s"><b>${Math.max(0, g.limit - g.played_today)}</b><span>还剩几局</span></div>
          <div class="s"><b>${g.unlocked ? '已解锁' : '未解锁'}</b><span>游戏资格</span></div>
        </div>
        ${g.unlocked
          ? `<button class="btn primary block lg" data-act="game-start">开始闯关</button>`
          : `<button class="btn ghost block lg" disabled>先把今天的学习任务完成 🔓</button>`}
        <p class="small muted" style="margin-top:8px">分数由爸爸妈妈的手机确认后才能入账哦</p>
      </div>

      ${d.wrong_pending ? `
        <div class="card wrong-entry" data-act="go" data-v="wrong">
          <div class="we-l"><div style="font-size:26px">📕</div></div>
          <div class="we-c">
            <b>错题本里还有 ${d.wrong_pending} 道题</b>
            <span class="small muted">把它们改对，才算真的学会</span>
          </div>
          <div class="we-r">›</div>
        </div>` : ''}`;
  }

  function gamePlaying() {
    const q = G.round.questions[G.idx];
    return `
      <div class="sec-title"><h3>🎮 第 ${G.idx + 1} / ${G.round.questions.length} 题</h3>
        <span class="hint">剩余 ${G.left} 秒</span></div>
      <div class="timer-wrap"><i style="width:${G.left / G.round.time_limit * 100}%"></i></div>
      <div class="card">
        <div class="game-q"><div class="expr">${q.a} ${q.op} ${q.b} = ?</div></div>
        <div class="game-ans" id="gAns">${G.answers[G.idx] == null ? '?' : G.answers[G.idx]}</div>
        <div class="numpad">
          ${[1,2,3,4,5,6,7,8,9].map(n => `<button data-act="g-num" data-n="${n}">${n}</button>`).join('')}
          <button data-act="g-del">⌫</button>
          <button data-act="g-num" data-n="0">0</button>
          <button class="btn" style="padding:15px 0" data-act="g-next">${G.idx === G.round.questions.length - 1 ? '交卷' : '下一题'}</button>
        </div>
      </div>`;
  }

  /* ------------------------------------------------ 错题本 */
  const WB = { items: null, mode: 'list', res: null };  // list / review / result

  function wrong(d) {
    if (!d) return `<div class="card">${emptyBox('正在加载错题本…')}</div>`;

    if (WB.mode === 'review' && WB.items) return wrongReview();
    if (WB.mode === 'result' && WB.res) return wrongResult();

    const due = d.review || [];
    const subs = d.subjects || [];
    const list = d.filtered || d.list;
    const total = d.total_pending || 0;

    if (!d.list.length) {
      return `
        <div class="sec-title"><h3>📕 错题本</h3></div>
        <div class="card" style="text-align:center;padding:26px 16px">
          <div style="font-size:52px">🌟</div>
          <h3 style="margin:8px 0 4px">错题本是空的！</h3>
          <p class="muted small">做错过的题目会收进这里，搞懂了它就消失啦</p>
        </div>`;
    }

    return `
      <div class="sec-title"><h3>📕 错题本</h3><span class="hint">今天到期 ${due.length} 道 · 还有 ${total} 道没掌握</span></div>

      <div class="card" style="text-align:center;background:var(--gold-soft)">
        <div style="font-size:44px">${due.length ? '🧠' : '🎉'}</div>
        <div class="stat-row" style="margin-top:8px">
          <div class="s"><b>${due.length}</b><span>今天该复习</span></div>
          <div class="s"><b>${total}</b><span>还没掌握</span></div>
          <div class="s"><b>+${d.review_bonus}</b><span>全对奖励</span></div>
        </div>
        ${due.length
          ? `<button class="btn primary block lg" style="margin-top:14px" data-act="wb-start">
               开始订正这 ${due.length} 道
             </button>
             <p class="small muted" style="margin-top:6px">
               改完后选一选「会了 / 有点难 / 太简单」，系统会自己排下次再见它的时间
             </p>`
          : `<p class="small muted" style="margin-top:12px">${d.all_clear || '今天的都复习完啦，明天见！'}</p>`}
      </div>

      <div class="wb-toolbar" style="margin-top:14px">
        <select data-act="wb-subject">
          <option value="">📚 全部科目</option>
          ${subs.map(s => `<option value="${UI.esc(s.code)}" ${WB_FILTER.subject === s.code ? 'selected' : ''}>${s.icon} ${UI.esc(s.name)}</option>`).join('')}
        </select>
        <select data-act="wb-order">
          <option value="recent" ${WB_FILTER.order === 'recent' ? 'selected' : ''}>最近错的在前</option>
          <option value="times" ${WB_FILTER.order === 'times' ? 'selected' : ''}>错得多的在前</option>
          <option value="manual" ${WB_FILTER.order === 'manual' ? 'selected' : ''}>我排的顺序</option>
        </select>
      </div>

      <div class="card">
        <div class="row spread" style="margin-bottom:6px">
          <b>${list.length ? `共 ${list.length} 道` : '这个科目下还没有题'}</b>
          ${WB_FILTER.order === 'manual'
            ? `<button class="btn ghost sm" data-act="wb-renumber">按默认重排</button>` : ''}
        </div>
        ${list.length ? list.map((w, i) => wrongRow(w, i, list.length)).join('')
          : `<p class="small muted" style="text-align:center;padding:10px 0">换一个科目看看 ✨</p>`}
      </div>
    `;
  }

  function wrongRow(w, i, len) {
    const sub = UI.esc(w.subject_name || '');
    const meta = [];
    if (w.times_wrong > 1) meta.push(`错过 ${w.times_wrong} 次`);
    if (!w.mastered && w.due_date) meta.push(`${w.due_date} 再见它`);
    if (w.times_reviewed) meta.push(`复习过 ${w.times_reviewed} 次`);

    return `
      <div class="wq-item ${w.mastered ? 'ok' : ''}">
        <div class="wq-head">
          <div style="flex:1">
            <div class="qt">${UI.esc(w.question)} ${w.mastered ? '✅' : ''}</div>
            <div class="wq-meta">
              ${sub ? `<span class="tag-sub">${sub}</span> ` : ''}
              ${w.tag ? `<span class="tag-sub">${UI.esc(w.tag)}</span> ` : ''}
              ${meta.join(' · ')} <span style="color:#c9c2b6">${w.seq}</span>
            </div>
            <div class="wq-meta">
              你答：<b>${UI.esc(w.wrong_answer || '空')}</b> · 正确答案 <b>${UI.esc(w.correct_answer)}</b>
            </div>
            ${w.explain ? `<div class="wq-meta">💡 ${UI.esc(w.explain)}</div>` : ''}
          </div>
        </div>
        <div class="wq-acts">
          <button class="btn ghost xs" data-act="wb-move" data-id="${w.id}" data-dir="up" ${i === 0 ? 'disabled' : ''}>↑ 上移</button>
          <button class="btn ghost xs" data-act="wb-move" data-id="${w.id}" data-dir="down" ${i === len - 1 ? 'disabled' : ''}>↓ 下移</button>
          <button class="btn ghost xs" data-act="wb-edit" data-id="${w.id}">✏️ 改一改</button>
          <button class="btn ghost xs" data-act="wb-variant" data-id="${w.id}">🔁 同类练一练</button>
          ${w.mastered
            ? `<button class="btn ghost xs" data-act="wb-forget" data-id="${w.id}">再放回错题本</button>`
            : `<button class="btn ghost xs" data-act="wb-rate" data-id="${w.id}" data-r="easy">😎 我已经很会了</button>`}
        </div>
      </div>`;
  }

  function wrongResult() {
    const r = WB.res;
    return `
      <div class="sec-title"><h3>🧠 订正结果</h3>
        <button class="btn sm ghost" data-act="wb-quit">完成</button></div>
      <div class="card" style="text-align:center">
        <div style="font-size:46px">${r.all_correct ? '🏆' : '💪'}</div>
        <h3 style="margin:6px 0 2px">${r.right} / ${r.total} 改对了</h3>
        <p class="small muted">${UI.esc(r.note || '')}</p>
        ${r.points ? `<p class="small" style="color:#2E9E63;font-weight:800;margin-top:6px">+${r.points} 颗星星币</p>` : ''}
        <p class="small muted" style="margin-top:4px">下次复习：${UI.esc(r.next_due || '')}</p>
      </div>
      ${r.results.map(it => `
        <div class="card" style="margin-top:10px">
          <div class="qt">${it.correct ? '✅' : '❌'} ${UI.esc(it.question)}</div>
          <div class="wq-meta">
            ${it.correct ? `答案 ${UI.esc(it.answer)}` : `你写 ${UI.esc(it.your || '空')} · 正确答案 ${UI.esc(it.answer)}`}
          </div>
          <div class="wq-meta">${UI.esc(it.tip || '')} · ${it.next_gap} 天后再见它</div>
          ${it.correct ? `
          <div class="wq-acts">
            <button class="btn ghost xs" data-act="wb-rate" data-id="${it.id}" data-r="hard">😅 刚才有点蒙</button>
            <button class="btn ghost xs" data-act="wb-rate" data-id="${it.id}" data-r="easy">😎 太简单啦</button>
          </div>` : ''}
        </div>`).join('')}
    `;
  }

  function wrongReview() {
    const items = WB.items;
    const i = WB.idx;
    const it = items[i];
    return `
      <div class="sec-title"><h3>🧠 订正第 ${i + 1} / ${items.length} 题</h3>
        <button class="btn sm ghost" data-act="wb-quit">退出</button></div>
      <div class="timer-wrap"><i style="width:${(i + 1) / items.length * 100}%"></i></div>
      <div class="card">
        <div class="game-q"><div class="expr">${UI.esc(it.question.replace(' = ?', ''))} = ?</div></div>
        <p class="small muted" style="text-align:center;margin-top:6px">
          上次你写的是 <b>${UI.esc(it.wrong_answer || '（没填）')}</b>，正确答案是 <b>${UI.esc(it.correct_answer)}</b>
        </p>
        <div class="game-ans" id="gAns">${WB.answers[i] == null ? '?' : WB.answers[i]}</div>
        <div class="numpad">
          ${[1,2,3,4,5,6,7,8,9].map(n => `<button data-act="wb-num" data-n="${n}">${n}</button>`).join('')}
          <button data-act="wb-del">⌫</button>
          <button data-act="wb-num" data-n="0">0</button>
          <button class="btn" style="padding:15px 0" data-act="wb-next">${i === items.length - 1 ? '交卷' : '下一题'}</button>
        </div>
      </div>`;
  }

  /* ================================================================
     星星花园
     浇水不给星，只有收成才给 —— 这条规则写在这里也写在服务端，
     前端只是展示，改掉前端代码不会多拿到一颗星。
     ================================================================ */
  let GTIMER = null;

  function garden(d) {
    if (!d) return `<div class="card">${emptyBox('正在打理花园…')}</div>`;
    if (!d.enabled) return `<div class="card">${emptyBox('花园没有开启 🌱')}</div>`;

    startCountdown();
    return `
      <div class="sec-title"><h3>🌱 星星花园</h3>
        <span class="hint">可用 ${d.coins.available} 星 · ${d.slot_total} 块地</span></div>
      <div class="card soft-tip">${UI.esc(d.tip)}</div>

      <div class="plot-grid">
        ${d.plots.map(plotCard).join('')}
        ${Array.from({ length: Math.min(2, d.slot_locked || 0) }).map(() => `
          <div class="plot locked"><div class="pe">🔒</div>
            <div class="small muted">升级后解锁</div></div>`).join('')}
      </div>

      <p class="small muted" style="margin-top:10px">
        每次浇水要隔 ${d.cooldown_min} 分钟 · 收成约为种子价的 ${Math.round(d.yield_rate * 100)}%<br>
        ${UI.esc(d.next_slot_hint)}
      </p>`;
  }

  function plotCard(p) {
    if (p.empty) {
      return `<div class="plot empty">
        <div class="pe">🟫</div>
        <div class="small muted">空地</div>
        <button class="btn ghost sm" data-act="gd-plant" data-slot="${p.slot}">种点什么</button>
      </div>`;
    }
    const pct = Math.min(100, Math.round(p.water_count / p.water_needed * 100));
    return `<div class="plot ${p.status}">
      <div class="pe big">${p.stage_emoji}${p.droopy ? '🥀' : ''}</div>
      <div class="nm">${UI.esc(p.name)}</div>
      ${p.can_harvest
        ? `<div class="small g">熟啦！</div>
           <button class="btn primary sm" data-act="gd-harvest" data-slot="${p.slot}">收获 +${p.yield_coin}</button>`
        : `<div class="bar grow"><i style="width:${pct}%"></i></div>
           <div class="small muted">浇水 ${p.water_count}/${p.water_needed}</div>
           ${p.can_water
             ? `<button class="btn ghost sm" data-act="gd-water" data-slot="${p.slot}">💧 浇水</button>`
             : `<button class="btn ghost sm" disabled data-sec="${p.wait_minutes * 60}"
                 data-cd="1">⏳ <span class="cd">${cdText(p.wait_minutes * 60)}</span></button>`}
          `}
    </div>`;
  }

  function cdText(sec) {
    sec = Math.max(0, sec | 0);
    if (sec >= 3600) return Math.ceil(sec / 3600) + ' 小时';
    if (sec >= 60) return Math.ceil(sec / 60) + ' 分';
    return sec + ' 秒';
  }

  /** 统一的倒计时：所有带 data-sec 的元素按秒递减，到 0 触发一次刷新 */
  function startCountdown() {
    clearInterval(GTIMER);
    GTIMER = setInterval(() => {
      const nodes = [...document.querySelectorAll('[data-sec]')];
      if (!nodes.length) { clearInterval(GTIMER); return; }
      nodes.forEach(n => {
        let v = +n.dataset.sec - 1;
        if (v < 0) v = 0;
        n.dataset.sec = v;
        const t = n.classList.contains('cd') ? n : n.querySelector('.cd');
        if (t) t.textContent = cdText(v);
        if (v <= 0 && n.dataset.cd) {
          n.dataset.cd = '';          // 只触发一次刷新，避免倒计时归零后反复请求
          clearInterval(GTIMER);
          App.load();
        }
      });
    }, 1000);
  }

  /* ================================================================
     番茄钟 / 专注
     倒计时只在前端显示，判卷在服务端按真实时间差算。
     ================================================================ */
  const PM = { minutes: null };

  function focus(d) {
    if (!d) return `<div class="card">${emptyBox('正在准备番茄钟…')}</div>`;
    if (!d.enabled) return `<div class="card">${emptyBox('番茄钟没有开启 🍅')}</div>`;

    if (d.running) {
      const r = d.running;
      startCountdown();
      const pct = Math.max(0, Math.min(100,
        100 - r.remain_seconds / (r.plan_minutes * 60) * 100));
      return `
        <div class="sec-title"><h3>🍅 正在专注</h3><span class="hint">${UI.esc(r.topic)}</span></div>
        <div class="card pomo-run">
          <div class="ring"><span class="cd" data-sec="${r.remain_seconds}" data-cd="1">${fmt(r.remain_seconds)}</span></div>
          <div class="bar grow" style="margin-top:12px"><i style="width:${pct}%"></i></div>
          <p class="small muted" style="margin-top:10px">
            ${UI.esc(r.topic)} · 计划 ${r.plan_minutes} 分钟 · 手机放到一边哦
          </p>
          <div class="row" style="gap:8px;margin-top:12px">
            <button class="btn ghost lg" style="flex:1" data-act="pm-abort" data-id="${r.id}">实在坚持不住</button>
            <button class="btn primary lg" style="flex:1" data-act="pm-finish" data-id="${r.id}">我专注完啦</button>
          </div>
        </div>`;
    }

    return `
      <div class="sec-title"><h3>🍅 专注番茄</h3>
        <span class="hint">今天 ${d.today_used}/${d.limit} 个</span></div>
      <div class="card" style="text-align:center">
        <div style="font-size:56px">🍅</div>
        <h3 style="margin:6px 0 4px">专心做一件事</h3>
        <p class="muted small">时间到了点「我专注完啦」，${d.points_per_pomodoro} 星就到账</p>
        <div class="stat-row" style="margin-top:14px">
          <div class="s"><b>${d.today_valid}</b><span>今天有效</span></div>
          <div class="s"><b>${d.today_left}</b><span>还剩几个</span></div>
          <div class="s"><b>+${d.bonus_points}</b><span>第${d.bonus_at}个额外</span></div>
        </div>
      </div>

      <div class="sec-title"><h3>⏱ 选一段时长</h3></div>
      <div class="card">
        <label class="f"><span>这段专注时间里我要做什么</span>
          <input id="pmTopic" placeholder="比如：写数学作业" value="写今天的作业"></label>
        <div class="min-chips">
          ${d.minutes_options.map(m => `
            <button class="chip ${m === d.default_minutes ? 'on' : ''}"
              data-act="pm-pick" data-m="${m}">${m} 分钟</button>`).join('')}
        </div>
        <button class="btn primary block lg" style="margin-top:14px" data-act="pm-start">开始专注</button>
        <p class="small muted" style="margin-top:8px">${UI.esc(d.tip)}</p>
      </div>

      ${d.history.length ? `
        <div class="sec-title"><h3>📖 今天的专注</h3></div>
        <div class="card">
          ${d.history.map(h => `
            <div class="row spread" style="padding:6px 0;border-bottom:1px dashed var(--line)">
              <span>${UI.esc(h.topic)} <span class="small muted">${h.started_at} · ${h.actual_minutes} 分钟</span></span>
              <b class="${h.valid ? 'plus' : 'muted'}">${h.valid ? '+' + h.points + ' 星' : '未计入'}</b>
            </div>`).join('')}
        </div>` : ''}`;
  }

  function fmt(sec) {
    sec = Math.max(0, sec | 0);
    const m = String(Math.floor(sec / 60)).padStart(2, '0');
    const s = String(sec % 60).padStart(2, '0');
    return m + ':' + s;
  }

  /* ================================================================
     每日识字 + 识字闯关
     ================================================================ */
  const W = { round: null, idx: 0, answers: [], t0: 0, mode: 'cards' };

  function word(d) {
    if (!d) return `<div class="card">${emptyBox('正在准备今天的小课堂…')}</div>`;
    if (W.round) return wordPlaying();

    if (W.mode === 'quiz') return wordQuizIntro();

    return `
      <div class="sec-title"><h3>📖 每日识字</h3>
        <span class="hint">认识 ${d.known_count}/${d.total_chars} 字</span></div>
      <div class="card">
        <div class="row spread"><b>识字进度</b><span class="small muted">${d.percent}%</span></div>
        <div class="bar exp" style="margin-top:8px"><i style="width:${Math.max(2, d.percent)}%"></i></div>
        <p class="small muted" style="margin-top:8px">${UI.esc(d.note)}</p>
      </div>

      <div class="sec-title"><h3>✨ 今天的新字</h3><span class="hint">每天 ${d.per_day} 个</span></div>
      ${d.new.length
        ? `<div class="hanzi-grid">${d.new.map(hanziCard).join('')}</div>`
        : `<div class="card">${emptyBox('太厉害了，词库里的字都认识啦 🎉')}</div>`}

      ${d.review.length ? `
        <div class="sec-title"><h3>🔁 再看看</h3><span class="hint">上次没记住的</span></div>
        <div class="hanzi-grid">${d.review.map(hanziCard).join('')}</div>` : ''}

      <div class="card wrong-entry" data-act="w-quiz" style="margin-top:12px">
        <div class="we-l"><div style="font-size:26px">🎯</div></div>
        <div class="we-c"><b>识字闯关</b>
          <span class="small muted">看拼音选汉字、看单词选意思</span></div>
        <div class="we-r">›</div>
      </div>`;
  }

  function hanziCard(h) {
    return `
      <div class="hanzi-card">
        <div class="hz">${UI.esc(h.char)}</div>
        <div class="py">${UI.esc(h.pinyin)}</div>
        <div class="wd">${UI.esc(h.word)}</div>
        <div class="small muted">${UI.esc(h.mean)}</div>
        <div class="row" style="gap:6px;margin-top:8px">
          <button class="btn ghost sm" style="flex:1" data-act="w-mark"
            data-k="${UI.esc(h.char)}" data-v="0">还没记住</button>
          <button class="btn primary sm" style="flex:1" data-act="w-mark"
            data-k="${UI.esc(h.char)}" data-v="1">我认识</button>
        </div>
      </div>`;
  }

  function wordQuizIntro() {
    return `
      <div class="savebar">
        <button class="btn ghost sm" data-act="w-mode" data-v="cards">‹ 返回</button>
        <div style="flex:1;text-align:center;font-weight:800">🎯 识字闯关</div>
        <div style="width:44px"></div>
      </div>
      <div class="card" style="text-align:center">
        <div style="font-size:56px">🎯</div>
        <h3 style="margin:6px 0 4px">看拼音、认汉字、选意思</h3>
        <p class="muted small">答错的字会自动进错题本，明天还会来找你</p>
        <button class="btn primary block lg" style="margin-top:14px" data-act="w-start">开始闯关</button>
      </div>
      <button class="btn ghost block sm" style="margin-top:10px" data-act="w-mode" data-v="cards">返回每日识字</button>`;
  }

  function wordPlaying() {
    const q = W.round.questions[W.idx];
    const hint = { pinyin: '选出正确的读音', hanzi: '选出正确的汉字',
                   en2zh: '它的中文意思是？', zh2en: '它的英文单词是？' }[q.kind] || '';
    return `
      <div class="savebar">
        <button class="btn ghost sm" data-act="w-quit">‹ 退出</button>
        <div style="flex:1;text-align:center;font-weight:800">第 ${W.idx + 1} / ${W.round.questions.length} 题</div>
        <div style="width:44px"></div>
      </div>
      <div class="card quiz">
        <div class="q-prompt">${UI.esc(q.prompt)}</div>
        <div class="small muted">${UI.esc(hint)}</div>
        <div class="opts">
          ${q.options.map(o => `
            <button class="opt ${W.answers[W.idx] === o ? 'on' : ''}"
              data-act="w-opt" data-v="${UI.esc(o)}">${UI.esc(o)}</button>`).join('')}
        </div>
        <button class="btn primary block lg" style="margin-top:14px" data-act="w-next"
          ${W.answers[W.idx] == null ? 'disabled' : ''}>
          ${W.idx === W.round.questions.length - 1 ? '交卷' : '下一题'}
        </button>
      </div>`;
  }

  /* ================================================================
     宠物（纯矢量 SVG，不依赖任何图片）
     ================================================================ */
  function pet(d) {
    if (!d) return `<div class="card">${emptyBox('正在找小伙伴…')}</div>`;
    if (!d.has_pet) return petAdopt(d);

    return `
      <div class="sec-title"><h3>🐾 ${UI.esc(d.name)}</h3>
        <span class="hint">${UI.esc(d.stage_name)} · 认识第 ${d.adopted_days} 天</span></div>
      <div class="card pet-card">
        <div class="pet-stage">${petSvg(d.species, d.stage, d.mood)}</div>
        <div class="bubble">${UI.esc(d.say)}</div>
        <div class="row spread" style="margin-top:10px">
          <span class="small muted">心情 ${d.mood_word}</span>
          <span class="small muted">${d.mood}/100</span>
        </div>
        <div class="bar mood"><i style="width:${d.mood}%"></i></div>
      </div>

      <div class="card">
        <div class="stat-row">
          <div class="s"><b>${UI.esc(d.stage_name)}</b><span>当前形态</span></div>
          <div class="s"><b>${d.exp}</b><span>你的成长值</span></div>
          <div class="s"><b>${d.bond}</b><span>亲密度</span></div>
        </div>
        <p class="small muted" style="margin-top:8px">
          ${d.max_stage
            ? '已经是最终形态啦，它跟着你一路长大 🌟'
            : `再攒 ${d.to_next} 点成长值，它就会变成下一种形态`}
        </p>
        <p class="small muted">${UI.esc(d.species_line)}</p>
      </div>

      <div class="grid2">
        <button class="btn primary lg" data-act="pt-feed"
          ${d.feed_left <= 0 ? 'disabled' : ''}>🍚 喂食 · ${d.feed_cost} 星</button>
        <button class="btn ghost lg" data-act="pt-play"
          ${d.play_left <= 0 ? 'disabled' : ''}>🎾 陪它玩</button>
      </div>
      <p class="small muted" style="margin-top:8px">
        今天还能喂 ${d.feed_left} 次、玩 ${d.play_left} 次 ·
        它的等级跟着你的成长值走，喂东西是喂不大的 —— 你好好努力，它就长得快
      </p>`;
  }

  function petAdopt(d) {
    return `
      <div class="sec-title"><h3>🐾 领养一个小伙伴</h3></div>
      <div class="card" style="text-align:center">
        <div style="font-size:56px">🥚</div>
        <h3 style="margin:6px 0 4px">它会陪你一起长大</h3>
        <p class="muted small">它的等级跟着你的成长值走 —— 你好好努力，它就长得快</p>
      </div>
      <div class="tool-grid">
        ${d.species.map(s => `
          <button class="tool" data-act="pt-adopt" data-sp="${s.code}">
            <span class="ti">${s.emoji}</span>
            <b>${UI.esc(s.name)}</b>
            <span class="small muted">${UI.esc(s.line)}</span>
          </button>`).join('')}
      </div>
      <p class="small muted" style="margin-top:10px">领养不需要花星星币。</p>`;
  }

  /** 纯 SVG 绘制：一只蛋里的小家伙，随形态变大、随心情变表情 */
  function petSvg(species, stage, mood) {
    const pal = {
      dragon: ['#8ed081', '#5fae55', '#ffd3d3'],
      cat: ['#ffd166', '#f0a03c', '#ffe8cf'],
      owl: ['#b3aef0', '#8a83dd', '#f7e2a8'],
      penguin: ['#7fd0f5', '#4a97ce', '#ffe0a3'],
    }[species] || ['#8ed081', '#5fae55', '#ffd3d3'];

    const [c1, c2, c3] = pal;
    const s = 0.52 + Math.min(4, stage) * 0.12;
    const happy = mood >= 60, sad = mood < 40;
    const eyeY = -6;
    const eye = `
      <ellipse cx="-13" cy="${eyeY}" rx="5.4" ry="${happy ? 6.2 : 5}" fill="#fff"/>
      <ellipse cx="13"  cy="${eyeY}" rx="5.4" ry="${happy ? 6.2 : 5}" fill="#fff"/>
      <circle cx="-13" cy="${eyeY + 1}" r="2.6" fill="#2d3142"/>
      <circle cx="13"  cy="${eyeY + 1}" r="2.6" fill="#2d3142"/>`;
    const mouth = happy
      ? `<path d="M -7 6 Q 0 13 7 6" stroke="#2d3142" stroke-width="2.4" fill="none" stroke-linecap="round"/>`
      : sad
        ? `<path d="M -7 11 Q 0 5 7 11" stroke="#2d3142" stroke-width="2.4" fill="none" stroke-linecap="round"/>`
        : `<path d="M -6 9 L 6 9" stroke="#2d3142" stroke-width="2.4" stroke-linecap="round"/>`;

    let extra = '';
    if (species === 'dragon') {
      extra = `
        <path d="M -26 -26 L -32 -44 L -18 -34 Z" fill="${c2}"/>
        <path d="M 26 -26 L 32 -44 L 18 -34 Z" fill="${c2}"/>
        <path d="M -34 -6 q -14 6 0 16 q 6 -10 -0 -16 Z" fill="${c2}"/>`;
    } else if (species === 'cat') {
      extra = `
        <path d="M -28 -24 L -34 -46 L -14 -32 Z" fill="${c2}"/>
        <path d="M 28 -24 L 34 -46 L 14 -32 Z" fill="${c2}"/>`;
    } else if (species === 'owl') {
      extra = `
        <path d="M -30 -18 q 10 -22 20 -22 q -4 14 0 22 Z" fill="${c2}"/>
        <path d="M 30 -18 q -10 -22 -20 -22 q 4 14 0 22 Z" fill="${c2}"/>
        <path d="M -6 4 l 6 8 l 6 -8 Z" fill="${c3}"/>`;
    } else {
      extra = `<path d="M -22 8 q 22 18 44 0 q -10 22 -22 22 q -12 0 -22 -22 Z" fill="#fff" opacity=".85"/>`;
    }

    const body = `
      <g transform="translate(100 112) scale(${s.toFixed(2)})">
        <ellipse cx="0" cy="52" rx="34" ry="9" fill="#000" opacity=".08"/>
        <ellipse cx="-14" cy="46" rx="11" ry="7" fill="${c2}"/>
        <ellipse cx="14" cy="46" rx="11" ry="7" fill="${c2}"/>
        <ellipse cx="0" cy="4" rx="38" ry="42" fill="${c1}"/>
        <ellipse cx="0" cy="14" rx="26" ry="28" fill="#fff" opacity=".55"/>
        ${extra}
        <ellipse cx="-30" cy="8" rx="9" ry="13" fill="${c2}" transform="rotate(-18 -30 8)"/>
        <ellipse cx="30" cy="8" rx="9" ry="13" fill="${c2}" transform="rotate(18 30 8)"/>
        <circle cx="0" cy="-2" r="30" fill="${c1}"/>
        ${eye}${mouth}
        ${stage >= 3 ? `<path d="M -30 -22 q 30 -18 60 0 q -14 10 -30 10 q -16 0 -30 -10 Z" fill="${c2}"/>` : ''}
        ${stage >= 4 ? `<circle cx="0" cy="-38" r="6" fill="#ffd166" stroke="#fff" stroke-width="2"/>` : ''}
      </g>`;

    const egg = `
      <g opacity=".95">
        <path d="M 100 26 C 132 26 150 66 150 104 C 150 146 128 180 100 180
                 C 72 180 50 146 50 104 C 50 66 68 26 100 26 Z" fill="#f6efe2" stroke="#e3d7c2" stroke-width="3"/>
        <path d="M 62 96 l 12 -8 l -8 12 l 12 2 l -10 10" stroke="#d9c9ad" stroke-width="3" fill="none"/>
        <ellipse cx="100" cy="168" rx="42" ry="8" fill="#000" opacity=".06"/>
      </g>`;

    return `<svg viewBox="0 0 200 200" width="100%" height="180" role="img">
      <defs><radialGradient id="pg" cx="50%" cy="40%">
        <stop offset="0%" stop-color="#fff" stop-opacity=".9"/>
        <stop offset="100%" stop-color="#fff" stop-opacity="0"/></radialGradient></defs>
      <rect width="200" height="200" rx="24" fill="url(#pg)"/>
      ${stage === 0 ? egg : ''}
      ${stage === 0 ? `<g transform="translate(0 18) scale(.8) translate(25 0)">${body}</g>` : body}
    </svg>`;
  }

  /* ================================================================
     家庭共学（孩子端）
     ================================================================ */
  function family(d) {
    if (!d) return `<div class="card">${emptyBox('正在看看今天的陪伴…')}</div>`;
    return `
      <div class="sec-title"><h3>👨‍👩‍👧 一起长大的时间</h3></div>
      <div class="card">
        <div class="stat-row">
          <div class="s"><b>${d.today_minutes}</b><span>今天（分钟）</span></div>
          <div class="s"><b>${d.week_minutes}</b><span>近 7 天</span></div>
          <div class="s"><b>${d.count}</b><span>次数</span></div>
        </div>
        ${d.note ? `<p class="small muted" style="margin-top:10px">${UI.esc(d.note)}</p>` : ''}
      </div>

      <div class="sec-title"><h3>📚 都一起做了什么</h3></div>
      ${d.records.length
        ? `<div class="card">
            ${d.records.map(r => `
              <div class="row spread" style="padding:7px 0;border-bottom:1px dashed var(--line)">
                <div class="row" style="gap:8px">
                  <span style="font-size:20px">${r.kind_emoji}</span>
                  <div><div style="font-weight:700">${UI.esc(r.kind_name)}</div>
                    <div class="small muted">${r.date} · 和${UI.esc(r.parent)}</div>
                    ${r.note ? `<div class="small muted">${UI.esc(r.note)}</div>` : ''}</div>
                </div>
                <b>${r.minutes} 分</b>
              </div>`).join('')}
           </div>`
        : `<div class="card">${emptyBox('还没有记录。今天可以拉着爸爸妈妈读一本书 📖')}</div>`}`;
  }

  /* ------------------------------------------------ 我的 */
  function me(d) {
    const m = d.profile, lv = d.level_now;
    return `
      <div class="sec-title"><h3>🏅 我的等级</h3><span class="hint">成长值 ${m.exp_total}</span></div>
      <div class="card">
        <div class="row spread">
          <div class="row">
            <div class="ava" style="width:46px;height:46px;border-radius:50%;background:var(--gold-soft);display:grid;place-items:center;font-size:26px">${UI.avatar(m.avatar)}</div>
            <div><div style="font-weight:800">${UI.esc(m.name)}</div>
              <div class="small muted">Lv${m.level} ${UI.esc(m.title)}</div>
              <button class="btn ghost xs" style="margin-top:5px" data-act="me-avatar">🎨 换个头像</button>
            </div>
          </div>
          <span class="tag">累计成长值 ${m.exp_total}</span>
        </div>
        ${lv.max_level ? `<p class="small muted" style="margin-top:10px">已经是最高等级啦 🌟</p>` : `
        <div class="bar exp" style="margin-top:12px"><i style="width:${lv.percent}%"></i></div>
        <div class="row spread"><span class="small muted">距 Lv${lv.next_level} ${UI.esc(lv.next_title)} 还差 ${lv.to_next}</span>
          <span class="small muted">${lv.percent}%</span></div>
        <div class="small muted" style="margin-top:6px">🎁 下一级解锁：${UI.esc(lv.next_perk || '')}</div>`}
      </div>

      <div class="sec-title"><h3>🎖️ 等级特权</h3></div>
      <div class="card">
        ${d.levels.map(l => `
          <div class="lv-item ${l.level > m.level ? 'off' : ''}">
            <div class="bn">Lv${l.level}</div>
            <div style="flex:1">
              <div style="font-weight:700">${UI.esc(l.title)} <span class="small muted">${l.exp} 成长值</span></div>
              <div class="small muted">${UI.esc(l.perk || '')}</div>
            </div>
            ${l.level <= m.level ? '<span class="tag g">已解锁</span>' : ''}
          </div>`).join('')}
      </div>

      <div class="sec-title"><h3>🎓 荣誉证书</h3></div>
      <div class="card">
        <div class="row spread">
          <div><div style="font-weight:700">${UI.esc(m.name)} · Lv${m.level} ${UI.esc(m.title)}</div>
            <div class="small muted">打印出来贴在墙上，或截图发给家人</div></div>
          <button class="btn ghost sm" data-act="certificate">查看证书</button>
        </div>
      </div>

      ${titleCard(d)}

      <div class="sec-title"><h3>🏆 徽章墙</h3>
        <span class="hint">${gotCount(d.achievement_wall)} / ${(d.achievement_wall || []).length} 已点亮</span></div>
      <div class="card">
        ${badgeWall(d.achievement_wall)}
      </div>

      <div class="cols">
        <div>
          <div class="sec-title"><h3>⭐ 已实现的愿望</h3></div>
          <div class="card">
            ${d.wish_done.length ? d.wish_done.map(w => `
              <div class="row spread" style="padding:7px 0;border-bottom:1px dashed var(--line)">
                <div class="row"><span style="font-size:22px">🎁</span>
                  <div><div style="font-weight:700">${UI.esc(w.title)}</div>
                    <div class="small muted">${w.at} · ${w.cost} 星</div></div></div>
              </div>`).join('') : emptyBox('还没有实现的愿望')}
          </div>
        </div>
        <div>
          <div class="sec-title"><h3>📜 星星明细</h3></div>
          <div class="card">
            ${d.ledger.length ? d.ledger.map(r => `
              <div class="ledger-row">
                <div><div>${UI.esc(r.note || '')}</div>
                  <div class="small muted">${r.date} · ${sourceName(r.source_type)}</div></div>
                <div class="${r.delta_coin >= 0 ? 'plus' : 'minus'}">${r.delta_coin >= 0 ? '+' : ''}${r.delta_coin}</div>
              </div>`).join('') : emptyBox('还没有记录')}
          </div>
        </div>
      </div>

      <button class="btn ghost block lg" style="margin-top:14px" data-act="logout">退出登录</button>`;
  }

  function gotCount(wall) {
    return (wall || []).filter(a => a.got).length;
  }

  function titleCard(d) {
    const owned = (d.achievement_wall || []).filter(a => a.got);
    const cur = d.display_title_code || '';
    return `
      <div class="sec-title"><h3>🎖️ 我的称号</h3>
        <span class="hint">挑一个挂在名字旁边</span></div>
      <div class="card">
        <div class="row spread">
          <div class="row">
            <div style="font-size:22px">${cur ? '✨' : '—'}</div>
            <div><div style="font-weight:700">${UI.esc(d.display_title || '暂未选择')}</div>
              <div class="small muted">${cur ? '这就是别人看到你的样子' : '拿到称号后就能挂出来啦'}</div></div>
          </div>
          <button class="btn ghost sm" data-act="pick-title" ${owned.length ? '' : 'disabled'}>
            选择称号</button>
        </div>
        ${owned.length ? '' : '<p class="small muted" style="margin-top:8px">完成徽章墙上的挑战，就会有称号可以挂。</p>'}
      </div>`;
  }

  function badgeWall(wall) {
    if (!wall || !wall.length) return emptyBox('还没有称号，继续加油');
    return `<div class="badge-wall">${wall.map(a => `
      <div class="badge ${a.got ? '' : 'locked'}">
        <div class="bi">${a.got ? a.icon : '🔒'}</div>
        <div class="bn2">${UI.esc(a.name)}</div>
        ${a.got
          ? `<div class="small muted">${a.got_at} 获得</div>`
          : `<div class="bar sm" style="margin-top:5px"><i style="width:${a.percent}%"></i></div>
             <div class="small muted">${a.current} / ${a.target} · ${a.hint}</div>`}
        ${a.desc ? `<div class="small muted bd">${UI.esc(a.desc)}</div>` : ''}
      </div>`).join('')}</div>`;
  }

  function sourceName(s) {
    return { task: '任务', application: '申请加分', game: '小游戏', streak: '连续打卡',
             manual: '爸妈奖励', redeem: '兑换愿望' }[s] || s;
  }

  function certHTML(c) {
    const achv = (c.achievements || []).slice(0, 6);
    return `
      <div class="cert-overlay" id="certOverlay">
        <div class="cert-actions cert-no-print">
          <button class="btn primary sm" data-act="cert-print">🖨 打印 / 存成 PDF</button>
          <button class="btn ghost sm" data-act="cert-close">关闭</button>
        </div>
        <div class="cert-paper">
          <div class="cert-frame">
            <div class="cert-head">
              <div class="cert-star">${UI.avatar(c.avatar, 60)}</div>
              <div class="cert-kicker">星星成长记</div>
              <h2 class="cert-title">荣 誉 证 书</h2>
              <div class="cert-sub">Certificate of Growth</div>
            </div>
            <p class="cert-line">兹证明</p>
            <div class="cert-name">${UI.esc(c.name)}</div>
            <p class="cert-body">
              凭借日复一日的坚持，已达 <b>Lv${c.level} ${UI.esc(c.title)}</b>，
              累计成长值 <b>${c.exp}</b>，连续打卡 <b>${c.streak_days}</b> 天。
            </p>
            <div class="cert-grid">
              <div class="cert-cell"><div class="cv">${c.level}</div><div class="ck">当前等级</div></div>
              <div class="cert-cell"><div class="cv">${c.exp}</div><div class="ck">成长值</div></div>
              <div class="cert-cell"><div class="cv">${c.streak_days}</div><div class="ck">连续打卡</div></div>
              <div class="cert-cell"><div class="cv">${(c.wishes_done || []).length}</div><div class="ck">实现愿望</div></div>
            </div>
            ${achv.length ? `
              <div class="cert-achv">
                ${achv.map(a => `<span class="cert-chip">${a.icon} ${UI.esc(a.name)}</span>`).join('')}
              </div>` : ''}
            ${(c.wishes_done || []).length ? `
              <div class="cert-wish">
                <div class="small muted">已经实现的愿望</div>
                ${c.wishes_done.slice(0, 4).map(w =>
                  `<div class="cert-wish-row">🎁 ${UI.esc(w.title)} <span class="muted">${w.at} · ${w.cost} 星</span></div>`
                ).join('')}
              </div>` : ''}
            <div class="cert-foot">
              <div>颁发日期 ${c.issued_at}</div>
              <div class="muted">编号 ${UI.esc(c.serial)}</div>
            </div>
          </div>
        </div>
        <p class="cert-tip cert-no-print small muted">手机上可以直接截图保存，电脑上点打印即可存成 PDF。</p>
      </div>`;
  }

  /* ------------------------------------------------ 交互 */
  const actions = {
    async 'checkin'(el) {
      const need = el.dataset.need === '1';
      const tplId = el.dataset.id;
      const nm = el.dataset.nm;
      UI.sheet({
        title: '打卡 · ' + UI.esc(nm),
        body: `
          <label class="f"><span>说点什么（可选）</span><textarea id="evText" placeholder="我今天完成了…"></textarea></label>
          <div class="row spread">
            <span class="small muted">${need ? '这个任务需要拍张照片 📷' : '可以拍张照片留念'}</span>
            <button class="btn ghost sm" data-act="pick-photo">📷 拍照</button>
          </div>
          <div id="evPreview" style="margin-top:8px"></div>
          <input type="hidden" id="evImg">`,
        okText: '提交打卡',
        onOk: async (wrap) => {
          const text = wrap.querySelector('#evText').value.trim();
          const img = wrap.querySelector('#evImg').value;
          if (need && !img) { UI.toast('这个任务要拍照哦', 'err'); return false; }
          try {
            const r = await API.post('/api/child/checkin',
              { template_id: +tplId, evidence_text: text, evidence_image: img });
            UI.toast(r.status === 'approved' ? `已到账 +${r.points} 星 ⭐` : '已提交，等爸爸妈妈确认');
            if (r.streak_bonus) setTimeout(() => UI.celebrate('🔥', `连续打卡奖励 +${r.streak_bonus}`, '坚持就是力量'), 400);
            App.load();
          } catch (e) { UI.toast(e.message, 'err'); }
        }
      });
    },

    'pick-photo'() {
      UI.pickImage((url) => {
        const wrap = document.querySelector('.sheet');
        if (!wrap) return;
        wrap.querySelector('#evImg').value = url;
        wrap.querySelector('#evPreview').innerHTML =
          `<img src="${url}" style="width:100%;border-radius:12px">`;
        UI.toast('照片已添加');
      });
    },

    'wish-new'() {
      UI.sheet({
        title: '许下一个愿望',
        body: `
          <label class="f"><span>我想实现什么</span><input id="wTitle" placeholder="比如：乐高城市系列"></label>
          <div class="row" style="gap:8px;align-items:flex-start;margin:10px 0;background:var(--bg);border-radius:12px;padding:10px 12px">
            <span style="font-size:18px;line-height:1.3">⭐</span>
            <div class="small muted">需要多少星星币，由爸爸妈妈来定。<br>你只要说清楚想要什么就好。</div>
          </div>
          <label class="f"><span>备注（可选）</span><textarea id="wNote" placeholder="为什么想要它？"></textarea></label>
          <div class="row spread">
            <span class="small muted">配图（可选）</span>
            <button class="btn ghost sm" data-act="wish-photo">📷 上传照片</button>
          </div>
          <div id="wPreview" style="margin-top:8px"></div>
          <input type="hidden" id="wCover">
          <p class="small muted" style="margin-top:10px">许愿不需要花星星币。先有目标，再一点点攒。</p>`,
        okText: '许下愿望',
        onOk: async (wrap) => {
          const title = wrap.querySelector('#wTitle').value.trim();
          if (!title) { UI.toast('给它起个名字吧', 'err'); return false; }
          try {
            await API.post('/api/child/wish', {
              title,
              note: wrap.querySelector('#wNote').value.trim(),
              cover_image: wrap.querySelector('#wCover').value
            });
            UI.toast('愿望已许下，等爸爸妈妈确认 🌈');
            App.load();
          } catch (e) { UI.toast(e.message, 'err'); }
        }
      });
    },

    'wish-photo'() {
      UI.pickImage((url) => {
        const wrap = document.querySelector('.sheet');
        if (!wrap) return;
        wrap.querySelector('#wCover').value = url;
        wrap.querySelector('#wPreview').innerHTML = `<img src="${url}" style="width:100%;border-radius:12px">`;
      });
    },

    async 'wish-primary'(el) {
      await API.post(`/api/child/wish/${el.dataset.id}/primary`, {});
      UI.toast('已设为主目标');
      App.load();
    },

    async 'wish-drop'(el) {
      if (!await UI.confirm('放弃这个愿望？', '星星币不会减少，随时可以许新的愿望')) return;
      await API.del(`/api/child/wish/${el.dataset.id}`);
      UI.toast('已放弃，星星币还在账户里');
      App.load();
    },

    'wish-edit'(el) {
      const id = +el.dataset.id;
      // 从已加载的数据里取这条愿望，回填到编辑框
      const list = (App.state.child.wishes && App.state.child.wishes.wishes)
                || (App.state.child.home && App.state.child.home.wishes) || [];
      const w = list.find(x => x.id === id) || {};
      UI.sheet({
        title: '编辑愿望',
        body: `
          <label class="f"><span>我想实现什么</span><input id="wTitle" value="${UI.esc(w.title || '')}"></label>
          <label class="f"><span>备注（可选）</span><textarea id="wNote">${UI.esc(w.note || '')}</textarea></label>
          <div class="row spread">
            <span class="small muted">配图（可选）</span>
            <button class="btn ghost sm" data-act="wish-photo">📷 上传照片</button>
          </div>
          <div id="wPreview" style="margin-top:8px">${w.cover ? `<img src="${UI.esc(w.cover)}" style="width:100%;border-radius:12px">` : ''}</div>
          <input type="hidden" id="wCover" value="${UI.esc(w.cover || '')}">
          <label class="f" style="margin-top:10px"><span>目标日期（可选）</span><input id="wDate" type="date" value="${UI.esc(w.target_date || '')}"></label>
          <p class="small muted" style="margin-top:8px">星星币由爸爸妈妈定，这里改不了。只能改名字、备注和配图。</p>`,
        okText: '保存',
        onOk: async (wrap) => {
          const title = wrap.querySelector('#wTitle').value.trim();
          if (!title) { UI.toast('给它起个名字吧', 'err'); return false; }
          try {
            await API.put('/api/child/wish/' + id, {
              title,
              note: wrap.querySelector('#wNote').value.trim(),
              cover_image: wrap.querySelector('#wCover').value,
              target_date: wrap.querySelector('#wDate').value || null
            });
            UI.toast('愿望已更新 🌈');
            App.load();
          } catch (e) { UI.toast(e.message, 'err'); }
        }
      });
    },

    async 'redeem'(el) {
      if (!await UI.confirm('兑换这个愿望？', '提交后爸爸妈妈会收到通知，确认之前星星币处于冻结状态')) return;
      try {
        await API.post(`/api/child/redeem/${el.dataset.id}`, {});
        UI.celebrate('🎉', '兑换申请已提交', '等爸爸妈妈来确认，马上就能实现啦');
        App.load();
      } catch (e) { UI.toast(e.message, 'err'); }
    },

    'apply-open'() {
      UI.sheet({
        title: '💡 我今天还想加分',
        body: `
          <label class="f"><span>我做了什么</span><input id="aTitle" placeholder="比如：主动帮奶奶提东西"></label>
          <label class="f"><span>想申请多少星（最多 10）</span><input id="aPoints" type="number" value="5" min="1" max="10"></label>
          <label class="f"><span>说给爸爸妈妈听</span><textarea id="aText" placeholder="写一句话说明经过…"></textarea></label>
          <div class="row spread">
            <span class="small muted">也可以拍张照片</span>
            <button class="btn ghost sm" data-act="apply-photo">📷 拍照</button>
          </div>
          <div id="aPreview" style="margin-top:8px"></div>
          <input type="hidden" id="aImg">`,
        okText: '提交申请',
        onOk: async (wrap) => {
          const title = wrap.querySelector('#aTitle').value.trim();
          const text = wrap.querySelector('#aText').value.trim();
          const img = wrap.querySelector('#aImg').value;
          if (!title) { UI.toast('写一下你做了什么吧', 'err'); return false; }
          if (!text && !img) { UI.toast('写一句话或者拍张照片', 'err'); return false; }
          try {
            await API.post('/api/child/apply', {
              title, points: +wrap.querySelector('#aPoints').value || 5,
              evidence_text: text, evidence_image: img
            });
            UI.toast('已提交，等爸爸妈妈确认 😊');
            App.load();
          } catch (e) { UI.toast(e.message, 'err'); }
        }
      });
    },

    'apply-photo'() {
      UI.pickImage((url) => {
        const wrap = document.querySelector('.sheet');
        if (!wrap) return;
        wrap.querySelector('#aImg').value = url;
        wrap.querySelector('#aPreview').innerHTML = `<img src="${url}" style="width:100%;border-radius:12px">`;
      });
    },

    /* ---------------------------------------- 小游戏 */
    async 'game-start'() {
      try {
        const r = await API.get('/api/child/game/round?code=math');
        G.round = r; G.idx = 0; G.answers = new Array(r.questions.length).fill(null);
        G.left = r.time_limit; G.t0 = Date.now();
        clearInterval(G.timer);
        G.timer = setInterval(() => {
          G.left--;
          const bar = document.querySelector('.timer-wrap > i');
          if (bar) bar.style.width = (G.left / G.round.time_limit * 100) + '%';
          const h = document.querySelector('.sec-title .hint');
          if (h) h.textContent = '剩余 ' + G.left + ' 秒';
          if (G.left <= 0) { clearInterval(G.timer); actions['g-finish'](); }
        }, 1000);
        App.render();
      } catch (e) { UI.toast(e.message, 'err'); }
    },

    async 'me-avatar'() {
      const me = App.state.user || {};
      UI.pickAvatar(me.avatar, async (v) => {
        try {
          await API.patch('/api/account/profile', { avatar: v });
          App.state.user.avatar = v;
          UI.toast('头像换好啦', 'ok');
          App.load();
        } catch (e) { UI.toast(e.message, 'err'); }
      });
    },

    /* ---------------------------------------- 错题本 */
    'wb-subject'(el) {
      WB_FILTER.subject = el.value;
      WB_FILTER.order = WB_FILTER.order === 'recent' ? 'recent' : WB_FILTER.order;
      App.load();
    },

    'wb-order'(el) {
      WB_FILTER.order = el.value;
      App.load();
    },

    async 'wb-renumber'() {
      try { await API.post('/api/child/wrong/renumber', {}); UI.toast('已按默认重排'); App.load(); }
      catch (e) { UI.toast(e.message, 'err'); }
    },

    async 'wb-move'(el) {
      try {
        await API.post(`/api/child/wrong/${el.dataset.id}/move?dir=${el.dataset.dir}`, {});
        if (WB_FILTER.order !== 'manual') { WB_FILTER.order = 'manual'; }
        App.load();
      } catch (e) { UI.toast(e.message, 'err'); }
    },

    'wb-edit'(el) {
      const d = App.state.child.wrong;
      const it = (d.filtered || d.list).find(x => x.id === +el.dataset.id);
      if (!it) return;
      const subs = d.subjects || [];
      UI.sheet({
        title: '改一改这道题',
        body: `
          <label class="f"><span>题目</span><input id="wqQ" value="${UI.esc(it.question)}"></label>
          <label class="f"><span>正确答案</span><input id="wqA" value="${UI.esc(it.correct_answer)}"></label>
          <label class="f"><span>我上次写的</span><input id="wqW" value="${UI.esc(it.wrong_answer)}"></label>
          <label class="f"><span>科目</span><select id="wqS">
            ${subs.map(s => `<option value="${UI.esc(s.code)}" ${s.code === it.subject ? 'selected' : ''}>${s.icon} ${UI.esc(s.name)}</option>`).join('')}
          </select></label>
          <label class="f"><span>知识点（可不填）</span><input id="wqT" value="${UI.esc(it.tag)}" placeholder="比如：进位加法"></label>
          <label class="f"><span>做错的理由</span><select id="wqC">
            <option value="">还没填</option>
            ${[['careless', '粗心大意'], ['misread', '看错题目'], ['calc', '算错了'],
               ['unknown', '真的不会'], ['slow', '没做完'], ['other', '其它']]
              .map(c => `<option value="${c[0]}" ${c[0] === it.cause ? 'selected' : ''}>${c[1]}</option>`).join('')}
          </select></label>
          <label class="f"><span>讲一遍给自己听（解析）</span><textarea id="wqE">${UI.esc(it.explain)}</textarea></label>`,
        okText: '保存',
        onOk: async (wrap) => {
          try {
            await API.patch(`/api/child/wrong/${it.id}`, {
              question: wrap.querySelector('#wqQ').value.trim(),
              correct_answer: wrap.querySelector('#wqA').value.trim(),
              wrong_answer: wrap.querySelector('#wqW').value.trim(),
              subject: wrap.querySelector('#wqS').value,
              tag: wrap.querySelector('#wqT').value.trim(),
              cause: wrap.querySelector('#wqC').value,
              explain: wrap.querySelector('#wqE').value.trim(),
            });
            UI.toast('改好啦', 'ok');
            App.load();
          } catch (e) { UI.toast(e.message, 'err'); return false; }
        }
      });
    },

    async 'wb-variant'(el) {
      try {
        const r = await API.get(`/api/child/wrong/${el.dataset.id}/variants`);
        const vs = r.variants || [];
        UI.sheet({
          title: '同类题 · 举一反三',
          body: vs.length
            ? `<p class="small muted">原题：${UI.esc(r.question)}</p>
               ${vs.map((v, i) => `
                 <div class="card" style="margin-top:8px">
                   <div class="qt">${i + 1}. ${UI.esc(v.question)}</div>
                   <div class="wq-meta">答案
                     <b data-ans hidden>${UI.esc(v.correct_answer)}</b>
                     <a href="javascript:;" class="small" data-x-ans>点我看答案</a></div>
                 </div>`).join('')}`
            : `<p class="small muted">这类题暂时还出不了同类题，先把它做对吧 🙂</p>`,
          okText: '知道啦'
        });
        const box = document.getElementById('modalRoot');
        box.querySelectorAll('[data-x-ans]').forEach(a => {
          a.onclick = () => { const b = a.parentNode.querySelector('[data-ans]'); b.hidden = !b.hidden; };
        });
      } catch (e) { UI.toast(e.message, 'err'); }
    },

    async 'wb-rate'(el) {
      try {
        const r = await API.post(`/api/child/wrong/${el.dataset.id}/rate?rating=${el.dataset.r}&adjust=1`, {});
        UI.toast(r.tip || '已记下', 'ok');
        App.load();
      } catch (e) { UI.toast(e.message, 'err'); }
    },

    async 'wb-forget'(el) {
      if (!await UI.confirm('放回错题本', '放回之后它还会出现在复习里哦', false)) return;
      try { await API.post(`/api/child/wrong/${el.dataset.id}/forget`, {}); App.load(); }
      catch (e) { UI.toast(e.message, 'err'); }
    },

    'wb-num'(el) {
      const v = el.dataset.n;
      WB.answers[WB.idx] = String((WB.answers[WB.idx] || '') + v).slice(0, 3);
      const box = document.getElementById('gAns');
      if (box) box.textContent = WB.answers[WB.idx];
    },

    'wb-del'() {
      WB.answers[WB.idx] = String(WB.answers[WB.idx] || '').slice(0, -1) || null;
      const box = document.getElementById('gAns');
      if (box) box.textContent = WB.answers[WB.idx] == null ? '?' : WB.answers[WB.idx];
    },

    'wb-next'() {
      if (WB.idx < WB.items.length - 1) { WB.idx++; App.render(); return; }
      actions['wb-submit']();
    },

    'wb-quit'() {
      WB.mode = 'list'; WB.items = null; WB.res = null; WB.idx = 0;
      App.load();
    },

    async 'wb-start'() {
      const d = App.state.child.wrong;
      const items = (d && d.review) || [];
      if (!items.length) { UI.toast('没有要订正的题', 'err'); return; }
      WB.items = items; WB.idx = 0; WB.mode = 'review';
      WB.answers = new Array(items.length).fill(null);
      App.render();
    },

    async 'wb-submit'() {
      try {
        const r = await API.post('/api/child/wrong/review', {
          answers: (WB.answers || []).map(x => x == null ? '' : x)
        });
        WB.items = null; WB.res = r; WB.mode = 'result';
        App.render();
        if (r.points) UI.toast(`+${r.points} 颗星星币`, 'ok');
      } catch (e) {
        UI.toast(e.message, 'err');
        WB.mode = 'list'; WB.items = null; App.load();
      }
    },

    'g-num'(el) {
      const v = el.dataset.n;
      G.answers[G.idx] = String(((G.answers[G.idx] || '') + v)).slice(0, 3);
      const box = document.getElementById('gAns');
      if (box) box.textContent = G.answers[G.idx];
    },

    'g-del'() {
      G.answers[G.idx] = String(G.answers[G.idx] || '').slice(0, -1) || null;
      const box = document.getElementById('gAns');
      if (box) box.textContent = G.answers[G.idx] == null ? '?' : G.answers[G.idx];
    },

    'g-next'() {
      if (G.idx < G.round.questions.length - 1) {
        G.idx++; App.render(); return;
      }
      actions['g-finish']();
    },

    async 'g-finish'() {
      clearInterval(G.timer);
      try {
        const r = await API.post('/api/child/game/submit', {
          round_token: G.round.round_token,
          answers: G.answers.map(a => a == null ? '' : a),
          used_seconds: Math.round((Date.now() - G.t0) / 1000)
        });
        G.round = null;
        UI.celebrate(r.cleared ? '🏆' : '🎮', `答对 ${r.correct}/${r.total}`,
          r.points ? `获得 ${r.points} 颗星星币`
            : (r.overtime ? '这次超时啦，星星币已经到上限或超时' : '今天这类星星币已经到上限啦'));
        App.load();
      } catch (e) { UI.toast(e.message, 'err'); App.render(); }
    },

    /* ---- 称号自选 ---- */
    async 'pick-title'() {
      const d = App.state.child.me;
      const owned = (d.achievement_wall || []).filter(a => a.got);
      if (!owned.length) { UI.toast('还没有称号可选哦', 'err'); return; }
      UI.sheet({
        title: '挂在名字旁边的称号',
        body: `
          <div class="row spread title-opt ${!d.display_title_code ? 'on' : ''}" data-tcode="">
            <div><div style="font-weight:700">不显示额外称号</div>
              <div class="small muted">只显示等级称号</div></div>
            <span class="tag">${!d.display_title_code ? '当前' : ''}</span>
          </div>
          ${owned.map(a => `
            <div class="row spread title-opt ${d.display_title_code === a.code ? 'on' : ''}" data-tcode="${UI.esc(a.code)}">
              <div class="row"><span style="font-size:26px">${a.icon}</span>
                <div><div style="font-weight:700">${UI.esc(a.name)}</div>
                  <div class="small muted">${a.got_at} 获得</div></div></div>
              <span class="tag">${d.display_title_code === a.code ? '当前' : ''}</span>
            </div>`).join('')}`,
        okText: '关闭',
        onOk: () => {}
      });
      const box = document.getElementById('modalRoot');
      box.querySelectorAll('.title-opt').forEach(el => {
        el.style.cursor = 'pointer';
        el.onclick = async () => {
          const code = el.dataset.tcode;
          try {
            await API.post('/api/child/title', { code });
            UI.toast(code ? '称号已换好 ✨' : '已取消展示称号');
            UI.closeSheet && UI.closeSheet();
            const m = document.getElementById('modalRoot');
            if (m) m.innerHTML = '';
            App.load();
          } catch (e) { UI.toast(e.message, 'err'); }
        };
      });
    },

    /* ---- 星星花园 ---- */
    'gd-plant'(el) {
      const d = App.state.child.garden;
      UI.sheet({
        title: '种点什么',
        body: `
          <p class="small muted">种子要用星星币买，收成会比买种子多一些，但要多浇几次水、等上几小时。</p>
          <div class="plant-list">
            ${d.plants.map(p => `
              <button class="plant-row" data-code="${p.code}"
                data-act="gd-plant-pick" data-slot="${+el.dataset.slot}">
                <span style="font-size:26px">${p.emoji}</span>
                <div style="flex:1;text-align:left">
                  <b>${UI.esc(p.name)}</b>
                  <div class="small muted">种子 ${p.seed_cost} 星 · 浇 ${p.water_needed} 次 · 收 ${Math.floor(p.seed_cost * d.yield_rate)} 星</div>
                  <div class="small muted">${UI.esc(p.desc || '')}</div>
                </div>
              </button>`).join('')}
          </div>`,
        cancelText: '再想想'
      });
    },

    async 'gd-plant-pick'(el) {
      const code = el.dataset.code, slot = +el.dataset.slot;
      UI.close();
      try {
        const r = await API.post('/api/child/garden/plant', { slot, code });
        UI.toast(`种下啦，浇够 ${r.water_needed} 次水就能收 🌱`);
        App.load();
      } catch (e) { UI.toast(e.message, 'err'); }
    },

    async 'gd-water'(el) {
      try {
        const r = await API.post('/api/child/garden/water', { slot: +el.dataset.slot });
        UI.toast(r.note);
        App.load();
      } catch (e) { UI.toast(e.message, 'err'); }
    },

    async 'gd-harvest'(el) {
      try {
        const r = await API.post('/api/child/garden/harvest', { slot: +el.dataset.slot });
        if (r.gain > 0) UI.celebrate('🌻', `收获 ${r.name} +${r.gain} 星`, r.note);
        else UI.toast('今天花园的星星币已经领满啦，明天再来 🌱');
        App.load();
      } catch (e) { UI.toast(e.message, 'err'); }
    },

    /* ---- 番茄钟 ---- */
    'pm-pick'(el) {
      PM.minutes = +el.dataset.m;
      [...document.querySelectorAll('.min-chips .chip')]
        .forEach(c => c.classList.toggle('on', c === el));
    },

    async 'pm-start'() {
      const minutes = PM.minutes || App.state.child.focus.default_minutes;
      const topic = (document.getElementById('pmTopic') || {}).value || '专注学习';
      try {
        await API.post('/api/child/focus/start', { minutes, topic: topic.trim() });
        UI.toast(`开始啦！${minutes} 分钟后见 🍅`);
        App.load();
      } catch (e) { UI.toast(e.message, 'err'); }
    },

    async 'pm-finish'(el) {
      try {
        const r = await API.post('/api/child/focus/end',
          { session_id: +el.dataset.id, mode: 'finish' });
        if (r.points > 0) UI.celebrate('🍅', `专注完成 +${r.points} 星`, r.note);
        else UI.toast(r.note || '今天的上限到啦');
        App.load();
      } catch (e) { UI.toast(e.message, 'err'); }
    },

    async 'pm-abort'(el) {
      const ok = await UI.confirm('要放弃这一次吗？', '放弃不会扣星，但这一次也不算一个番茄。', true);
      if (!ok) return;
      try {
        await API.post('/api/child/focus/end',
          { session_id: +el.dataset.id, mode: 'abort' });
        UI.toast('没关系，休息一下再开始 🙂');
        App.load();
      } catch (e) { UI.toast(e.message, 'err'); }
    },

    /* ---- 每日识字 / 闯关 ---- */
    async 'w-mark'(el) {
      try {
        const r = await API.post('/api/child/word/mark',
          { key: el.dataset.k, known: el.dataset.v === '1' });
        UI.toast(r.note);
        App.load();
      } catch (e) { UI.toast(e.message, 'err'); }
    },

    'w-quiz'() { W.mode = 'quiz'; App.render(); },

    'w-mode'(el) {
      W.mode = el.dataset.v;
      App.render();
      if (W.mode === 'cards') App.load('word');
    },

    async 'w-start'() {
      try {
        const r = await API.get('/api/child/word/round');
        W.round = r;
        W.idx = 0;
        W.answers = new Array(r.questions.length).fill(null);
        W.t0 = Date.now();
        App.render();
      } catch (e) { UI.toast(e.message, 'err'); }
    },

    'w-opt'(el) {
      W.answers[W.idx] = el.dataset.v;
      App.render();
    },

    async 'w-next'() {
      if (W.idx < W.round.questions.length - 1) {
        W.idx++;
        App.render();
        return;
      }
      try {
        const sec = Math.round((Date.now() - W.t0) / 1000);
        const r = await API.post('/api/child/word/submit',
          { round_token: W.round.round_token, answers: W.answers, used_seconds: sec });
        W.round = null;
        UI.celebrate(r.cleared ? '🎯' : '📖',
          `答对 ${r.correct}/${r.total}　+${r.points} 星`, r.note);
        App.load('word');
      } catch (e) { UI.toast(e.message, 'err'); }
    },

    'w-quit'() { W.round = null; App.load('word'); },

    /* ---- 宠物 ---- */
    async 'pt-adopt'(el) {
      const code = el.dataset.sp;
      UI.sheet({
        title: '给它起个名字',
        body: `<label class="f"><span>名字</span><input id="ptName" placeholder="小星"></label>
               <p class="small muted">免费领养。它会跟着你的成长值一点点长大。</p>`,
        okText: '就是它了',
        onOk: async (wrap) => {
          const name = wrap.querySelector('#ptName').value.trim();
          try {
            const r = await API.post('/api/child/pet/adopt', { species: code, name });
            UI.celebrate('🎉', `${r.name} 来啦`, '好好照顾它，它会和你一起长大');
            App.load();
          } catch (e) { UI.toast(e.message, 'err'); }
        }
      });
    },

    async 'pt-feed'() {
      try {
        const r = await API.post('/api/child/pet/feed');
        UI.toast(r.note);
        App.load();
      } catch (e) { UI.toast(e.message, 'err'); }
    },

    async 'pt-play'() {
      try {
        const r = await API.post('/api/child/pet/play');
        UI.toast(r.note);
        App.load();
      } catch (e) { UI.toast(e.message, 'err'); }
    },

    /* ---- 荣誉证书 ---- */
    async 'certificate'() {
      try {
        const c = await API.get('/api/child/certificate');
        const host = document.getElementById('modalRoot');
        host.innerHTML = certHTML(c);
      } catch (e) { UI.toast(e.message, 'err'); }
    },

    'cert-close'() {
      document.getElementById('modalRoot').innerHTML = '';
    },

    'cert-print'() {
      try { window.print(); }
      catch (e) { UI.toast('这台设备不支持直接打印，可以截图保存哦', 'err'); }
    },
  };

  return { home, wishes, game, wrong, garden, focus, word, pet, family, me, actions };
})();
