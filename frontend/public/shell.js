/* ============================================================
   速赢AI — 共享外壳：侧边栏 + 顶栏注入，自动高亮当前页
   每个页面只需：<body data-page="screener" data-title="智能选股">
   并在末尾引用本脚本即可。
   ============================================================ */
(function(){
  const I = { // 16px 线性图标
    dash:'<rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/>',
    search:'<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>',
    chain:'<circle cx="12" cy="5" r="2.4"/><circle cx="5" cy="19" r="2.4"/><circle cx="19" cy="19" r="2.4"/><path d="M12 7.4v4M12 11.4L5.8 17M12 11.4L18.2 17"/>',
    line:'<path d="M3 17l5-6 4 4 5-8 4 5"/>',
    bulb:'<path d="M9 18V9l4 3 5-8"/><path d="M4 20h16"/>',
    bolt:'<path d="M13 2L4 14h6l-1 8 9-12h-6z"/>',
    dollar:'<circle cx="12" cy="12" r="9"/><path d="M12 7v10M9.5 9.2c0-1.2 1.1-1.9 2.5-1.9s2.5.7 2.5 1.9-1.1 1.7-2.5 1.7-2.5.6-2.5 1.8 1.1 1.9 2.5 1.9 2.5-.7 2.5-1.9"/>',
    robot:'<rect x="5" y="7" width="14" height="12" rx="2"/><path d="M9 7V5a3 3 0 0 1 6 0v2M9 13h.01M15 13h.01"/>',
    flask:'<path d="M4 4v16h16"/><path d="M7 14l3-4 3 2 4-6"/>',
    pulse:'<circle cx="12" cy="12" r="9"/><path d="M12 8v4l3 2"/>',
    train:'<path d="M10 2v3M14 2v3M7 8h10l-1 12H8z"/><path d="M9 12h6M9 16h6"/>',
    registry:'<rect x="3" y="4" width="18" height="6" rx="1.5"/><rect x="3" y="14" width="18" height="6" rx="1.5"/><path d="M7 7h.01M7 17h.01"/>',
    clock:'<circle cx="12" cy="12" r="9"/><path d="M12 8v4l3 2"/>',
  };
  const NAV = [
    {g:'行情决策'},
    {k:'dashboard',  f:'index.html',        i:'dash',   t:'AI 智能看板'},
    {k:'screener',   f:'screener.html',     i:'search', t:'智能选股', pill:'12'},
    {k:'supply-chain',f:'supply-chain.html',i:'chain',  t:'产业链拆解'},
    {k:'predictions',f:'predictions.html',  i:'line',   t:'K线预测'},
    {k:'strategy',   f:'strategy.html',     i:'bulb',   t:'方案管理'},
    {k:'signals',    f:'signals.html',      i:'bolt',   t:'交易信号', pill:'3'},
    {g:'交易执行'},
    {k:'trade',      f:'trade.html',        i:'dollar', t:'交易中心'},
    {k:'auto-trade', f:'auto-trade.html',   i:'robot',  t:'量化交易'},
    {k:'backtest',   f:'backtest.html',     i:'flask',  t:'回测分析'},
    {k:'diagnosis',  f:'diagnosis.html',    i:'pulse',  t:'个股诊断'},
    {g:'模型 / 系统', admin:true},
    {k:'training',      f:'training.html',       i:'train',    t:'模型训练'},
    {k:'model-registry',f:'model-registry.html', i:'registry', t:'模型注册'},
    {k:'data-update',   f:'data-update.html',    i:'clock',    t:'数据更新'},
  ];
  function svg(p){return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'+p+'</svg>';}

  const page = document.body.dataset.page || 'dashboard';
  const title = document.body.dataset.title || 'AI 智能看板';

  let navHTML = '';
  NAV.forEach(n=>{
    if(n.g){ navHTML += '<div class="nav-group">'+n.g+(n.admin?'<span class="nav-admin">admin</span>':'')+'</div>'; return; }
    navHTML += '<a class="nav-item'+(n.k===page?' active':'')+'" href="'+n.f+'">'+svg(I[n.i])+'<span>'+n.t+'</span>'+(n.pill?'<span class="pill">'+n.pill+'</span>':'')+'</a>';
  });

  const sidebar = '<aside class="sidebar"><div class="brand"><div class="logo">'+svg(I.line)+'</div><div class="name">速赢<b>AI</b></div></div><nav class="nav">'+navHTML+'</nav></aside>';

  const header = '<header class="header">'+
    '<div class="crumb"><b>'+title+'</b></div>'+
    '<div class="mkt-ticker">'+
      '<div class="tk"><span class="lbl">上证</span><span class="val up mono">3,486.32 +0.74%</span></div>'+
      '<div class="tk"><span class="lbl">深成</span><span class="val up mono">10,612.5 +1.12%</span></div>'+
      '<div class="tk"><span class="lbl">创业板</span><span class="val down mono">2,108.7 −0.43%</span></div>'+
      '<div class="tk"><span class="lbl">北证50</span><span class="val up mono">1,042.1 +0.31%</span></div>'+
    '</div>'+
    '<div class="header-right">'+
      '<button class="hbtn" id="themeBtn" title="切换明暗">'+svg('<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>')+'</button>'+
      '<button class="hbtn" title="刷新" onclick="location.reload()">'+svg('<path d="M21 12a9 9 0 1 1-2.6-6.3"/><path d="M21 4v5h-5"/>')+'</button>'+
      '<a class="hbtn" href="signals.html" title="交易信号">'+svg('<path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 0 1-3.4 0"/>')+'<span class="dot">3</span></a>'+
      '<button class="hbtn" title="系统设置">'+svg('<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-2.7 1.1V21a2 2 0 0 1-4 0v-.1a1.6 1.6 0 0 0-2.7-1.1l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A1.6 1.6 0 0 0 4 15M3 12h.1M21 12h-.1"/>')+'</button>'+
      '<div class="user"><div class="av">罗</div><div class="un">罗杰</div></div>'+
    '</div></header>';

  document.getElementById('sidebar-mount').outerHTML = sidebar;
  document.getElementById('header-mount').outerHTML = header;

  // 明暗切换
  const root = document.documentElement;
  try{ const t=localStorage.getItem('proto_theme'); if(t) root.setAttribute('data-theme',t); }catch(e){}
  const tb = document.getElementById('themeBtn');
  if(tb) tb.addEventListener('click',()=>{
    const cur = root.getAttribute('data-theme')==='light'?'dark':'light';
    root.setAttribute('data-theme',cur);
    try{ localStorage.setItem('proto_theme',cur); }catch(e){}
    window.dispatchEvent(new Event('od-theme-change'));
  });
})();
