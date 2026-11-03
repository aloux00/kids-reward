/* ============================================================
   家长端视图。多名家长共享同一个家庭，谁看到谁处理。
   ============================================================ */
const ParentViews = (() => {

  const CATS = [
    { k: 'study', n: '学习', i: '📚' }, { k: 'exercise', n: '运动', i: '🏃' },
    { k: 'chore', n: '家务', i: '🧹' }, { k: 'habit', n: '习惯', i: '⏰' },
  ];

  /* ------------------------------------------------ 待办理 */
  function todo(d) {
    const items = d.pending.items;
    const c = d.overview.counts;
    const kinds = { task: ['打卡待确认', '📋'], apply: ['加分申请', '💡'], redeem: ['兑换申请', '🎁'] };

    return `
      <div class="sec-title"><h3>🔔 待处理</h3><span class="hint">${UI.todayCn()}</span></div>
      <div class="stat-row">
        <div class="s"><b>${c.task}</b><span>打卡</span></div>
        <div class="s"><b>${c.apply}</b><span>加分申请</span></div>
        <div class="s"><b>${c.redeem}</b><span>兑换</span></div>
      </div>
      ${items.length ? items.map(pendingRow).join('')
        : `<div class="card">${empty('全部处理完了 👏')}</div>`}

      <div class="sec-title"><h3>👧🧒 孩子概览</h3></div>
      ${d.overview.kids.map(kidRow).join('')}
      <p class="small muted" style="text-align:center;margin-top:12px">
        ${Object.values(kinds).map(v => v[0]).join(' · ')} 三类待办合并显示在同一列表里
      </p>`;
  }

  function pendingRow(it) {
    const label = { task: '打卡待确认', apply: '加分申请', redeem: '兑换申请' }[it.kind];
    const evi = it.evidence_image
      ? `<div class="evi"><img src="${UI.esc(it.evidence_image)}" style="max-width:100%;border-radius:8px">
           ${it.evidence_text ? '<div style="margin-top:6px">' + UI.esc(it.evidence_text) + '</div>' : ''}</div>`
      : (it.evidence_text ? `<div class="evi">${UI.esc(it.evidence_text)}</div>` : '');

    return `
      <div class="pending-item">
        <div class="row spread">
          <div class="row">
            <span class="ava" style="width:34px;height:34px;border-radius:50%;background:var(--primary-soft);display:grid;place-items:center;font-size:20px">${UI.esc(it.child_avatar)}</span>
            <div>
              <div class="who">${UI.esc(it.child_name)} · ${label}</div>
              <div class="small muted">${it.at}</div>
            </div>
          </div>
          <span class="tag ${it.kind === 'redeem' ? '' : 'g'}">${it.kind === 'redeem' ? '-' : '+'}${it.points} 星</span>
        </div>
        <div class="tt">${UI.esc(it.icon || '')} ${UI.esc(it.title)}</div>
        ${evi}
        <div class="acts">
          <button class="btn r" data-act="p-reject" data-kind="${it.kind}" data-id="${it.id}">驳回</button>
          <button class="btn g" data-act="p-approve" data-kind="${it.kind}" data-id="${it.id}"
            data-points="${it.points}" data-title="${UI.esc(it.title)}">通过</button>
        </div>
      </div>`;
  }

  function kidRow(k) {
    return `
      <div class="kid-row">
        <div class="ava">${UI.avatar(k.avatar)}</div>
        <div style="flex:1">
          <div style="font-weight:800">${UI.esc(k.name)} <span class="tag">Lv${k.level} ${UI.esc(k.title)}</span></div>
          <div class="small muted">可用 ${k.coin_available} 星${k.coin_frozen ? ` · 冻结 ${k.coin_frozen}` : ''} · 成长值 ${k.exp_total} · 连续 ${k.streak_days} 天</div>
        </div>
        <button class="btn ghost sm" data-act="p-report" data-id="${k.id}">报表</button>
      </div>`;
  }

  /* ------------------------------------------------ 任务管理 */
  function tasks(d) {
    const list = d.tasks.tasks, kids = d.tasks.kids;
    return `
      <div class="sec-title">
        <h3>📋 任务库</h3>
        <span class="hint">只有家长能发布任务</span>
      </div>
      <button class="btn primary block lg" style="margin-bottom:12px" data-act="p-task-new">＋ 发布任务</button>
      ${list.map(t => taskCard(t, kids)).join('')}
      <p class="small muted" style="margin-top:10px">
        每天重复的任务请选「按天重复」，临时安排的一次性机会请选「不重复」，可用截止时间控制它的有效期。
      </p>`;
  }

  function taskCard(t, kids) {
    const rep = { daily: '每天', weekly: '每周', none: '一次' }[t.repeat_type];
    const names = t.assignee_names.length ? t.assignee_names.join('、') : '全部孩子';
    return `
      <div class="card" style="${t.active ? '' : 'opacity:.55'}">
        <div class="row spread">
          <div class="row">
            <span style="font-size:26px">${UI.esc(t.icon)}</span>
            <div>
              <div style="font-weight:800">${UI.esc(t.name)}</div>
              <div class="small muted">${CATS.find(c => c.k === t.category)?.n || t.category} · ${rep} · ${names}</div>
            </div>
          </div>
          <span class="tag g">${t.points} 星</span>
        </div>
        <div class="row" style="margin-top:10px;gap:6px;flex-wrap:wrap">
          <span class="tag n">${t.display_zone === 'today' ? '今日任务区' : '额外任务区'}</span>
          ${t.need_approval ? '<span class="tag a">需确认</span>' : '<span class="tag n">自动入账</span>'}
          ${t.need_photo ? '<span class="tag">需照片</span>' : ''}
          ${t.repeat_type === 'weekly' && t.repeat_rule.length ? `<span class="tag n">周${t.repeat_rule.map(x => '一二三四五六日'[x - 1]).join('')}</span>` : ''}
          ${!t.active ? '<span class="tag r">已停用</span>' : ''}
        </div>
        ${t.active ? `
        <div class="row" style="margin-top:10px;gap:8px">
          <button class="btn ghost sm" data-act="p-task-edit" data-id="${t.id}">修改</button>
          <button class="btn ghost sm" data-act="p-task-stop" data-id="${t.id}">停用</button>
        </div>` : ''}
      </div>`;
  }

  function taskForm(t, kids) {
    const isEdit = !!t;
    t = t || { name: '', category: 'study', points: 5, icon: '✅', repeat_type: 'daily',
               repeat_rule: [], assignee_ids: [], display_zone: 'today',
               need_approval: true, need_photo: false, effective_from: '', effective_to: '' };
    return `
      <label class="f"><span>任务名称</span><input id="tName" value="${UI.esc(t.name)}" placeholder="比如：阅读 30 分钟"></label>
      <div class="row" style="gap:8px">
        <label class="f" style="flex:1"><span>图标</span><input id="tIcon" value="${UI.esc(t.icon)}" maxlength="4"></label>
        <label class="f" style="flex:2"><span>分值</span><input id="tPoints" type="number" value="${t.points}" min="1" max="50"></label>
      </div>
      <label class="f"><span>分类</span>
        <select id="tCat">${CATS.map(c => `<option value="${c.k}" ${t.category === c.k ? 'selected' : ''}>${c.i} ${c.n}</option>`).join('')}</select>
      </label>
      <label class="f"><span>重复方式</span>
        <select id="tRepeat">
          <option value="daily" ${t.repeat_type === 'daily' ? 'selected' : ''}>按天重复（每天作业等）</option>
          <option value="weekly" ${t.repeat_type === 'weekly' ? 'selected' : ''}>按周重复（指定星期）</option>
          <option value="none" ${t.repeat_type === 'none' ? 'selected' : ''}>不重复（随机任务 / 一次性惊喜）</option>
        </select>
      </label>
      <label class="f"><span>星期（仅按周重复时生效）</span>
        <div class="row" style="flex-wrap:wrap;gap:6px">
          ${['一','二','三','四','五','六','日'].map((d, i) => `
            <label class="tag n" style="cursor:pointer">
              <input type="checkbox" class="tDay" value="${i + 1}" ${t.repeat_rule.includes(i + 1) ? 'checked' : ''} style="width:auto"> 周${d}
            </label>`).join('')}
        </div>
      </label>
      <div class="row" style="gap:8px">
        <label class="f" style="flex:1"><span>生效日（可空）</span><input id="tFrom" type="date" value="${t.effective_from}"></label>
        <label class="f" style="flex:1"><span>截止日（可空）</span><input id="tTo" type="date" value="${t.effective_to}"></label>
      </div>
      <label class="f"><span>派给谁（不选则全部孩子）</span>
        <div class="row" style="flex-wrap:wrap;gap:6px">
          ${kids.map(k => `<label class="tag n" style="cursor:pointer">
            <input type="checkbox" class="tKid" value="${k.id}" ${t.assignee_ids.includes(k.id) ? 'checked' : ''} style="width:auto">
            ${UI.avatarText(k.avatar)} ${UI.esc(k.name)}</label>`).join('')}
        </div>
      </label>
      <label class="f"><span>展示区</span>
        <select id="tZone">
          <option value="today" ${t.display_zone === 'today' ? 'selected' : ''}>今日任务区（不做影响连续打卡）</option>
          <option value="extra" ${t.display_zone === 'extra' ? 'selected' : ''}>额外任务区（多劳多得，不做不扣星）</option>
        </select>
      </label>
      <label class="row"><input type="checkbox" id="tApprove" ${t.need_approval ? 'checked' : ''} style="width:auto"> 需要家长确认后才给分</label>
      <label class="row" style="margin-top:8px"><input type="checkbox" id="tPhoto" ${t.need_photo ? 'checked' : ''} style="width:auto"> 必须提交照片佐证</label>
      <p class="small muted" style="margin-top:10px">随机任务同样计入每日上限，不会被用来绕过上限。</p>`;
  }

  /* ------------------------------------------------ 愿望 */
  function wishes(d) {
    const list = d.wishes.wishes;
    const waiting = list.filter(w => w.status === 'pending');
    const others = list.filter(w => w.status !== 'pending');
    return `
      <div class="sec-title"><h3>🌈 愿望管理</h3><span class="hint">孩子许愿后需要确认</span></div>
      ${waiting.length
        ? waiting.map(w => `
            <div class="card" style="border:2px solid var(--gold)">
              <div class="row spread">
                <div>
                  <div style="font-weight:800">${UI.esc(w.title)}</div>
                  <div class="small muted">${UI.esc(w.child_name)} · ${w.priced ? w.cost + ' 星' : '<b style="color:var(--gold)">⭐ 还没定价</b>'} · ${w.created_at}</div>
                </div>
                <span class="tag a">待确认</span>
              </div>
              ${w.note ? `<p class="small muted" style="margin-top:6px">${UI.esc(w.note)}</p>` : ''}
              <div class="row" style="margin-top:10px;gap:8px">
                <button class="btn r sm" data-act="p-wish-reject" data-id="${w.id}">不合适</button>
                <button class="btn gold sm" data-act="p-wish-approve" data-id="${w.id}" data-cost="${w.cost}">${w.priced ? '确认并调整分值' : '⭐ 定星星币并确认'}</button>
              </div>
            </div>`).join('')
        : `<div class="card">${empty('没有等待确认的愿望 👌')}</div>`}

      <div class="sec-title"><h3>📜 全部愿望</h3></div>
      ${others.map(w => `
        <div class="card">
          <div class="row spread">
            <div>
              <div style="font-weight:800">${UI.esc(w.title)}</div>
              <div class="small muted">${UI.esc(w.child_name)} · ${w.priced ? w.cost + ' 星' : '<b style="color:var(--gold)">⭐ 还没定价</b>'}</div>
            </div>
            ${statusTag(w.status)}
          </div>
          ${w.status === 'active' ? `
          <div class="row" style="margin-top:9px;gap:8px">
            <button class="btn ghost sm" data-act="p-wish-cost" data-id="${w.id}" data-cost="${w.cost}">⭐ 改星星币数量</button>
          </div>` : ''}
        </div>`).join('') || `<div class="card">${empty('暂无')}</div>`}`;
  }

  function statusTag(s) {
    return { pending: '<span class="tag a">待确认</span>', active: '<span class="tag g">进行中</span>',
             completed: '<span class="tag">已实现 🎉</span>', abandoned: '<span class="tag n">已放弃</span>' }[s] || '';
  }

  /* ------------------------------------------------ 更多 */
  function more(d) {
    const kids = d.overview.kids;
    const R = d.rules || { levels: [], application: {}, daily_cap: {} };
    return `
      <div class="sec-title"><h3>⚙️ 管理</h3><span class="hint">${UI.esc(d.overview.parent.name)} · ${d.overview.parent.role === 'owner' ? '主账号' : '家长'}</span></div>
      <div class="grid2">
        <div class="card">
          <h4 style="margin-bottom:10px">👨‍👩‍👧 家庭成员</h4>
          ${d.members.members.map(m => `
            <div class="row spread" style="padding:6px 0;border-bottom:1px dashed var(--line)">
              <div class="row"><span style="font-size:22px">${UI.avatar(m.avatar, 26)}</span>
                <div><div style="font-weight:700">${UI.esc(m.name)}</div>
                  <div class="small muted">${m.role === 'child' ? '孩子' : (m.role === 'owner' ? '主家长' : '家长')}${m.username ? ' · ' + UI.esc(m.username) : ''}</div></div></div>
              <button class="btn ghost xs" data-act="p-member-edit" data-id="${m.id}" data-role="${m.role}">编辑</button>
            </div>`).join('')}
          <button class="btn ghost block sm" style="margin-top:10px" data-act="p-kid-new">＋ 添加孩子</button>
        </div>
        <div class="card">
          <h4 style="margin-bottom:10px">⭐ 手动调整</h4>
          <p class="small muted">偶尔的特别鼓励可以在这里给分，同样受每日上限约束。</p>
          ${kids.map(k => `
            <button class="btn ghost block sm" style="margin-top:8px"
              data-act="p-grant" data-id="${k.id}" data-nm="${UI.esc(k.name)}">给 ${UI.esc(k.name)} 加分</button>`).join('')}
        </div>
      </div>
      <div class="grid2">
        <div class="card">
          <h4 style="margin-bottom:10px">📕 错题本</h4>
          <p class="small muted">按科目汇总、挑题排序、导出可打印的 Word 练习卷，还能维护科目。</p>
          <button class="btn primary block sm" style="margin-top:10px" data-act="go" data-v="wrongbook">打开错题汇总</button>
          <button class="btn ghost block sm" style="margin-top:8px" data-act="p-subjects">🏷️ 科目管理</button>
        </div>
        <div class="card">
          <h4 style="margin-bottom:10px">📚 教材库</h4>
          <p class="small muted">上传课本或从内置教材库下载，孩子翻开即读；还能布置「读第几页」的阅读作业。</p>
          <button class="btn primary block sm" style="margin-top:10px" data-act="go" data-v="library">打开教材库</button>
        </div>
      </div>
      <div class="card">
        <h4 style="margin-bottom:10px">🎨 界面与账号</h4>
        <p class="small muted">左上角的名字、你自己和孩子的头像、登录口令，都在这里改。</p>
        <button class="btn ghost block sm" style="margin-top:10px" data-act="p-brand">🏷️ 改系统名字</button>
        <button class="btn ghost block sm" style="margin-top:8px" data-act="p-my-profile">🙋 我的资料</button>
      </div>
      <div class="card">
        <h4 style="margin-bottom:10px">📚 家长学堂 · 家庭共学</h4>
        <p class="small muted">十几篇离线微课，每篇都收在「今晚就能做的一件事」上；
          顺手把陪伴孩子的分钟数记下来 —— 这些数据也会出现在孩子那一端。</p>
        <button class="btn primary block sm" style="margin-top:10px" data-act="go" data-v="school">打开家长学堂</button>
      </div>
      <div class="card">
        <h4 style="margin-bottom:10px">⚖️ 积分规则</h4>
        <div class="stat-row" style="margin-top:2px">
          <div class="s"><b>${R.daily_cap ? Object.values(R.daily_cap).reduce((a, b) => a + (+b || 0), 0) : '-'}</b><span>每天上限合计</span></div>
          <div class="s"><b>${R.levels.length}</b><span>等级</span></div>
          <div class="s"><b>${R.application.enabled ? '开' : '关'}</b><span>申请加分</span></div>
        </div>
        <p class="small muted" style="margin-top:8px">分值、每日上限、等级称号、特权、连击奖励、游戏开关，都可以直接调整。</p>
        <button class="btn primary block sm" style="margin-top:10px" data-act="go" data-v="rules">打开规则编辑器</button>
      </div>
      <button class="btn ghost block lg" style="margin-top:10px" data-act="logout">退出登录</button>`;
  }

  /* ------------------------------------------------ 错题汇总 */
  const WSTATUS = { pending: '没掌握的', mastered: '已掌握的', all: '全部' };

  function wrongbook(d) {
    const s = d.wrong, st = d.wrongStats || {};
    if (!s) return `<div class="card">${empty('正在整理错题…')}</div>`;

    const q = s.filter || {};
    const kids = s.kids || [];
    const subs = s.subjects || [];
    const groups = s.groups || [];
    const picked = WBK.ids;

    return `
      <div class="savebar">
        <button class="btn ghost sm" data-act="go" data-v="more">‹ 返回</button>
        <div style="flex:1;text-align:center;font-weight:800">📕 错题汇总</div>
        <span class="small muted">${s.total} 题</span>
      </div>

      <div class="wb-toolbar">
        <select data-act="wbk-kid">
          ${kids.map(k => `<option value="${k.id}" ${k.id === q.kid_id ? 'selected' : ''}>${UI.avatarText(k.avatar)} ${UI.esc(k.name)}</option>`).join('')}
        </select>
        <select data-act="wbk-subject">
          <option value="">全部科目</option>
          ${subs.map(x => `<option value="${UI.esc(x.code)}" ${x.code === q.subject ? 'selected' : ''}>${x.icon} ${UI.esc(x.name)}</option>`).join('')}
        </select>
        <select data-act="wbk-status">
          ${Object.entries(WSTATUS).map(([k, v]) => `<option value="${k}" ${k === q.status ? 'selected' : ''}>${v}</option>`).join('')}
        </select>
      </div>

      <div class="grid2">
        <div class="card">
          <div class="stat-row" style="margin:0">
            <div class="s"><b>${st.total || 0}</b><span>累计错题</span></div>
            <div class="s"><b>${st.pending || 0}</b><span>没掌握</span></div>
            <div class="s"><b>${st.due_today || 0}</b><span>今天到期</span></div>
            <div class="s"><b>${st.master_rate || 0}%</b><span>掌握率</span></div>
          </div>
        </div>
        <div class="card">
          <div class="small muted" style="margin-bottom:4px">分科目</div>
          ${(st.by_subject || []).map(x => `
            <div class="row spread" style="padding:3px 0">
              <span class="small">${UI.esc(x.name)}</span>
              <span class="small muted">${x.pending} 未掌握 / ${x.total} · ${x.rate}%</span>
            </div>`).join('') || '<p class="small muted">还没有错题</p>'}
        </div>
      </div>

      ${(st.by_cause || []).length ? `
      <div class="card" style="margin-top:10px">
        <div class="small muted" style="margin-bottom:6px">错在哪儿（这才知道该怎么改）</div>
        <div class="row" style="gap:8px;flex-wrap:wrap">
          ${st.by_cause.map(c => `<span class="tag-sub">${UI.esc(c.name)} ${c.count}</span>`).join('')}
        </div>
      </div>` : ''}

      <div class="card" style="margin-top:10px">
        <div class="row spread" style="margin-bottom:8px">
          <b>要打印的题（${picked.length ? picked.length + ' 道已选' : '默认全部'}）</b>
          <span class="small muted">点题号可以勾选 / 取消</span>
        </div>
        <div class="row" style="gap:8px;flex-wrap:wrap;margin-bottom:8px">
          <label class="row small" style="gap:4px">
            <input type="checkbox" id="wbkAns" ${WBK.answers ? 'checked' : ''}>附答案页</label>
          <label class="row small" style="gap:4px">
            <input type="checkbox" id="wbkVar" ${WBK.variants ? 'checked' : ''}>每题带一道同类题</label>
        </div>
        <div class="row" style="gap:8px;flex-wrap:wrap">
          <button class="btn primary sm" data-act="w-export">📄 导出 Word</button>
          <button class="btn ghost sm" data-act="w-print">🖨️ 打印练习卷</button>
          <button class="btn ghost sm" data-act="w-renumber">↻ 按推荐顺序整理</button>
          ${picked.length ? `<button class="btn ghost sm" data-act="w-clear-pick">清空选择</button>` : ''}
        </div>
      </div>

      ${groups.length ? groups.map(g => `
        <div class="sec-title" style="margin-top:14px">
          <h3>${g.icon} ${UI.esc(g.name)}</h3><span class="hint">${g.count} 题 · ${g.pending} 未掌握</span>
        </div>
        <div class="card">
          ${g.items.map((it, i) => `
            <div class="wq-item">
              <div class="wq-head">
                <label class="row small" style="gap:6px;align-items:flex-start">
                  <input type="checkbox" class="wbk-pick" data-act="w-pick" data-id="${it.id}" ${picked.includes(it.id) ? 'checked' : ''}>
                  <div>
                    <div class="qt">${i + 1}. ${UI.esc(it.question)} ${it.mastered ? '✅' : ''}</div>
                    <div class="wq-meta">
                      ${it.tag ? `<span class="tag-sub">${UI.esc(it.tag)}</span> ` : ''}
                      ${it.cause_name ? `<span class="tag-sub">${UI.esc(it.cause_name)}</span> ` : ''}
                      错过 ${it.times_wrong} 次 · 复习过 ${it.times_reviewed} 次 ·
                      ${it.mastered ? '已掌握' : (it.due_date ? `${it.due_date} 再见` : '待复习')}
                      <span style="color:#c9c2b6">${it.seq}</span>
                    </div>
                    <div class="wq-meta">你答 ${UI.esc(it.wrong_answer || '空')} · 正确答案 <b>${UI.esc(it.correct_answer)}</b>
                      ${it.explain ? ' · ' + UI.esc(it.explain) : ''}</div>
                  </div>
                </label>
              </div>
              <div class="wq-acts">
                <button class="btn ghost xs" data-act="w-move" data-id="${it.id}" data-dir="up">↑</button>
                <button class="btn ghost xs" data-act="w-move" data-id="${it.id}" data-dir="down">↓</button>
                <button class="btn ghost xs" data-act="w-edit" data-id="${it.id}">✏️ 编辑</button>
                <button class="btn r xs" data-act="w-del" data-id="${it.id}">🗑 删除</button>
              </div>
            </div>`).join('')}
        </div>`).join('')
        : `<div class="card" style="text-align:center;padding:26px 16px;margin-top:10px">
             <div style="font-size:44px">🎉</div>
             <p class="muted small" style="margin-top:6px">这个筛选条件下没有错题</p>
           </div>`}

      <p class="small muted" style="margin-top:12px">
        导出的是「练习卷 + 答案/解析」两份内容：前面只留题面给孩子写，后面给家长对答案。
        题里带的小号数字是来源编号，孩子做完可以直接回这里找原题。
      </p>`;
  }

  /* ------------------------------------------------ 规则编辑器 */
  function rules(d) {
    const r = d.rules;
    const g = (r.games && r.games[0]) || {};
    const ap = r.application || {};
    const cap = r.daily_cap || {};
    const gd = r.garden || {}, pd = r.pomodoro || {}, wd = r.words || {}, pt = r.pet || {};
    const sum = Object.values(cap).reduce((a, b) => a + (+b || 0), 0);
    const NS = (id, v, step) => `<input id="${id}" type="number" value="${v}" ${step ? `step="${step}"` : ''}>`;

    return `
      <div class="savebar">
        <button class="btn ghost sm" data-act="go" data-v="more">‹ 返回</button>
        <div style="flex:1;text-align:center;font-weight:800">⚖️ 积分规则</div>
        <button class="btn gold sm" data-act="p-rules-save">保存</button>
      </div>
      <div class="rule-tip">改完点保存，<b>立即生效</b>，孩子不用重新登录。规则存在服务器的 <code>rules.yaml</code> 里。</div>

      <div class="rule-head"><h3>🪙 星星叫什么名字</h3></div>
      <div class="card">
        <div class="numgrid">
          <label class="f"><span>能花的（兑换愿望用）</span><input id="rcCoin" value="${UI.esc(r.currency.coin_name)}"></label>
          <label class="f"><span>不能花的（决定等级）</span><input id="rcExp" value="${UI.esc(r.currency.exp_name)}"></label>
        </div>
        <p class="small muted" style="margin-top:8px">
          两种点数同时增加、同时累计。兑换时只花掉第一种，第二种永远不清零 —— 这样孩子换完礼物也不会失去等级和积累。
        </p>
      </div>

      <div class="rule-head"><h3>🚧 每天最多能赚多少</h3><span class="hint">合计 ${sum} 星/天</span></div>
      <div class="card">
        <div class="rule-tip">
          每一类任务一天内的得分上限，超出部分不计分。它的作用是防止孩子靠反复做同一类事情把星星币刷贬值。
        </div>
        <div class="numgrid">
          <label class="f"><span>📚 学习</span>${NS('dcStudy', cap.study)}</label>
          <label class="f"><span>🏃 运动</span>${NS('dcExercise', cap.exercise)}</label>
          <label class="f"><span>🧹 家务</span>${NS('dcChore', cap.chore)}</label>
          <label class="f"><span>⏰ 习惯</span>${NS('dcHabit', cap.habit)}</label>
          <label class="f"><span>🎮 游戏</span>${NS('dcGame', cap.game)}</label>
          <label class="f"><span>🌱 花园</span>${NS('dcGarden', cap.garden)}</label>
        </div>
      </div>

      <div class="rule-head"><h3>🔥 连续打卡奖励</h3></div>
      <div class="card">
        <div class="rule-tip">
          连续天数达到门槛时额外送一次奖励。这是撑过第 7 天、第 30 天的关键 —
          孩子为「不断签」而坚持的动力，往往比为具体任务更强。
        </div>
        <div class="numgrid">
          ${r.streak_bonus.map(b => `
            <label class="f"><span>连续 ${b.days} 天</span>
              <input class="sbRow" data-days="${b.days}" type="number" value="${b.points}"></label>`).join('')}
          <label class="f"><span>🛡️ 每月断签保护</span>${NS('shShield', r.streak_shield_per_month)}</label>
        </div>
        <p class="small muted" style="margin-top:8px">
          断签保护：偶尔漏打卡一天不会被清零，每月只能用这么多次。
        </p>
      </div>

      <div class="rule-head"><h3>🎖️ 等级、称号与特权</h3><span class="hint">${r.levels.length} 级</span></div>
      <div class="card">
        <div class="rule-tip">
          成长值达到门槛就升到这一级。<b>每一级都要配一个真实的家庭特权</b> ——
          只有名字、生活里没有任何变化的称号，三天就会被孩子无视。
        </div>
        <div id="lvBox">
          ${r.levels.map((l, i) => lvRow(l, i)).join('')}
        </div>
        <button class="btn ghost block sm" style="margin-top:6px" data-act="p-lv-add">＋ 增加一级</button>
      </div>

      <div class="rule-head"><h3>💡 孩子主动申请加分</h3></div>
      <div class="card">
        <div class="sw-row">
          <div><div class="lb">允许孩子主动申请</div>
            <div class="d">做了分外的好事可以提交，家长确认后才给分。既不剥夺主动性，也守住了发布权。</div></div>
          <label class="switch"><input type="checkbox" id="apEnabled" ${ap.enabled ? 'checked' : ''}><i></i></label>
        </div>
        <div class="numgrid" style="margin-top:12px">
          <label class="f"><span>每天最多申请</span>${NS('apDaily', ap.daily_limit)}</label>
          <label class="f"><span>单次最多给</span>${NS('apMax', ap.max_points_per_apply)}</label>
          <label class="f"><span>超期自动作废（天）</span>${NS('apExpire', ap.expire_days)}</label>
        </div>
        <div class="sw-row">
          <div><div class="lb">必须有照片或文字佐证</div>
            <div class="d">不建议强制照片 ——「多读了 20 分钟书」没法拍，硬要照片只会逼孩子随手敷衍。</div></div>
          <label class="switch"><input type="checkbox" id="apEvidence" ${ap.require_evidence ? 'checked' : ''}><i></i></label>
        </div>
        <div class="sw-row">
          <div><div class="lb">计入每日上限 <span class="tag g">建议开启</span></div>
            <div class="d">关掉的话，申请就成了绕开上限的后门，前面所有防通胀的设计都会被架空。</div></div>
          <label class="switch"><input type="checkbox" id="apCap" ${ap.count_into_daily_cap ? 'checked' : ''}><i></i></label>
        </div>
      </div>

      <div class="rule-head"><h3>🎮 益智小游戏</h3></div>
      <div class="card">
        <div class="sw-row">
          <div><div class="lb">开启小游戏</div><div class="d">分数由服务器判定，孩子改不了浏览器里的结果。</div></div>
          <label class="switch"><input type="checkbox" id="gEnabled" ${g.enabled ? 'checked' : ''}><i></i></label>
        </div>
        <div class="numgrid" style="margin-top:12px">
          <label class="f"><span>每天最多玩</span>${NS('gLimit', r.gating.game_daily_play_limit)}</label>
          <label class="f"><span>每局题量</span>${NS('gQuestions', g.questions)}</label>
          <label class="f"><span>答对一题</span>${NS('gPer', g.points_per_correct)}</label>
          <label class="f"><span>全部答对额外</span>${NS('gClear', g.clear_bonus)}</label>
          <label class="f"><span>限时（秒）</span>${NS('gTime', g.time_limit)}</label>
        </div>
        <div class="sw-row">
          <div><div class="lb">完成当天学习任务才解锁</div>
            <div class="d">把游戏放在学习之后 —— 顺序反过来的话，学习会变成对游戏的阻碍。</div></div>
          <label class="switch"><input type="checkbox" id="gUnlock" ${r.gating.game_unlock_after_study ? 'checked' : ''}><i></i></label>
        </div>
      </div>

      <div class="rule-head"><h3>🧩 扩展模块</h3><span class="hint">花园 / 番茄钟 / 识字 / 宠物</span></div>
      <div class="card">
        <div class="rule-tip">
          这几个模块的分值全部走同一套上限与同一个记账内核，这里只是它们的旋钮。
          默认值已经压得很克制 —— 调高之前先想清楚：孩子会不会发现「刷这个」比好好打卡更划算。
        </div>
        <div class="sw-row">
          <div><div class="lb">星星花园</div>
            <div class="d">浇水不给分，只有收成才给；收益率刻意压低，教的是「等一等才有」。</div></div>
          <label class="switch"><input type="checkbox" id="gdEnabled" ${gd.enabled ? 'checked' : ''}><i></i></label>
        </div>
        <div class="sw-row">
          <div><div class="lb">番茄钟</div>
            <div class="d">时长由服务端按真实时间差判定，孩子改不了时钟。</div></div>
          <label class="switch"><input type="checkbox" id="pdEnabled" ${pd.enabled ? 'checked' : ''}><i></i></label>
        </div>
        <div class="sw-row">
          <div><div class="lb">每日识字 / 识字闯关</div>
            <div class="d">词库全部在本机，离线可用；答错的字自动进错题本。</div></div>
          <label class="switch"><input type="checkbox" id="wdEnabled" ${wd.enabled ? 'checked' : ''}><i></i></label>
        </div>
        <div class="sw-row">
          <div><div class="lb">宠物养成</div>
            <div class="d">等级跟着成长值走，喂东西喂不大；不会死亡，不会有惩罚。</div></div>
          <label class="switch"><input type="checkbox" id="ptEnabled" ${pt.enabled ? 'checked' : ''}><i></i></label>
        </div>
        <div class="numgrid" style="margin-top:12px">
          <label class="f"><span>🌱 浇水间隔（分钟）</span>${NS('gdCool', gd.water_cooldown_min)}</label>
          <label class="f"><span>🌱 收成倍率</span>${NS('gdYield', gd.yield_rate, '0.05')}</label>
          <label class="f"><span>🌱 初始地块</span>${NS('gdSlots', gd.slots_base)}</label>
          <label class="f"><span>🍅 每天几个番茄</span>${NS('pdLimit', pd.daily_limit)}</label>
          <label class="f"><span>🍅 一个番茄几分</span>${NS('pdPoints', pd.points_per_pomodoro)}</label>
          <label class="f"><span>📖 每天新字几个</span>${NS('wdPer', wd.new_per_day)}</label>
          <label class="f"><span>📖 闯关每天几局</span>${NS('wdLimit', wd.daily_round_limit)}</label>
          <label class="f"><span>🐾 喂一次几星</span>${NS('ptFeed', pt.feed_cost)}</label>
        </div>
      </div>

      <div class="rule-head"><h3>🎁 兑换</h3></div>
      <div class="card">
        <label class="f"><span>小额自动核销阈值（星）</span>${NS('rdAuto', r.redemption.auto_approve_below)}</label>
        <p class="small muted">填 0 表示所有兑换都要家长点确认。建议保持 0 ——
          由爸爸妈妈把礼物送到手里，这个动作本身就是仪式感。</p>
      </div>

      <div class="card">
        <h4 style="margin-bottom:8px">🧾 原始文件</h4>
        <p class="small muted">需要精细调整时可以直接编辑原文，支持注释与任意字段。</p>
        <button class="btn ghost block sm" style="margin-top:8px" data-act="p-rules-raw">查看 / 编辑 YAML 原文</button>
      </div>

      <div class="row" style="gap:8px">
        <button class="btn ghost lg" style="flex:1" data-act="go" data-v="more">取消</button>
        <button class="btn gold lg" style="flex:2" data-act="p-rules-save">保存并生效</button>
      </div>`;
  }

  function lvRow(l, i) {
    return `
      <div class="lv-row">
        <div class="no">Lv${i + 1}</div>
        <input class="lv-title" value="${UI.esc(l.title)}" placeholder="称号">
        <input class="lv-exp" type="number" value="${l.exp}" ${i === 0 ? 'disabled' : ''} title="成长值门槛">
        <input class="lv-perk perk" value="${UI.esc(l.perk)}" placeholder="解锁的真实特权，如：决定一次周末活动">
        ${i === 0
          ? '<div class="del small muted" style="text-align:center">起始</div>'
          : '<button class="btn ghost sm del" data-act="p-lv-del">删除</button>'}
      </div>`;
  }

  /* ------------------------------------------------ 家长学堂 / 家庭共学 */
  const SC = { kind: 'read' };

  function school(d) {
    const s = d.school;
    if (!s) return `<div class="card">${empty('正在准备今日内容…')}</div>`;

    return `
      <div class="sec-title"><h3>📚 家长学堂</h3>
        <span class="hint">已读 ${s.read_count}/${s.total_articles} 篇</span></div>

      <div class="card">
        <div class="row spread">
          <div>
            <div style="font-weight:800">本周陪伴</div>
            <div class="small muted">目标 ${s.goal_minutes} 分钟 · ${s.week_count} 次</div>
          </div>
          <div style="font-size:26px;font-weight:900">${s.week_minutes}<span class="small muted"> 分</span></div>
        </div>
        <div class="bar exp" style="margin-top:10px"><i style="width:${s.week_percent}%"></i></div>
        <div class="row spread" style="margin-top:6px">
          ${s.kids.map(k => `<span class="small muted">${UI.avatarText(k.avatar)} ${UI.esc(k.name)} ${k.minutes} 分</span>`).join('')}
          <span class="small muted">${s.week_percent}%</span>
        </div>
        <p class="small muted" style="margin-top:8px">
          陪伴不会折算成孩子的星星币 —— 记录在这里，是让孩子也看得见你的付出。
        </p>
      </div>

      <div class="sec-title"><h3>✨ 今日推荐</h3><span class="hint">没读过的优先</span></div>
      ${s.recommend.map(articleCard).join('')}

      <div class="sec-title"><h3>🗂 全部内容</h3></div>
      <div class="tool-grid">
        ${s.topics.map(t => `
          <button class="tool" data-act="p-school-topic" data-topic="${t.code}">
            <span class="ti">${t.emoji}</span>
            <b>${UI.esc(t.name)}</b>
            <span class="small muted">${t.count} 篇</span>
          </button>`).join('')}
      </div>

      <div class="sec-title"><h3>🤝 登记一次家庭共学</h3><span class="hint">今晚就能做</span></div>
      <div class="card">
        <label class="f"><span>和谁一起</span>
          <select id="flKid">${s.kids.map(k =>
            `<option value="${k.id}">${UI.avatarText(k.avatar)} ${UI.esc(k.name)}</option>`).join('')}</select></label>
        <div class="switch-row">
          ${s.kinds.map((k, i) => `
            <button class="chip ${i === 0 ? 'on' : ''}" data-act="p-fl-kind"
              data-k="${k.code}">${k.e} ${UI.esc(k.n)}</button>`).join('')}
        </div>
        <label class="f" style="margin-top:12px"><span>多少分钟</span>
          <input id="flMin" type="number" value="20" min="1" max="240"></label>
        <label class="f"><span>记一句（可选）</span>
          <input id="flNote" placeholder="比如：一起读完了《小王子》第五章"></label>
        <button class="btn primary block lg" data-act="p-school-learn">登记这一次</button>
      </div>

      ${s.recent.length ? `
        <div class="sec-title"><h3>📖 最近记录</h3></div>
        <div class="card">
          ${s.recent.map(r => `
            <div class="row spread" style="padding:7px 0;border-bottom:1px dashed var(--line)">
              <div>
                <div style="font-weight:700">${r.kind_emoji} ${UI.esc(r.kind_name)}
                  <span class="small muted">· ${UI.esc(r.child)} 和 ${UI.esc(r.parent)}</span></div>
                ${r.note ? `<div class="small muted">${UI.esc(r.note)}</div>` : ''}
              </div>
              <div style="text-align:right">
                <b>${r.minutes} 分</b>
                <div class="small muted">${r.date}</div>
              </div>
            </div>`).join('')}
        </div>` : ''}`;
  }

  function articleCard(a) {
    return `
      <div class="card art-card">
        <div class="row spread">
          <b>${UI.esc(a.title)}</b>
          <span class="tag">${a.minutes} 分钟</span>
        </div>
        <p class="small muted" style="margin-top:6px">${UI.esc(a.summary)}</p>
        <ul class="bullets">
          ${(a.bullets || []).map(b => `<li>${UI.esc(b)}</li>`).join('')}
        </ul>
        <div class="try-box">
          <span class="small muted">今晚就能做的一件事</span>
          <div>${UI.esc(a.try_it)}</div>
        </div>
        <button class="btn ghost block sm" style="margin-top:10px"
          data-act="p-school-read" data-code="${a.code}">读完了 ✅</button>
      </div>`;
  }

  function empty(msg) {
    return `<div class="empty"><span class="ico">☕</span>${UI.esc(msg)}</div>`;
  }

  /* ------------------------------------------------ 交互 */
  const actions = {
    /* ---------------- 审批 */
    'p-approve'(el) {
      const kind = el.dataset.kind, id = +el.dataset.id;
      const def = +el.dataset.points;
      const isRedeem = kind === 'redeem';
      UI.sheet({
        title: '通过' + (isRedeem ? '兑换' : '加分'),
        body: `
          <p class="small muted">${UI.esc(el.dataset.title)}</p>
          ${isRedeem ? '<p class="small muted">核销之后星星币才会真正扣除。</p>' : `
          <label class="f" style="margin-top:10px"><span>实际给分（不能高于任务分值）</span>
            <input id="rvPoints" type="number" value="${def}" min="0" max="${Math.max(def * 2, def)}"></label>`}`,
        okText: isRedeem ? '确认已实现' : '确认并给分',
        onOk: async (wrap) => {
          const body = { id, action: 'approve' };
          if (!isRedeem) body.points = +wrap.querySelector('#rvPoints').value;
          const path = kind === 'task' ? '/api/parent/review/task'
            : kind === 'apply' ? '/api/parent/review/apply' : '/api/parent/review/redeem';
          try {
            const r = await API.post(path, body);
            if (r.capped) UI.toast(r.note || '今天这类星星币已到上限', 'err');
            else UI.toast(isRedeem ? '已核销，愿望实现 🎉' : `已给 +${r.awarded || body.points} 星`, 'ok');
            if (isRedeem) UI.celebrate('🎉', '愿望已兑现', '记得把礼物送到孩子手上');
            App.load();
          } catch (e) { UI.toast(e.message, 'err'); }
        }
      });
    },

    'p-reject'(el) {
      const kind = el.dataset.kind, id = +el.dataset.id;
      UI.sheet({
        title: '驳回原因',
        body: `<p class="small muted">驳回会立刻告诉孩子，请写一句他能看懂的理由。驳回不扣任何星星币。</p>
               <label class="f" style="margin-top:10px"><span>理由</span>
               <textarea id="rvReason" placeholder="比如：这次照片看不清楚，重拍一张"></textarea></label>`,
        okText: '驳回',
        danger: true,
        onOk: async (wrap) => {
          const reason = wrap.querySelector('#rvReason').value.trim();
          if (!reason) { UI.toast('请写一句理由', 'err'); return false; }
          const path = kind === 'task' ? '/api/parent/review/task'
            : kind === 'apply' ? '/api/parent/review/apply' : '/api/parent/review/redeem';
          try {
            await API.post(path, { id, action: 'reject', reason });
            UI.toast('已驳回');
            App.load();
          } catch (e) { UI.toast(e.message, 'err'); }
        }
      });
    },

    /* ---------------- 任务 */
    'p-task-new'() {
      UI.sheet({
        title: '发布新任务',
        body: taskForm(null, App.state.parent.tasks.kids),
        okText: '发布',
        onOk: async (wrap) => {
          const payload = collectTaskForm(wrap);
          if (!payload) return false;
          try {
            await API.post('/api/parent/task', payload);
            UI.toast('任务已发布');
            App.load();
          } catch (e) { UI.toast(e.message, 'err'); }
        }
      });
    },

    'p-task-edit'(el) {
      const t = App.state.parent.tasks.tasks.find(x => x.id === +el.dataset.id);
      UI.sheet({
        title: '修改任务',
        body: taskForm(t, App.state.parent.tasks.kids),
        okText: '保存',
        onOk: async (wrap) => {
          const payload = collectTaskForm(wrap);
          if (!payload) return false;
          try {
            await API.patch('/api/parent/task/' + el.dataset.id, payload);
            UI.toast('已保存');
            App.load();
          } catch (e) { UI.toast(e.message, 'err'); }
        }
      });
    },

    async 'p-task-stop'(el) {
      if (!await UI.confirm('停用这个任务？', '历史记录仍然保留，可以随时重新发布同样的任务')) return;
      await API.del('/api/parent/task/' + el.dataset.id);
      UI.toast('已停用');
      App.load();
    },

    /* ---------------- 愿望 */
    'p-wish-approve'(el) {
      const cur = +el.dataset.cost || 0;
      UI.sheet({
        title: cur ? '确认愿望' : '给愿望定星星币',
        body: `<p class="small muted">${cur
          ? '可以调整它需要的星星币数量，建议控制在 7 天到 1 个月之间能有希望达成。'
          : '孩子许愿时不填价格 —— 需要多少星星币由你来定。建议定在 7 天到 1 个月能有希望达成的量。'}</p>
               <label class="f" style="margin-top:10px"><span>需要星星币</span>
               <input id="wvCost" type="number" value="${cur || ''}" placeholder="${cur || '比如 150'}" min="1"></label>`,
        okText: cur ? '确认' : '定好啦',
        onOk: async (wrap) => {
          const cost = +wrap.querySelector('#wvCost').value;
          if (!cost || cost < 1) { UI.toast('填一个大于 0 的星星币数量', 'err'); return false; }
          try {
            await API.post('/api/parent/wish/review', {
              wish_id: +el.dataset.id, action: 'approve', cost_coin: cost
            });
            UI.toast('愿望已确认');
            App.load();
          } catch (e) { UI.toast(e.message, 'err'); }
        }
      });
    },

    'p-wish-cost'(el) {
      const cur = +el.dataset.cost || 0;
      UI.sheet({
        title: '调整星星币数量',
        body: `<p class="small muted">改价立刻生效。孩子已经攒的星星币不会变，只是进度条会跟着更新。</p>
               <label class="f" style="margin-top:10px"><span>需要星星币</span>
               <input id="wcCost" type="number" value="${cur}" min="1"></label>`,
        okText: '保存',
        onOk: async (wrap) => {
          const cost = +wrap.querySelector('#wcCost').value;
          if (!cost || cost < 1) { UI.toast('填一个大于 0 的星星币数量', 'err'); return false; }
          if (cost === cur) return true;
          try {
            await API.patch('/api/parent/wish/' + el.dataset.id, { cost_coin: cost });
            UI.toast('已改为 ' + cost + ' 星');
            App.load();
          } catch (e) { UI.toast(e.message, 'err'); }
        }
      });
    },

    'p-wish-reject'(el) {
      UI.sheet({
        title: '不适合的原因',
        body: `<label class="f"><span>理由</span><textarea id="wvReason" placeholder="比如：这个太贵啦，我们换个 100 星的？"></textarea></label>`,
        okText: '驳回愿望',
        danger: true,
        onOk: async (wrap) => {
          const reason = wrap.querySelector('#wvReason').value.trim();
          if (!reason) { UI.toast('写一句理由', 'err'); return false; }
          await API.post('/api/parent/wish/review',
            { wish_id: +el.dataset.id, action: 'reject', reason });
          UI.toast('已处理');
          App.load();
        }
      });
    },

    /* ---------------- 其它 */
    'p-grant'(el) {
      UI.sheet({
        title: '给 ' + UI.esc(el.dataset.nm) + ' 加分',
        body: `
          <label class="f"><span>分数</span><input id="gPoints" type="number" value="5" min="1" max="50"></label>
          <label class="f"><span>理由</span><input id="gNote" placeholder="比如：今天主动帮奶奶拎东西"></label>`,
        okText: '给分',
        onOk: async (wrap) => {
          try {
            const r = await API.post('/api/parent/grant', {
              kid_id: +el.dataset.id,
              points: +wrap.querySelector('#gPoints').value,
              note: wrap.querySelector('#gNote').value.trim()
            });
            UI.toast(r.capped ? '已到今日上限，只入了部分分数' : `已给 +${r.granted} 星`, r.capped ? 'err' : 'ok');
            App.load();
          } catch (e) { UI.toast(e.message, 'err'); }
        }
      });
    },

    'p-kid-new'() {
      UI.sheet({
        title: '添加孩子',
        body: `
          <label class="f"><span>昵称</span><input id="kName" placeholder="比如：豆豆"></label>
          <label class="f"><span>头像（用 emoji）</span><input id="kAvatar" value="🙂" maxlength="4"></label>
          <label class="f"><span>出生年份</span><input id="kYear" type="number" value="${new Date().getFullYear() - 7}"></label>
          <label class="f"><span>登录口令（4 位以上）</span><input id="kPin" type="password" placeholder="让孩子自己想一个"></label>`,
        okText: '添加',
        onOk: async (wrap) => {
          try {
            await API.post('/api/parent/kid', {
              name: wrap.querySelector('#kName').value.trim(),
              avatar: wrap.querySelector('#kAvatar').value.trim() || '🙂',
              birth_year: +wrap.querySelector('#kYear').value,
              pin: wrap.querySelector('#kPin').value
            });
            UI.toast('已添加');
            App.load();
          } catch (e) { UI.toast(e.message, 'err'); }
        }
      });
    },

    /* ---------------- 界面与账号 */
    async 'p-brand'() {
      const cur = App.BRAND;
      UI.sheet({
        title: '改名字和图标',
        body: `
          <p class="small muted">改完立刻生效，左上角、标题栏、登录页都会变。</p>
          <label class="f"><span>系统名字</span><input id="apName" maxlength="20" value="${UI.esc(cur.name)}"></label>
          <label class="f"><span>副标题（登录页）</span><input id="apSub" maxlength="40" value="${UI.esc(cur.subtitle)}"></label>
          <label class="f"><span>图标（emoji）</span><input id="apLogo" maxlength="4" value="${UI.esc(cur.logo)}"></label>`,
        okText: '保存',
        onOk: async (wrap) => {
          try {
            const info = await API.put('/api/parent/app-info', {
              name: wrap.querySelector('#apName').value.trim(),
              subtitle: wrap.querySelector('#apSub').value.trim(),
              logo: wrap.querySelector('#apLogo').value.trim(),
            });
            Object.assign(App.BRAND, info);
            App.applyBrand();
            UI.toast('已更新', 'ok');
            App.load();
          } catch (e) { UI.toast(e.message, 'err'); return false; }
        }
      });
    },

    async 'p-my-profile'() {
      let me = {};
      try { me = await API.get('/api/account/profile'); } catch (e) { UI.toast(e.message, 'err'); return; }
      const wrap = UI.sheet({
        title: '我的资料',
        body: `
          <div style="display:flex;justify-content:center;margin-bottom:10px">
            <div id="mpAv" style="cursor:pointer">${UI.avatarBlock(me.avatar, 72)}</div>
          </div>
          <label class="f"><span>显示的名字（可以写「豆豆爸爸」）</span><input id="mpName" maxlength="10" value="${UI.esc(me.name)}"></label>
          <label class="f"><span>登录用户名</span><input id="mpUser" value="${UI.esc(me.username)}"></label>
          <p class="small muted" style="margin-top:8px">想改口令就填下面两行，不填就不改。</p>
          <label class="f"><span>现在的口令</span><input id="mpOld" type="password" placeholder="不修改就留空"></label>
          <label class="f"><span>新口令</span><input id="mpNew" type="password" placeholder="至少 4 位"></label>`,
        okText: '保存',
        onOk: async (w) => {
          try {
            await API.patch('/api/account/profile', {
              name: w.querySelector('#mpName').value.trim(),
              username: w.querySelector('#mpUser').value.trim(),
              avatar: AV_NOW,
              old_pin: w.querySelector('#mpOld').value,
              new_pin: w.querySelector('#mpNew').value,
            });
            UI.toast('已保存', 'ok');
            App.load();
          } catch (e) { UI.toast(e.message, 'err'); return false; }
        }
      });
      let AV_NOW = me.avatar;
      wrap.querySelector('#mpAv').onclick = () => UI.pickAvatar(AV_NOW, (v) => {
        AV_NOW = v;
        wrap.querySelector('#mpAv').innerHTML = UI.avatarBlock(v, 72);
      });
    },

    async 'p-member-edit'(el) {
      const id = +el.dataset.id, role = el.dataset.role;
      const list = App.state.parent.members.members;
      const m = list.find(x => x.id === id) || {};
      if (role !== 'child') { actions['p-my-profile'](); return; }

      const wrap = UI.sheet({
        title: '编辑 ' + UI.esc(m.name),
        body: `
          <div style="display:flex;justify-content:center;margin-bottom:10px">
            <div id="kdAv" style="cursor:pointer">${UI.avatarBlock(m.avatar, 72)}</div>
          </div>
          <label class="f"><span>昵称</span><input id="kdName" maxlength="10" value="${UI.esc(m.name)}"></label>
          <label class="f"><span>出生年份</span><input id="kdYear" type="number" value="${m.birth_year || ''}"></label>
          <label class="f"><span>界面风格</span><select id="kdUi">
            ${[['childish', '童趣（默认）'], ['normal', '清爽'], ['plain', '极简']]
              .map(x => `<option value="${x[0]}" ${x[0] === m.ui_mode ? 'selected' : ''}>${x[1]}</option>`).join('')}
          </select></label>
          <label class="f"><span>登录口令（留空表示不改）</span><input id="kdPin" type="password" placeholder="4 位以上"></label>`,
        okText: '保存',
        onOk: async (w) => {
          try {
            await API.put(`/api/parent/kid/${id}`, {
              name: w.querySelector('#kdName').value.trim(),
              birth_year: +w.querySelector('#kdYear').value || 0,
              ui_mode: w.querySelector('#kdUi').value,
              pin: w.querySelector('#kdPin').value,
              avatar: KD_AV,
            });
            UI.toast('已保存', 'ok');
            App.load();
          } catch (e) { UI.toast(e.message, 'err'); return false; }
        }
      });
      let KD_AV = m.avatar;
      wrap.querySelector('#kdAv').onclick = () => UI.pickAvatar(KD_AV, (v) => {
        KD_AV = v;
        wrap.querySelector('#kdAv').innerHTML = UI.avatarBlock(v, 72);
      });
    },

    async 'p-subjects'() {
      let rows = [];
      try { rows = (await API.get('/api/parent/wrong/subjects')).subjects || []; }
      catch (e) { UI.toast(e.message, 'err'); return; }
      UI.sheet({
        title: '错题科目',
        body: `
          <p class="small muted">一行一个科目。删除科目不会删题，那些题会被归到「其它」。</p>
          <div id="subRows">
            ${rows.map(s => `
              <div class="row sub-row" style="gap:6px;margin-top:8px">
                <input class="s-icon" value="${UI.esc(s.icon)}" maxlength="4" style="width:58px">
                <input class="s-name" value="${UI.esc(s.name)}" placeholder="科目名">
                <input class="s-code" value="${UI.esc(s.code)}" placeholder="代号(英文)" style="width:110px">
                <button class="btn r sm" data-act="p-sub-del">删</button>
              </div>`).join('')}
          </div>
          <button class="btn ghost block sm" style="margin-top:10px" data-act="p-sub-add">＋ 加一个科目</button>`,
        okText: '保存',
        onOk: async (wrap) => {
          const list = [...wrap.querySelectorAll('.sub-row')].map((r, i) => ({
            icon: r.querySelector('.s-icon').value.trim() || '📌',
            name: r.querySelector('.s-name').value.trim(),
            code: r.querySelector('.s-code').value.trim().toLowerCase(),
          })).filter(x => x.name);
          if (!list.length) { UI.toast('至少要留一个科目', 'err'); return false; }
          try {
            await API.put('/api/parent/wrong/subjects', { subjects: list });
            UI.toast('已保存', 'ok');
            App.load();
          } catch (e) { UI.toast(e.message, 'err'); return false; }
        }
      });
    },

    'p-sub-add'() {
      const box = document.getElementById('subRows');
      const div = document.createElement('div');
      div.className = 'row sub-row';
      div.style.cssText = 'gap:6px;margin-top:8px';
      div.innerHTML = `
        <input class="s-icon" value="📌" maxlength="4" style="width:58px">
        <input class="s-name" placeholder="科目名">
        <input class="s-code" placeholder="代号(英文)" style="width:110px">
        <button class="btn r sm" data-act="p-sub-del">删</button>`;
      box.appendChild(div);
    },

    'p-sub-del'(el) { el.closest('.sub-row').remove(); },

    /* ---------------- 错题汇总操作 */
    'wbk-kid'(el) { WBK.kid_id = +el.value; WBK.ids = []; App.load(); },
    'wbk-subject'(el) { WBK.subject = el.value; App.load(); },
    'wbk-status'(el) { WBK.status = el.value; App.load(); },

    'w-pick'(el) {
      const id = +el.dataset.id;
      WBK.ids = el.checked ? [...new Set([...WBK.ids, id])] : WBK.ids.filter(x => x !== id);
    },

    'w-clear-pick'() { WBK.ids = []; App.load(); },

    async 'w-renumber'() {
      try { await API.post(`/api/parent/kid/${WBK.kid_id}/wrong/renumber`, {}); UI.toast('已按顺序整理'); App.load(); }
      catch (e) { UI.toast(e.message, 'err'); }
    },

    async 'w-move'(el) {
      try {
        await API.post(`/api/parent/wrong/${el.dataset.id}/move?dir=${el.dataset.dir}`, {});
        App.load();
      } catch (e) { UI.toast(e.message, 'err'); }
    },

    async 'w-del'(el) {
      if (!await UI.confirm('删除这道题', '删掉之后孩子就看不到它了', true)) return;
      try { await API.del(`/api/parent/wrong/${el.dataset.id}`); UI.toast('已删除'); App.load(); }
      catch (e) { UI.toast(e.message, 'err'); }
    },

    'w-edit'(el) {
      const s = App.state.parent.wrong;
      let it = null;
      (s.groups || []).forEach(g => { g.items.forEach(x => { if (x.id === +el.dataset.id) it = x; }); });
      if (!it) return;
      UI.sheet({
        title: '编辑错题',
        body: `
          <label class="f"><span>科目</span><select id="weS">
            ${(s.subjects || []).map(x => `<option value="${UI.esc(x.code)}" ${x.code === it.subject ? 'selected' : ''}>${x.icon} ${UI.esc(x.name)}</option>`).join('')}
          </select></label>
          <label class="f"><span>题目</span><input id="weQ" value="${UI.esc(it.question)}"></label>
          <label class="f"><span>正确答案</span><input id="weA" value="${UI.esc(it.correct_answer)}"></label>
          <label class="f"><span>孩子写的答案</span><input id="weW" value="${UI.esc(it.wrong_answer)}"></label>
          <label class="f"><span>做错的原因</span><select id="weC">
            <option value="">还没填</option>
            ${[['careless', '粗心大意'], ['misread', '看错题目'], ['calc', '算错了'],
               ['unknown', '真的不会'], ['slow', '没做完'], ['other', '其它']]
              .map(c => `<option value="${c[0]}" ${c[0] === it.cause ? 'selected' : ''}>${c[1]}</option>`).join('')}
          </select></label>
          <label class="f"><span>知识点</span><input id="weT" value="${UI.esc(it.tag)}" placeholder="比如：进位加法"></label>
          <label class="f"><span>讲一遍的思路（解析）</span><textarea id="weE">${UI.esc(it.explain)}</textarea></label>`,
        okText: '保存',
        onOk: async (wrap) => {
          try {
            await API.patch(`/api/parent/wrong/${it.id}`, {
              subject: wrap.querySelector('#weS').value,
              question: wrap.querySelector('#weQ').value.trim(),
              correct_answer: wrap.querySelector('#weA').value.trim(),
              wrong_answer: wrap.querySelector('#weW').value.trim(),
              cause: wrap.querySelector('#weC').value,
              tag: wrap.querySelector('#weT').value.trim(),
              explain: wrap.querySelector('#weE').value.trim(),
            });
            UI.toast('已保存', 'ok');
            App.load();
          } catch (e) { UI.toast(e.message, 'err'); return false; }
        }
      });
    },

    'w-export'() {
      const ans = document.getElementById('wbkAns');
      const v = document.getElementById('wbkVar');
      WBK.answers = ans ? (ans.checked ? 1 : 0) : 1;
      WBK.variants = v && v.checked ? 1 : 0;
      location.href = '/api/parent/wrong/export?' + WBK.q();
      UI.toast('正在生成 Word…');
    },

    'w-print'() {
      const ans = document.getElementById('wbkAns');
      const v = document.getElementById('wbkVar');
      WBK.answers = ans ? (ans.checked ? 1 : 0) : 1;
      WBK.variants = v && v.checked ? 1 : 0;
      const s = App.state.parent.wrong;
      printWrongSheet(s, WBK.answers, WBK.variants);
    },

    /* ---------------- 规则编辑器 */
    'p-lv-add'() {
      const box = document.getElementById('lvBox');
      const rows = box.querySelectorAll('.lv-row');
      const last = [...box.querySelectorAll('.lv-exp')].pop();
      const suggest = (+last.value || 0) + 500;
      const div = document.createElement('div');
      div.className = 'lv-row';
      div.innerHTML = `
        <div class="no">Lv${rows.length + 1}</div>
        <input class="lv-title" placeholder="称号">
        <input class="lv-exp" type="number" value="${suggest}">
        <input class="lv-perk perk" placeholder="解锁的真实特权">
        <button class="btn ghost sm del" data-act="p-lv-del">删除</button>`;
      box.appendChild(div);
      UI.toast('已添加，记得给它配一个真实特权');
    },

    'p-lv-del'(el) {
      el.closest('.lv-row').remove();
      [...document.querySelectorAll('#lvBox .lv-row')].forEach((row, i) => {
        row.querySelector('.no').textContent = 'Lv' + (i + 1);
      });
    },

    'p-rules-save'() {
      const v = (id) => document.getElementById(id).value;
      const n = (id) => +document.getElementById(id).value || 0;
      const c = (id) => document.getElementById(id).checked;
      const g0 = (App.state.parent.rules.games || [])[0] || {};

      const payload = {
        currency: { coin_name: v('rcCoin').trim() || '星星币', exp_name: v('rcExp').trim() || '成长值' },
        daily_cap: {
          study: n('dcStudy'), exercise: n('dcExercise'), chore: n('dcChore'),
          habit: n('dcHabit'), game: n('dcGame'), garden: n('dcGarden'),
        },
        streak_bonus: [...document.querySelectorAll('.sbRow')]
          .map(x => ({ days: +x.dataset.days, points: +x.value || 0 })),
        streak_shield_per_month: n('shShield'),
        levels: [...document.querySelectorAll('#lvBox .lv-row')].map((row, i) => ({
          level: i + 1,
          title: row.querySelector('.lv-title').value.trim() || `第${i + 1}级`,
          exp: +row.querySelector('.lv-exp').value || 0,
          perk: row.querySelector('.lv-perk').value.trim(),
        })),
        gating: { game_daily_play_limit: n('gLimit'), game_unlock_after_study: c('gUnlock') },
        application: {
          enabled: c('apEnabled'), daily_limit: n('apDaily'),
          max_points_per_apply: n('apMax'), require_evidence: c('apEvidence'),
          count_into_daily_cap: c('apCap'), expire_days: n('apExpire'),
        },
        redemption: { auto_approve_below: n('rdAuto') },
        garden: {
          enabled: c('gdEnabled'), water_cooldown_min: n('gdCool'),
          yield_rate: +v('gdYield') || 1.2, slots_base: n('gdSlots'),
        },
        pomodoro: {
          enabled: c('pdEnabled'), daily_limit: n('pdLimit'),
          points_per_pomodoro: n('pdPoints'),
        },
        words: {
          enabled: c('wdEnabled'), new_per_day: n('wdPer'),
          daily_round_limit: n('wdLimit'),
        },
        pet: { enabled: c('ptEnabled'), feed_cost: n('ptFeed') },
        games: [{
          code: g0.code || 'math', name: g0.name || '速算闯关', icon: g0.icon || '🧠',
          desc: g0.desc || '', enabled: c('gEnabled'), questions: n('gQuestions'),
          points_per_correct: n('gPer'), clear_bonus: n('gClear'),
          time_limit: n('gTime'), ops: g0.ops || ['+', '-'], range_max: g0.range_max || 20,
        }],
      };

      UI.sheet({
        title: '保存规则',
        body: `<p class="small muted">规则会立刻生效；如果等级门槛变了，孩子的等级会当场重算。</p>
               <p class="small muted" style="margin-top:8px">建议先按默认值用两周，再根据实际数据微调 ——
               分给少了往上加孩子很高兴，给多了往回收会引发抵触。</p>`,
        okText: '确认保存',
        onOk: async () => {
          try {
            const r = await API.put('/api/parent/rules', payload);
            UI.toast('规则已保存并生效', 'ok');
            if (r.levels_changed && r.levels_changed.length) {
              const s = r.levels_changed.map(x => `${x.name} Lv${x.from}→Lv${x.to}`).join('、');
              UI.celebrate('🎖️', '等级已重新计算', s);
            }
            App.load('rules');
          } catch (e) { UI.toast(e.message, 'err'); }
        }
      });
    },

    /* ---- 家长学堂 ---- */
    async 'p-school-read'(el) {
      try {
        await API.post('/api/parent/school/read', { code: el.dataset.code });
        UI.toast('已标记为读过 📚', 'ok');
        App.load();
      } catch (e) { UI.toast(e.message, 'err'); }
    },

    async 'p-school-topic'(el) {
      const topic = el.dataset.topic;
      try {
        const r = await API.get('/api/parent/school/articles?topic=' + topic + '&depth=1');
        UI.sheet({
          title: '全部内容',
          body: `<div>${r.articles.map(articleCard).join('')}</div>`,
          cancelText: '关闭'
        });
        // 弹层里的按钮复用同一套事件委托
        const root = document.querySelector('.sheet');
        if (root) root.addEventListener('click', (e) => {
          const b = e.target.closest('[data-act="p-school-read"]');
          if (!b) return;
          e.preventDefault();
          ParentViews.actions['p-school-read'](b).then(() => UI.close());
        });
      } catch (e) { UI.toast(e.message, 'err'); }
    },

    'p-fl-kind'(el) {
      SC.kind = el.dataset.k;
      [...document.querySelectorAll('.switch-row .chip')]
        .forEach(c => c.classList.toggle('on', c === el));
    },

    async 'p-school-learn'() {
      const kidSel = document.getElementById('flKid');
      const minutes = +document.getElementById('flMin').value || 20;
      const note = document.getElementById('flNote').value.trim();
      if (!kidSel || !kidSel.value) { UI.toast('先选一个孩子', 'err'); return; }
      try {
        const r = await API.post('/api/parent/school/family-learn',
          { child_id: +kidSel.value, kind: SC.kind, minutes, note });
        UI.toast(`已记录 ${r.minutes} 分钟 · 本周累计 ${r.week_minutes} 分 🤝`, 'ok');
        App.load();
      } catch (e) { UI.toast(e.message, 'err'); }
    },

    async 'p-rules-raw'() {
      const r = await API.get('/api/parent/rules/raw');
      UI.sheet({
        title: 'YAML 原文',
        body: `<textarea id="rvText" style="min-height:380px;font-family:Consolas,monospace;font-size:12.5px">${UI.esc(r.text)}</textarea>`,
        okText: '保存原文',
        onOk: async (wrap) => {
          try {
            await API.post('/api/parent/rules/raw', { text: wrap.querySelector('#rvText').value });
            UI.toast('已保存');
            App.load('rules');
          } catch (e) { UI.toast(e.message, 'err'); return false; }
        }
      });
    },

    async 'p-report'(el) {
      const r = await API.get('/api/parent/report?kid_id=' + el.dataset.id + '&days=14');
      UI.sheet({
        title: UI.esc(r.kid.name) + ' · 近 14 天',
        body: `
          <div class="stat-row">
            <div class="s"><b>${r.total_earned}</b><span>累计获得</span></div>
            <div class="s"><b>${r.available}</b><span>可用</span></div>
            <div class="s"><b>${r.exp}</b><span>成长值</span></div>
            <div class="s"><b>${r.avg7}</b><span>日均</span></div>
          </div>
          <div class="small muted" style="margin-bottom:6px">分类分布</div>
          ${r.by_category.map(c => `
            <div class="row spread" style="padding:5px 0">
              <span>${{ study: '学习', exercise: '运动', chore: '家务', habit: '习惯', game: '游戏' }[c.category] || c.category}</span>
              <b>${c.coin} 星</b>
            </div>`).join('')}
          <div class="small muted" style="margin:10px 0 6px">每日明细</div>
          ${r.daily.filter(d => d.coin !== 0).slice(-7).map(d => `
            <div class="row spread" style="padding:5px 0;border-bottom:1px dashed var(--line)">
              <span class="small">${d.date}</span><b class="plus">+${d.coin}</b>
            </div>`).join('') || '<p class="small muted">近 7 天没有记录</p>'}`,
        okText: '关闭'
      });
    },
  };

  /* ------------------------------------------------ 打印：错题练习卷
     单独开一个窗口打印，排版和 Word 版一致：
     前面只有题面和留白，后面才是答案与解析。 */
  function printWrongSheet(s, withAnswers, withVariants) {
    const groups = s.groups || [];
    const kid = s.child || {};
    const esc = UI.esc;
    const lines = (it) => (it.variants || []).map(v =>
      `<div class="v">同类练一练：${esc(v.prompt || v.question)}</div>`).join('');

    const html = `<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>${esc(kid.name)} 错题重做 ${esc(s.generated_at)}</title>
<style>
  @page { size: A4; margin: 18mm 16mm; }
  * { box-sizing: border-box; }
  body { font-family: "Microsoft YaHei", "PingFang SC", sans-serif; color:#222; line-height:1.7; }
  h1 { font-size: 22px; text-align: center; margin: 0 0 4px; }
  .info { text-align:center; font-size:12px; color:#666; margin-bottom: 6px; }
  .hd { border-bottom: 1px solid #ddd; padding-bottom: 4px; margin: 14px 0 4px; }
  .fill { border-bottom: 1px dashed #999; display:inline-block; min-width: 60px; }
  h2 { font-size: 15px; margin: 16px 0 6px; }
  ol { margin: 0; padding-left: 22px; }
  li { margin-bottom: 10px; font-size: 15px; }
  li > .writespace { display:block; color:#bbb; letter-spacing: 2px; }
  .meta { font-size: 11px; color:#999; }
  .seq { color:#bbb; font-size:10px; }
  .v { font-size: 13px; color:#5b4bd6; margin-top: 2px; }
  .part { page-break-before: always; }
  .sig { margin-top: 10px; font-size: 12px; color:#666; text-align: center; }
</style></head><body>
<h1>${esc(kid.name)} · 错题重做练习</h1>
<div class="info">${esc(s.generated_at)} 生成 · 共 ${s.total} 题 ·
  姓名：<span class="fill" style="min-width:90px"></span>
  日期：<span class="fill" style="min-width:70px"></span>
  用时：<span class="fill" style="min-width:50px"></span></div>
<div class="sig">先做完所有的题，再翻到最后的参考答案。不会的做个记号，讲完再抄一遍。</div>
${groups.map((g, gi) => `
  <h2>${'一二三四五六七八九十'[gi] || (gi + 1)}、${esc(g.name)}（${g.count} 题）</h2>
  <ol>${g.items.map(it => `
    <li>${esc(it.prompt || it.question)}
      <span class="meta">${it.tag ? esc(it.tag) + ' · ' : ''}${it.cause_name ? esc(it.cause_name) + ' · ' : ''}${it.times_wrong > 1 ? '之前错 ' + it.times_wrong + ' 次' : ''}
        <span class="seq">${esc(it.seq)}</span></span>
      <span class="writespace">＿＿＿＿＿＿＿＿＿＿</span>
      ${withVariants ? lines(it) : ''}
    </li>`).join('')}</ol>`).join('')}
${withAnswers ? `<div class="part"><h2 style="font-size:20px">参考答案与解析</h2>
${groups.map((g, gi) => `
  <h2>${'一二三四五六七八九十'[gi] || (gi + 1)}、${esc(g.name)}</h2>
  <ol>${g.items.map(it => `
    <li>${esc(it.question)} <b>${esc(it.correct_answer)}</b>
      <span class="meta">${it.wrong_answer ? '（之前写成 ' + esc(it.wrong_answer) + '）' : ''}
        ${it.cause_name ? '｜' + esc(it.cause_name) : ''} <span class="seq">${esc(it.seq)}</span></span>
      ${(it.variants || []).length && withVariants
        ? `<div class="v">${it.variants.map(v => `${esc(v.question)} ${esc(v.correct_answer)}`).join(' ｜ ')}</div>` : ''}
      ${it.explain ? `<div class="meta">解析：${esc(it.explain)}</div>` : ''}
    </li>`).join('')}</ol>`).join('')}</div>` : ''}
</body></html>`;

    const w = window.open('', '_blank');
    if (!w) { UI.toast('弹窗被拦住了，请允许弹出窗口', 'err'); return; }
    w.document.write(html);
    w.document.close();
    setTimeout(() => { w.focus(); w.print(); }, 400);
  }

  function collectTaskForm(wrap) {
    const name = wrap.querySelector('#tName').value.trim();
    if (!name) { UI.toast('任务名称不能为空', 'err'); return null; }
    return {
      name,
      icon: wrap.querySelector('#tIcon').value.trim() || '✅',
      points: +wrap.querySelector('#tPoints').value || 5,
      category: wrap.querySelector('#tCat').value,
      repeat_type: wrap.querySelector('#tRepeat').value,
      repeat_rule: [...wrap.querySelectorAll('.tDay:checked')].map(x => +x.value),
      assignee_ids: [...wrap.querySelectorAll('.tKid:checked')].map(x => +x.value),
      display_zone: wrap.querySelector('#tZone').value,
      need_approval: wrap.querySelector('#tApprove').checked,
      need_photo: wrap.querySelector('#tPhoto').checked,
      effective_from: wrap.querySelector('#tFrom').value || null,
      effective_to: wrap.querySelector('#tTo').value || null,
    };
  }

  function reportDto(r) { return r; }

  return { todo, tasks, wishes, school, wrongbook, more, rules, actions };
})();
