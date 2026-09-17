// Injected into every document, including cross-origin embeds.
// Python owns all state; this draws it and sends back intent.
(() => {
  if (window.__vk_injected) return;
  window.__vk_injected = true;

  // --- element picker, active in EVERY frame ---
  let armed = null, target = null, box = null, tag = null, replaying = false;
  let root_ref = null;  // panel shadow root, top frame only

  const ensure = () => {
    if (box) return;
    box = document.createElement('div');
    box.style.cssText = 'position:fixed;pointer-events:none;z-index:2147483646;' +
      'border:2px solid #8ab4f8;background:rgba(138,180,248,.16);display:none;border-radius:3px';
    tag = document.createElement('div');
    tag.style.cssText = 'position:fixed;pointer-events:none;z-index:2147483647;' +
      'background:#8ab4f8;color:#14161a;font:12px/1.4 ui-monospace,Menlo,monospace;' +
      'padding:3px 8px;border-radius:4px;max-width:360px;overflow:hidden;' +
      'text-overflow:ellipsis;white-space:nowrap;display:none;font-weight:600';
    document.documentElement.append(box, tag);
  };

  const show = (el) => {
    if (!el || !el.getBoundingClientRect) return;
    ensure();
    const r = el.getBoundingClientRect();
    Object.assign(box.style, {display:'block', left:r.left+'px', top:r.top+'px',
                              width:r.width+'px', height:r.height+'px'});
    tag.textContent = armed === 'url'
      ? '▶ ' + el.tagName.toLowerCase() + ' — click to use this video'
      : ((el.innerText || '').trim().replace(/\s+/g,' ').slice(0,60) || '(no text)');
    Object.assign(tag.style, {display:'block', left:r.left+'px',
                              top:(r.top > 26 ? r.top - 24 : r.bottom + 5) + 'px'});
  };
  const hide = () => { if (box) box.style.display='none'; if (tag) tag.style.display='none'; };

  const isPanel = (el) => el && el.id === '__vk_host';

  document.addEventListener('mousemove', (e) => {
    if (!armed) return;
    if (isPanel(e.target)) { hide(); target = null; return; }
    target = e.target; show(target);
  }, true);

  // Keep the focused field focused when you click the page: focus moves on mousedown,
  // so suppressing it there is what keeps the field armed through the pick.
  document.addEventListener('mousedown', (e) => {
    if (armed && target && !isPanel(e.target)) e.preventDefault();
  }, true);

  document.addEventListener('click', (e) => {
    if (replaying || !armed || !target || isPanel(e.target)) return;
    e.preventDefault(); e.stopPropagation(); e.stopImmediatePropagation();
    const el = target;
    if (armed === 'url') {
      window.vkPick(el.tagName, {frame: location.href, player: true,
                                 ownFrame: window.top !== window.self});
      replaying = true;
      setTimeout(() => { el.click(); replaying = false; }, 0);
    } else {
      window.vkPick((el.innerText || '').trim().replace(/\s+/g,' ') || null,
                    {frame: location.href, player: false});
    }
  }, true);

  document.addEventListener('keydown', (e) => {
    if (armed && e.key === 'Escape') {
      window.vkArm(null);
      const f = root_ref && root_ref.querySelector('input.armed');
      if (f) f.blur();
    }
  }, true);

  window.__vk_setArmed = (field) => {
    armed = field;
    if (!field) { hide(); target = null; }
    const root = document.documentElement;
    if (root) root.style.setProperty('cursor', field ? 'crosshair' : '', 'important');
  };

  if (window.top !== window.self) return;  // only the top frame draws the panel

  const boot = () => {
    if (!document.documentElement) return;
    const host = document.createElement('div');
    host.id = '__vk_host';
    host.style.cssText = 'position:fixed;top:0;right:0;z-index:2147483647;';
    document.documentElement.appendChild(host);
    const root = host.attachShadow({mode:'open'});
    root_ref = root;
    root.innerHTML = `
      <style>
        *{box-sizing:border-box}
        .p{width:440px;height:100vh;overflow-y:auto;background:#14161a;color:#e8e8ea;
           font:13px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;padding:16px;
           border-left:1px solid #2a2e35}
        h1{font-size:12px;margin:0 0 14px;color:#8ab4f8;letter-spacing:.12em;font-weight:600}
        .sec{font-size:11px;color:#5f6368;letter-spacing:.08em;margin:18px 0 7px;
             text-transform:uppercase}
        .r{display:flex;align-items:center;gap:5px;margin:5px 0}
        label{width:62px;color:#9aa0a6;flex:none}
        input{flex:1;min-width:0;background:#1d2026;color:#e8e8ea;border:1px solid #2a2e35;
              padding:7px 9px;border-radius:4px;font:inherit}
        input:focus{outline:none;border-color:#8ab4f8}
        input.armed{border-color:#f28b82;box-shadow:0 0 0 1px #f28b82}
        .picking{color:#f28b82;font-size:11px;margin:10px 0 0;min-height:16px}
        .warn{color:#fdd663;font-size:11px;min-height:15px;padding-left:67px}
        .sug{margin:0 0 0 67px}
        .sug:empty{display:none}
        .s{display:block;width:100%;text-align:left;padding:6px 9px;margin:3px 0;
           font-size:12px;background:#1a1d23;border:1px solid #2a2e35;color:#9aa0a6}
        .s:hover,.s.top{background:#2b3340;color:#e8e8ea;border-color:#3d4654}
        .s em{font-style:normal;color:#8ab4f8;font-weight:700}
        .s u{text-decoration:none;color:#fdd663;font-weight:700;
             border-bottom:2px dotted #fdd663}
        .s .cs{float:right;color:#fdd663;font-size:10px;margin-left:8px}
        .s .k{float:right;color:#5f6368;font-size:10px}
        input.bad{border-color:#fdd663}
        button{background:#252932;color:#9aa0a6;border:1px solid #363b45;border-radius:4px;
               cursor:pointer;font:inherit}
        button:hover{background:#333944;color:#e8e8ea}
        .t{width:32px;height:32px;flex:none;font-size:11px;padding:0}
        .t.on{background:#8ab4f8;color:#14161a;border-color:#8ab4f8;font-weight:700}
        .t.armed{background:#f28b82;color:#14161a;border-color:#f28b82;font-weight:700}
        .url{font-size:11px;color:#81c995;word-break:break-all;margin:8px 0 0;
             padding:8px 10px;background:#1a1f1b;border-radius:4px;line-height:1.45}
        .url.empty{color:#5f6368;background:#1a1b1e}
        .acts{display:flex;flex-direction:column;gap:6px;margin-top:8px}
        .acts button{padding:11px 12px;text-align:left;font-size:13px}
        .acts button b{color:#e8e8ea;font-weight:600}
        .acts button:disabled:hover{background:#252932;color:#9aa0a6}
        .acts button span{color:#5f6368;font-size:11px;float:right;line-height:1.5}
        #b_lang{border-color:#4a5a6e} #b_lang:hover{background:#2b3a4a}
        #b_upd{background:#8ab4f8;color:#14161a;border-color:#8ab4f8}
        #b_upd b{color:#14161a}
        #b_video{background:#8ab4f8;color:#14161a;border-color:#8ab4f8}
        #b_video b{color:#14161a} #b_video span{color:#2a4060}
        #b_video:hover{background:#a6c8ff}
        .foot{display:flex;gap:6px;margin-top:14px}
        .foot button{flex:1;padding:9px}
        #fin{background:#2d4a34;border-color:#3d6344;color:#c8e6c9}
        #fin:hover{background:#3a5c42}
        .tabs{float:right;text-transform:none;letter-spacing:0}
        .tab{padding:2px 9px;font-size:11px;border-radius:3px;margin-left:3px}
        .tab.on{background:#8ab4f8;color:#14161a;border-color:#8ab4f8;font-weight:700}
        .lg .c{display:inline-block;padding:1px 6px;margin-left:3px;border-radius:3px;
               background:#1f2b22;border:1px solid #2f4536;color:#81c995;cursor:pointer;
               font-size:11px}
        .lg .c:hover{background:#2f4536;color:#b9f6ca}
        .lg .c.ed{background:#f28b82;border-color:#f28b82;color:#14161a;font-weight:700}
        .fdir{color:#8ab4f8;font-weight:600;font-size:12px;margin-top:6px}
        .ffile{font-size:12px;color:#e8e8ea;padding:3px 0;word-break:break-all}
        .ftr{color:#5f6368;font-size:11px}
        .edbar{background:#3a2c2c;border:1px solid #f28b82;border-radius:4px;
               padding:8px 10px;margin-bottom:10px;color:#f28b82;font-size:12px}
        .grp{color:#8ab4f8;font-size:12px;margin:12px 0 4px;font-weight:600}
        .it{display:flex;align-items:center;gap:8px;padding:5px 0;
            border-bottom:1px solid #1d2026;font-size:12px}
        .it .n{color:#5f6368;flex:none;width:58px}
        .it .ti{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;
                white-space:nowrap;color:#e8e8ea}
        .it .lg{flex:none;color:#81c995;font-size:11px}
        .it .x{flex:none;width:24px;height:24px;padding:0;font-size:13px;line-height:1;
               background:none;border:none;color:#5f6368}
        .it .x:hover{color:#f28b82;background:none}
        .empty{color:#5f6368;font-size:12px;padding:6px 0}
        .cand{display:block;width:100%;text-align:left;margin:5px 0;padding:8px 10px;
              font-size:11px;word-break:break-all;color:#fdd663;border-color:#5c4b1f;
              line-height:1.4}
        .cq{color:#fdd663;font-size:12px;margin:10px 0 4px}
        .hint{color:#5f6368;font-size:11px;margin-top:14px;line-height:1.6;
              border-top:1px solid #2a2e35;padding-top:12px}
        .hint b{color:#9aa0a6}
      </style>
      <div class="p">
        <h1>VIDKIT CAPTURE</h1>
        <div id="fields"></div>
        <datalist id="__vk_langs"></datalist>
        <div class="warn" id="langwarn"></div>
        <div class="picking" id="picking">click a field, then click that text on the page</div>
        <div class="url empty" id="url">no video selected</div>
        <div id="cands"></div>
        <div class="edbar" id="edbar" style="display:none">editing a saved source</div>
        <div class="sec">save this video, then…</div>
        <div class="acts" id="edacts" style="display:none">
          <button id="b_upd"><b>update this source</b></button>
          <button id="b_cancel"><b>cancel</b></button>
        </div>
        <div class="acts" id="acts">
          <button id="b_lang"><b>…add another language to it</b><span>keeps everything</span></button>
          <button id="b_video"><b>…start the next video</b><span>number + 1</span></button>
          <button id="b_day"><b>…start a new day</b><span>day + 1, number to 1</span></button>
          <button id="b_show"><b>…start a different course</b><span>clears all</span></button>
        </div>
        <div class="sec">plan
          <span class="tabs"><button id="tab_items" class="tab on">items</button
            ><button id="tab_files" class="tab">files</button></span>
        </div>
        <div id="plan"><div class="empty">nothing saved yet</div></div>
        <div class="foot">
          <button id="clr">clear form</button>
          <button id="fin">finish &amp; write plan</button>
        </div>
        <div class="hint">
          Click into a field, then click that text on the page.<br>
          Click into <b>url</b> and click the video itself. <b>esc</b> cancels.<br>
          Every field is editable by hand.<br>
          Suggestions: <em style="color:#8ab4f8;font-style:normal">matched</em> ·
          <u style="color:#fdd663;text-decoration:none;border-bottom:2px dotted #fdd663">different case</u> ·
          unmarked means no match.
        </div>
      </div>`;

    const fields = root.getElementById('fields');
    for (const c of window.__vk_cols) {
      const r = document.createElement('div');
      r.className = 'r';
      r.innerHTML = c === 'lang'
        ? `<label>${c}</label><input data-f="${c}" list="__vk_langs" autocomplete="off">`
        : `<label>${c}</label><input data-f="${c}" autocomplete="off">`;
      fields.appendChild(r);
      const sug = document.createElement('div');
      sug.className = 'sug'; sug.dataset.for = c;
      fields.appendChild(sug);
    }
    root.querySelectorAll('input').forEach(i => {
      i.oninput = () => window.vkField(i.dataset.f, i.value);
      // Enter takes the best suggestion, so a typo is one keystroke from fixed.
      i.onkeydown = (e) => {
        if (e.key !== 'Enter') return;
        const top = root.querySelector(`.sug[data-for="${i.dataset.f}"] .s`);
        if (top) { e.preventDefault(); window.vkAccept(i.dataset.f, top.dataset.v); }
      };
      // Focusing a field arms it. Type and it is just a text box; move onto the page
      // and the same field is waiting for a pick.
      i.onfocus  = () => window.vkArm(i.dataset.f);
    });
    let view = 'items';
    for (const [id, v] of [['tab_items','items'], ['tab_files','files']])
      root.getElementById(id).onclick = () => {
        view = v;
        root.getElementById('tab_items').classList.toggle('on', v === 'items');
        root.getElementById('tab_files').classList.toggle('on', v === 'files');
        if (window.__vk_last) window.__vk.paint(window.__vk_last);
      };
    for (const [id, mode] of [['b_lang','language'], ['b_video','video'],
                              ['b_day','day'], ['b_show','show']])
      root.getElementById(id).onclick = () => window.vkSave(mode);
    root.getElementById('b_upd').onclick = () => window.vkUpdate();
    root.getElementById('b_cancel').onclick = () => window.vkCancel();
    root.getElementById('clr').onclick = () => window.vkClear();
    root.getElementById('fin').onclick = () => window.vkFinish();

    window.__vk = {
      paint: (st) => {
        for (const c of window.__vk_cols) {
          const i = root.querySelector(`input[data-f="${c}"]`);
          const v = st.row[c] ?? '';
          if (i && i.value !== v) i.value = v;
        }
        root.querySelectorAll('input').forEach(i =>
          i.classList.toggle('armed', i.dataset.f === st.armed));
        root.getElementById('picking').textContent = st.armed
          ? `picking ${st.armed} — click it on the page, or just type`
          : 'click a field, then click that text on the page';

        const esc = (x) => x.replace(/[&<>"]/g, c =>
          ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
        // Three states per character: matched, matched but different case, missed.
        const mark = (segs) => segs.map(g =>
          g.kind === 'exact' ? `<em>${esc(g.text)}</em>`
          : g.kind === 'case' ? `<u>${esc(g.text)}</u>`
          : esc(g.text)).join('');
        root.querySelectorAll('.sug').forEach(d => { d.innerHTML = ''; });
        if (st.armed) {
          const box = root.querySelector(`.sug[data-for="${st.armed}"]`);
          if (box) st.suggest.forEach((sg, n) => {
            const b = document.createElement('button');
            b.className = 's' + (n === 0 ? ' top' : '');
            b.dataset.v = sg.text;
            b.innerHTML = mark(sg.segs) +
                          (sg.caseOff ? '<span class="cs">case</span>' : '') +
                          (n === 0 ? '<span class="k">enter</span>' : '');
            b.onclick = () => window.vkAccept(st.armed, sg.text);
            box.appendChild(b);
          });
        }

        const dl = root.getElementById('__vk_langs');
        if (dl && !dl.children.length)
          dl.innerHTML = st.langSuggest.map(l => `<option value="${l}">`).join('');
        const li = root.querySelector('input[data-f="lang"]');
        if (li) li.classList.toggle('bad', !!st.langProblem);
        root.getElementById('langwarn').textContent = st.langProblem || '';

        const cs = root.getElementById('cands');
        cs.innerHTML = st.candidates.length
          ? `<div class="cq">${st.candidates.length} streams from that player — pick one:</div>` : '';
        st.candidates.forEach(c => {
          const b = document.createElement('button');
          b.className = 'cand'; b.textContent = c;
          b.onclick = () => window.vkChoose(c);
          cs.appendChild(b);
        });

        const u = root.getElementById('url');
        u.textContent = st.url || 'no video selected';
        u.className = st.url ? 'url' : 'url empty';
        ['b_lang','b_video','b_day','b_show'].forEach(id => {
          const b = root.getElementById(id);
          b.disabled = !st.url;
          b.style.opacity = st.url ? '1' : '.35';
          b.style.cursor = st.url ? 'pointer' : 'not-allowed';
          b.title = st.url ? '' : 'arm url and click the video first';
        });

        // Editing replaces the four save buttons with update/cancel.
        const ed = st.editing !== null && st.editing !== undefined;
        root.getElementById('edbar').style.display = ed ? 'block' : 'none';
        root.getElementById('acts').style.display = ed ? 'none' : 'flex';
        root.getElementById('edacts').style.display = ed ? 'flex' : 'none';

        const plan = root.getElementById('plan');
        plan.innerHTML = '';
        const rows = view === 'items' ? st.plan : st.files;
        if (!rows.length) {
          plan.innerHTML = '<div class="empty">nothing saved yet</div>';
        } else if (view === 'items') {
          for (const n of rows) {
            const d = document.createElement('div');
            if (n.kind === 'group') { d.className = 'grp'; d.textContent = n.text; }
            else {
              d.className = 'it';
              d.innerHTML = `<span class="n">${n.num}</span>
                             <span class="ti">${esc(n.title)}</span>
                             <span class="lg"></span>
                             <button class="x" title="remove">×</button>`;
              const lg = d.querySelector('.lg');
              n.langs.forEach(l => {
                const c = document.createElement('span');
                c.className = 'c' + (l.idx === st.editing ? ' ed' : '');
                c.textContent = l.lang;
                c.title = 'edit this source';
                c.onclick = () => window.vkEdit(l.idx);
                lg.appendChild(c);
              });
              d.querySelector('.x').onclick = () => window.vkDelete(n.key);
            }
            plan.appendChild(d);
          }
        } else {
          for (const n of rows) {
            const d = document.createElement('div');
            d.style.paddingLeft = (n.depth * 14) + 'px';
            if (n.kind === 'dir') { d.className = 'fdir'; d.textContent = n.text + '/'; }
            else {
              d.className = 'ffile';
              d.innerHTML = esc(n.text) + '<div class="ftr"></div>';
              const tr = d.querySelector('.ftr');
              tr.append('audio: ');
              n.tracks.forEach(t => {
                const c = document.createElement('span');
                c.className = 'c' + (t.idx === st.editing ? ' ed' : '');
                c.textContent = t.lang + (t.default ? ' ·default' : '');
                c.style.cssText = 'display:inline-block;padding:1px 6px;margin-right:4px;' +
                  'border-radius:3px;background:#1f2b22;border:1px solid #2f4536;' +
                  'color:#81c995;cursor:pointer';
                c.onclick = () => window.vkEdit(t.idx);
                tr.appendChild(c);
              });
            }
            plan.appendChild(d);
          }
        }
        window.__vk_last = st;
      },
    };
    if (window.vkReady) window.vkReady();
  };

  if (document.readyState === 'loading')
    document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
