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
    {k:'workbench',  f:'suying-ai-workbench-redesign.html', i:'line', t:'开盘决策舱'},
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
  const currentHash = (location.hash || '').replace('#','');
  const MODULE_TABS = {
    dashboard: [
      {anchor:'market-sentiment', n:'市场情绪', s:'指数 / 涨跌家数'},
      {anchor:'auction-intent', n:'竞价意图', s:'9:25 抢筹'},
      {anchor:'signal-overview', n:'信号总览', s:'今日触发'},
      {anchor:'watchlist', n:'自选跟踪', s:'持仓线索'},
      {anchor:'service-health', n:'运行状态', s:'服务 / 数据'},
    ],
    workbench: [
      {anchor:'overview', n:'开盘闸门', s:'交易简报'},
      {anchor:'candidate-workspace', n:'候选决策', s:'AI 队列'},
      {anchor:'prediction-panel', n:'K线推演', s:'30 日路径'},
      {anchor:'trade-ticket', n:'风控交易', s:'半自动'},
      {anchor:'service-health', n:'链路审计', s:'6 / 7 在线'},
    ],
    screener: [
      {anchor:'factor-modes', n:'策略入口', s:'12 套策略'},
      {anchor:'candidate-list', n:'因子筛选', s:'过滤 / 排序'},
      {anchor:'candidate-list', n:'候选清单', s:'评分排序'},
      {anchor:'bulk-actions', n:'批量动作', s:'自选 / 下单'},
      {anchor:'diagnosis-linkage', n:'诊断联动', s:'批量送诊'},
    ],
    'supply-chain': [
      {anchor:'chain-map', n:'产业图谱', s:'上下游关系'},
      {anchor:'risk-spread', n:'链路证据', s:'来源 / 影响'},
      {anchor:'leader-board', n:'核心公司', s:'龙头 / 弹性'},
      {anchor:'risk-spread', n:'风险传导', s:'主题退潮'},
      {anchor:'screener-bridge', n:'加入选股', s:'主题候选'},
    ],
    predictions: [
      {anchor:'target-selector', n:'标的选择', s:'股票 / 模型'},
      {anchor:'kline-view', n:'K线走势', s:'历史 / 预测'},
      {anchor:'probability-path', n:'概率路径', s:'30 日区间'},
      {anchor:'price-levels', n:'关键价位', s:'支撑 / 阻力'},
      {anchor:'signal-generation', n:'生成信号', s:'执行触发'},
    ],
    strategy: [
      {anchor:'strategy-list', n:'方案列表', s:'策略库'},
      {anchor:'parameter-set', n:'参数组合', s:'仓位 / 止损'},
      {anchor:'execution-plan', n:'执行计划', s:'交易约束'},
      {anchor:'backtest-review', n:'回测复核', s:'收益 / 回撤'},
    ],
    signals: [
      {anchor:'signal-feed', n:'信号总览', s:'未读 / 已读'},
      {anchor:'buy-signals', n:'买入触发', s:'强弱分级'},
      {anchor:'risk-signals', n:'风险提示', s:'止损 / 止盈'},
      {anchor:'subscriptions', n:'订阅策略', s:'策略开关'},
    ],
    trade: [
      {anchor:'trade-ticket', n:'交易票', s:'买卖委托'},
      {anchor:'risk-check', n:'风控校验', s:'仓位 / 余额'},
      {anchor:'position-view', n:'持仓资金', s:'可用 / 冻结'},
      {anchor:'order-feed', n:'委托回报', s:'状态跟踪'},
    ],
    'auto-trade': [
      {anchor:'strategy-instance', n:'策略实例', s:'运行策略'},
      {anchor:'runtime-monitor', n:'运行监控', s:'成交 / 延迟'},
      {anchor:'risk-switches', n:'风控开关', s:'人工闸门'},
      {anchor:'execution-log', n:'执行日志', s:'审计记录'},
    ],
    backtest: [
      {anchor:'parameter-review', n:'回测参数', s:'区间 / 资金'},
      {anchor:'equity-curve', n:'收益曲线', s:'净值 / 回撤'},
      {anchor:'trade-breakdown', n:'交易拆解', s:'胜率 / 盈亏'},
      {anchor:'failure-cases', n:'失败样本', s:'风险解释'},
    ],
    diagnosis: [
      {anchor:'stock-profile', n:'个股画像', s:'基本面 / 资金'},
      {anchor:'risk-radar', n:'风险雷达', s:'多因子'},
      {anchor:'signal-history', n:'历史信号', s:'触发记录'},
      {anchor:'action-plan', n:'操作建议', s:'观察 / 执行'},
    ],
    training: [
      {anchor:'training-jobs', n:'训练任务', s:'队列状态'},
      {anchor:'loss-monitor', n:'损失曲线', s:'训练质量'},
      {anchor:'dataset-check', n:'数据校验', s:'缺失 / 偏移'},
      {anchor:'release-gate', n:'发布闸门', s:'准入检查'},
    ],
    'model-registry': [
      {anchor:'model-list', n:'模型列表', s:'版本 / 状态'},
      {anchor:'metrics-board', n:'指标对比', s:'收益 / 回撤'},
      {anchor:'deployment-stage', n:'部署阶段', s:'灰度 / 回滚'},
      {anchor:'audit-log', n:'审计记录', s:'变更历史'},
    ],
    'data-update': [
      {anchor:'sync-overview', n:'同步总览', s:'源状态'},
      {anchor:'data-quality', n:'质量检查', s:'缺失 / 延迟'},
      {anchor:'sync-log', n:'同步日志', s:'任务明细'},
      {anchor:'repair-actions', n:'修复动作', s:'重跑 / 补数'},
    ],
  };
  const MODULE_CONTEXT = {
    dashboard: ['当前模块','AI 智能看板','功能板块','市场情绪 · 竞价意图 · 信号总览','业务状态','盘后复盘','数据状态','实时刷新 42s'],
    workbench: ['当前模块','开盘决策舱','功能板块','开盘闸门 · 候选决策 · 风控交易','业务状态','开盘前复核','数据状态','候选延迟 1 周期'],
    screener: ['当前模块','智能选股','功能板块','策略入口 · 因子筛选 · 候选清单','业务状态','42 只候选','数据状态','选股服务延迟'],
    'supply-chain': ['当前模块','产业链拆解','功能板块','产业图谱 · 链路证据 · 风险传导','业务状态','AI 算力主题','数据状态','证据链在线'],
    predictions: ['当前模块','K线预测','功能板块','标的选择 · K线走势 · 概率路径','业务状态','30 日预测','数据状态','模型在线'],
    strategy: ['当前模块','方案管理','功能板块','方案列表 · 参数组合 · 执行计划','业务状态','4 套运行','数据状态','策略库在线'],
    signals: ['当前模块','交易信号','功能板块','信号总览 · 买入触发 · 风险提示','业务状态','3 条未读','数据状态','推送在线'],
    trade: ['当前模块','交易中心','功能板块','交易票 · 风控校验 · 委托回报','业务状态','半自动复核','数据状态','交易网关在线'],
    'auto-trade': ['当前模块','量化交易','功能板块','策略实例 · 运行监控 · 风控开关','业务状态','3 运行 / 2 暂停','数据状态','执行链路在线'],
    backtest: ['当前模块','回测分析','功能板块','收益曲线 · 交易拆解 · 参数复核','业务状态','策略复核','数据状态','回测引擎在线'],
    diagnosis: ['当前模块','个股诊断','功能板块','个股画像 · 风险雷达 · 操作建议','业务状态','中际旭创 300308','数据状态','诊断模型在线'],
    training: ['当前模块','模型训练','功能板块','训练任务 · 损失曲线 · 数据校验','业务状态','1 个任务训练中','数据状态','训练集可用'],
    'model-registry': ['当前模块','模型注册','功能板块','模型列表 · 指标对比 · 部署阶段','业务状态','14 个注册版本','数据状态','灰度通道在线'],
    'data-update': ['当前模块','数据更新','功能板块','同步总览 · 质量检查 · 修复动作','业务状态','83% 健康','数据状态','盘后同步待执行'],
  };

  let navHTML = '';
  NAV.forEach(n=>{
    if(n.g){ navHTML += '<div class="nav-group">'+n.g+(n.admin?'<span class="nav-admin">admin</span>':'')+'</div>'; return; }
    const current = n.k===page;
    navHTML += '<a class="nav-item'+(current?' active':'')+'" href="'+n.f+'"'+(current?' aria-current="page"':'')+'>'+svg(I[n.i])+'<span>'+n.t+'</span>'+(n.pill?'<span class="pill">'+n.pill+'</span>':'')+'</a>';
  });

  const sidebar = '<aside class="sidebar"><div class="brand"><div class="logo">'+svg(I.line)+'</div><div class="name">速赢<b>AI</b></div></div><nav class="nav">'+navHTML+'</nav></aside>';

  const tabs = MODULE_TABS[page] || [
    {anchor:'overview', n:'总览', s:'当前页面'},
    {anchor:'primary-panel', n:'核心面板', s:'主要功能'},
    {anchor:'status-panel', n:'状态', s:'数据 / 服务'},
  ];
  let tabHTML = '';
  tabs.forEach((item, index)=>{
    const href = item.anchor ? '#'+item.anchor : '#';
    const active = item.anchor ? ((currentHash && currentHash === item.anchor) || (!currentHash && index === 0)) : false;
    tabHTML += '<a class="module-tab'+(active?' active':'')+'" href="'+href+'" data-tab-anchor="'+(item.anchor || '')+'"'+(active?' aria-current="true"':'')+'><span class="tab-no">'+String(index+1).padStart(2,'0')+'</span><span class="tab-main">'+item.n+'</span><span class="tab-sub">'+item.s+'</span></a>';
  });
  const ctx = MODULE_CONTEXT[page] || ['当前模块', title, '功能板块', tabs.map(t=>t.n).join(' · '), '业务状态', '可用', '数据状态', '在线'];

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
  const moduleTabs = '<nav class="module-tabs" aria-label="模块功能页签">'+tabHTML+'</nav>';
  const context = '<section class="module-context" aria-label="当前模块上下文">'+
    '<div class="context-card"><span>'+ctx[0]+'</span><b>'+ctx[1]+'</b></div>'+
    '<div class="context-card"><span>'+ctx[2]+'</span><b>'+ctx[3]+'</b></div>'+
    '<div class="context-card ok"><span>'+ctx[4]+'</span><b>'+ctx[5]+'</b></div>'+
    '<div class="context-card warn"><span>'+ctx[6]+'</span><b>'+ctx[7]+'</b></div>'+
  '</section>';

  document.getElementById('sidebar-mount').outerHTML = sidebar;
  document.getElementById('header-mount').outerHTML = '<div class="shell-top">'+header+moduleTabs+context+'</div>';

  function syncTabs(){
    const hash = (location.hash || '').replace('#','');
    const links = Array.prototype.slice.call(document.querySelectorAll('.module-tab[data-tab-anchor]'));
    const activeAnchor = hash || (tabs[0] && tabs[0].anchor) || '';
    links.forEach((link)=>{
      const active = link.dataset.tabAnchor === activeAnchor;
      link.classList.toggle('active', active);
      if(active) link.setAttribute('aria-current','true');
      else link.removeAttribute('aria-current');
    });
  }
  window.addEventListener('hashchange', syncTabs);
  document.querySelectorAll('.module-tab[data-tab-anchor]').forEach((link)=>link.addEventListener('click',()=>setTimeout(syncTabs, 0)));
  syncTabs();

  // 明暗切换：默认白天主题，夜间主题只在用户显式切换后启用。
  const root = document.documentElement;
  let theme = 'light';
  try{ theme = localStorage.getItem('suying_theme') || 'light'; }catch(e){}
  root.setAttribute('data-theme',theme === 'dark' ? 'dark' : 'light');
  const tb = document.getElementById('themeBtn');
  if(tb) tb.addEventListener('click',()=>{
    const cur = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    root.setAttribute('data-theme',cur);
    try{ localStorage.setItem('suying_theme',cur); }catch(e){}
    window.dispatchEvent(new Event('od-theme-change'));
  });
  function shellToast(text){
    if(!text) return;
    let node = document.getElementById('shellToast');
    if(!node){
      node = document.createElement('div');
      node.id = 'shellToast';
      node.className = 'toast';
      node.setAttribute('role','status');
      node.setAttribute('aria-live','polite');
      document.body.appendChild(node);
    }
    node.textContent = text;
    node.classList.add('show');
    window.clearTimeout(shellToast.timer);
    shellToast.timer = window.setTimeout(()=>node.classList.remove('show'), 1700);
  }
  document.addEventListener('click',(event)=>{
    const toastTarget = event.target.closest('[data-toast]');
    if(toastTarget && toastTarget.tagName !== 'A'){
      event.preventDefault();
      shellToast(toastTarget.dataset.toast);
    }
    const segButton = event.target.closest('.seg .s');
    if(segButton && segButton.parentElement){
      Array.prototype.forEach.call(segButton.parentElement.querySelectorAll('.s'),(button)=>button.classList.remove('active'));
      segButton.classList.add('active');
    }
  });
})();
