/* 速赢AI PRD preview shell: shared sidebar, market header, module tabs, context strip. */
(function(){
  // 统一注入空 favicon，消除全站 /favicon.ico 404 console error
  if(!document.querySelector('link[rel="icon"]')){
    const fav = document.createElement('link');
    fav.rel = 'icon'; fav.href = 'data:,';
    document.head.appendChild(fav);
  }
  const I = {
    dash:'<rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/>',
    line:'<path d="M3 17l5-6 4 4 5-8 4 5"/>',
    search:'<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>',
    chain:'<circle cx="12" cy="5" r="2.4"/><circle cx="5" cy="19" r="2.4"/><circle cx="19" cy="19" r="2.4"/><path d="M12 7.4v4M12 11.4L5.8 17M12 11.4L18.2 17"/>',
    bolt:'<path d="M13 2L4 14h6l-1 8 9-12h-6z"/>',
    dollar:'<circle cx="12" cy="12" r="9"/><path d="M12 7v10M9.5 9.2c0-1.2 1.1-1.9 2.5-1.9s2.5.7 2.5 1.9-1.1 1.7-2.5 1.7-2.5.6-2.5 1.8 1.1 1.9 2.5 1.9 2.5-.7 2.5-1.9"/>',
    robot:'<rect x="5" y="7" width="14" height="12" rx="2"/><path d="M9 7V5a3 3 0 0 1 6 0v2M9 13h.01M15 13h.01"/>',
    shield:'<path d="M12 3l7 3v5c0 5-3.4 8.4-7 10-3.6-1.6-7-5-7-10V6z"/><path d="M9 12l2 2 4-5"/>',
    flask:'<path d="M4 4v16h16"/><path d="M7 14l3-4 3 2 4-6"/>',
    pulse:'<circle cx="12" cy="12" r="9"/><path d="M12 8v4l3 2"/>',
    train:'<path d="M10 2v3M14 2v3M7 8h10l-1 12H8z"/><path d="M9 12h6M9 16h6"/>',
    registry:'<rect x="3" y="4" width="18" height="6" rx="1.5"/><rect x="3" y="14" width="18" height="6" rx="1.5"/><path d="M7 7h.01M7 17h.01"/>',
    clock:'<circle cx="12" cy="12" r="9"/><path d="M12 8v4l3 2"/>',
    doc:'<path d="M6 3h9l3 3v15H6z"/><path d="M15 3v4h4M9 12h6M9 16h6"/>'
  };

  const NAV = [
    {g:'行情决策'},
    {k:'dashboard', f:'1.1 sentiment-dashboard-preview.html', i:'dash', t:'智能看板'},
    {k:'opening-decision', f:'2.1 decision-overview-preview.html', i:'line', t:'开盘决策'},
    {k:'screener', f:'3.1 screener-workbench-preview.html', i:'search', t:'智能选股', pill:'12'},
    {k:'supply-chain', f:'4.1 policy-analysis-preview.html', i:'chain', t:'产业链拆解'},
    {k:'predictions', f:'5.0 prediction-preview.html', i:'line', t:'K线预测'},
    {k:'signals', f:'6.0 signal-detail-preview.html', i:'bolt', t:'交易信号', pill:'3'},
    {g:'交易执行'},
    {k:'trade', f:'7.0 trade-center-preview.html', i:'dollar', t:'交易中心'},
    {k:'auto-trade', f:'8.1 strategy-market-preview.html', i:'robot', t:'量化交易'},
    {k:'plans', f:'9.1 plan-list-preview.html', i:'doc', t:'方案管理'},
    {k:'risk-control', f:'10.0 risk-control-dashboard-preview.html', i:'shield', t:'风控中心'},
    {k:'backtest', f:'11.1 backtest-run-preview.html', i:'flask', t:'回测分析'},
    {k:'diagnosis', f:'12.0 diagnosis-preview.html', i:'pulse', t:'个股诊断'},
    {g:'模型 / 系统', admin:true},
    {k:'training', f:'13.0 model-training-preview.html', i:'train', t:'模型训练'},
    {k:'model-registry', f:'14.0 model-registry-preview.html', i:'registry', t:'模型注册'},
    {k:'data-update', f:'15.0 data-update-preview.html', i:'clock', t:'数据更新'},
    {k:'runtime-status', f:'16.0 runtime-status-preview.html', i:'pulse', t:'运行状态'}
  ];

  const MODULE_TABS = {
    dashboard: [
      {n:'市场情绪', s:'宽度 / 资金', f:'1.1 sentiment-dashboard-preview.html'},
      {n:'竞价意图', s:'9:25 抢筹', f:'1.2 auction-dashboard-preview.html'},
      {n:'信号总览', s:'今日触发', f:'1.3 signal-overview-preview.html'},
      {n:'自选跟踪', s:'持仓线索', f:'1.4 watchlist-dashboard-preview.html'}
    ],
    'opening-decision': [
      {n:'决策总览', s:'开盘闸门', f:'2.1 decision-overview-preview.html'},
      {n:'竞价分析', s:'集合竞价', f:'2.2 auction-analysis-preview.html'},
      {n:'信号扫描', s:'触发队列', f:'2.3 signal-scan-preview.html'},
      {n:'候选池', s:'AI 队列', f:'2.4 candidate-pool-preview.html'},
      {n:'执行监控', s:'链路状态', f:'2.5 execution-monitor-preview.html'}
    ],
    screener: [
      {n:'选股工作台', s:'策略入口', f:'3.1 screener-workbench-preview.html'},
      {n:'模型对比', s:'评分差异', f:'3.2 model-compare-preview.html'},
      {n:'因子分析', s:'IC / 暴露', f:'3.3 factor-analysis-preview.html'}
    ],
    'supply-chain': [
      {n:'政策梳理', s:'政策证据', f:'4.1 policy-analysis-preview.html'},
      {n:'产业链解构', s:'上下游图谱', f:'4.2 chain-decompose-preview.html'},
      {n:'多维度分析', s:'公司对比', f:'4.3 company-analysis-preview.html'}
    ],
    predictions: [
      {n:'预测总览', s:'模型概览', f:'5.0 prediction-preview.html'},
      {n:'单股预测', s:'30 日路径', f:'5.1 single-stock-preview.html'},
      {n:'多股对比', s:'组合比较', f:'5.2 multi-compare-preview.html'},
      {n:'准确率回测', s:'命中复核', f:'5.3 backtest-preview.html'}
    ],
    signals: [
      {n:'信号详情', s:'单股深读', f:'6.0 signal-detail-preview.html'},
      {n:'信号总览', s:'未读 / 已读', f:'6.1 signal-overview-preview.html'},
      {n:'信号历史', s:'触发记录', f:'6.2 signal-history-preview.html'}
    ],
    trade: [
      {n:'交易中心', s:'总览', f:'7.0 trade-center-preview.html'},
      {n:'下单面板', s:'人工确认', f:'7.1 order-panel-preview.html'},
      {n:'持仓监控', s:'资金 / 盈亏', f:'7.2 position-monitor-preview.html'},
      {n:'订单管理', s:'委托回报', f:'7.3 order-management-preview.html'},
      {n:'账户总览', s:'资产结构', f:'7.4 account-overview-preview.html'},
      {n:'券商管理', s:'通道状态', f:'7.5 broker-management-preview.html'}
    ],
    'auto-trade': [
      {n:'策略广场', s:'策略模板', f:'8.1 strategy-market-preview.html'},
      {n:'策略配置', s:'参数闸门', f:'8.2 strategy-config-preview.html'},
      {n:'策略监控', s:'运行状态', f:'8.3 strategy-monitor-preview.html'},
      {n:'策略日志', s:'审计追踪', f:'8.4 strategy-log-preview.html'}
    ],
    plans: [
      {n:'方案列表', s:'策略库', f:'9.1 plan-list-preview.html'},
      {n:'方案详情', s:'参数组合', f:'9.2 plan-detail-preview.html'},
      {n:'方案对比', s:'收益 / 回撤', f:'9.3 plan-compare-preview.html'},
      {n:'结算报告', s:'执行复盘', f:'9.4 settlement-report-preview.html'}
    ],
    'risk-control': [
      {n:'风控总览', s:'风险仪表盘', f:'10.0 risk-control-dashboard-preview.html'},
      {n:'持仓风险', s:'仓位 / 集中度', f:'10.2 position-risk-preview.html'},
      {n:'策略风险', s:'策略暴露', f:'10.3 strategy-risk-preview.html'},
      {n:'市场风险', s:'波动 / 流动性', f:'10.4 market-risk-preview.html'},
      {n:'事件审计', s:'规则命中', f:'10.5 event-audit-preview.html'}
    ],
    backtest: [
      {n:'回测运行', s:'参数执行', f:'11.1 backtest-run-preview.html'},
      {n:'策略对比', s:'组合比较', f:'11.2 backtest-compare-preview.html'},
      {n:'交易明细', s:'成交拆解', f:'11.3 backtest-trades-preview.html'}
    ],
    diagnosis: [
      {n:'诊断总览', s:'个股画像', f:'12.0 diagnosis-preview.html'},
      {n:'综合诊断', s:'五维评分', f:'12.1 diagnosis-overview-preview.html'},
      {n:'模型视角', s:'Kronos / ML', f:'12.2 model-perspective-preview.html'},
      {n:'多股对比', s:'横向比较', f:'12.3 diagnosis-compare-preview.html'},
      {n:'风险扫描', s:'风险雷达', f:'12.4 diagnosis-risk-preview.html'}
    ],
    training: [
      {n:'模型训练', s:'训练总览', f:'13.0 model-training-preview.html'},
      {n:'训练任务', s:'队列状态', f:'13.1 training-tasks-preview.html'},
      {n:'MLflow', s:'实验追踪', f:'13.2 mlflow-experiment-preview.html'}
    ],
    'model-registry': [{n:'模型注册', s:'版本 / 灰度', f:'14.0 model-registry-preview.html'}],
    'data-update': [
      {n:'数据更新', s:'同步总览', f:'15.0 data-update-preview.html'},
      {n:'全部数据表', s:'表级质量', f:'15.2 all-tables-preview.html'},
      {n:'同步调度', s:'任务编排', f:'15.3 sync-schedule-preview.html'}
    ],
    'runtime-status': [{n:'运行状态', s:'服务 / 任务', f:'16.0 runtime-status-preview.html'}]
  };

  function svg(path){return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'+path+'</svg>';}
  function esc(v){return String(v || '').replace(/[&<>"']/g, (m)=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));}

  const page = document.body.dataset.page || 'dashboard';
  const title = document.body.dataset.title || '智能看板';
  const currentFile = decodeURIComponent(location.pathname.split('/').pop() || '');
  let navHTML = '';
  NAV.forEach((n)=>{
    if(n.g){ navHTML += '<div class="nav-group">'+n.g+(n.admin?'<span class="nav-admin">admin</span>':'')+'</div>'; return; }
    const current = n.k === page;
    navHTML += '<a class="nav-item'+(current?' active':'')+'" href="'+esc(n.f)+'"'+(current?' aria-current="page"':'')+'>'+svg(I[n.i])+'<span>'+esc(n.t)+'</span>'+(n.pill?'<span class="pill">'+esc(n.pill)+'</span>':'')+'</a>';
  });

  const tabs = MODULE_TABS[page] || [{n:'总览', s:'当前页面', f:currentFile}];
  let tabHTML = '';
  tabs.forEach((item, index)=>{
    const active = item.f === currentFile || (!currentFile && index === 0);
    tabHTML += '<a class="module-tab'+(active?' active':'')+'" href="'+esc(item.f || '#')+'"'+(active?' aria-current="true"':'')+'><span class="tab-no">'+String(index+1).padStart(2,'0')+'</span><span class="tab-main">'+esc(item.n)+'</span><span class="tab-sub">'+esc(item.s)+'</span></a>';
  });

  const sidebarMount = document.getElementById('sidebar-mount');
  const headerMount = document.getElementById('header-mount');
  if(sidebarMount){
    sidebarMount.outerHTML = '<aside class="sidebar"><div class="brand"><div class="logo">'+svg(I.line)+'</div><div class="name">速赢<b>AI</b></div></div><nav class="nav">'+navHTML+'</nav></aside>';
  }
  if(headerMount){
    const header = '<header class="header"><div class="crumb"><b>'+esc(title)+'</b></div><div class="mkt-ticker"><div class="tk"><span class="lbl">上证</span><span class="val up mono">3,486.32 +0.74%</span></div><div class="tk"><span class="lbl">深成</span><span class="val up mono">10,612.5 +1.12%</span></div><div class="tk"><span class="lbl">创业板</span><span class="val down mono">2,108.7 −0.43%</span></div><div class="tk"><span class="lbl">北证50</span><span class="val up mono">1,042.1 +0.31%</span></div></div><div class="header-right"><button class="hbtn" id="themeBtn" title="切换明暗">'+svg('<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>')+'</button><button class="hbtn" title="刷新" data-toast="页面数据已刷新">'+svg('<path d="M21 12a9 9 0 1 1-2.6-6.3"/><path d="M21 4v5h-5"/>')+'</button><a class="hbtn" href="6.1 signal-overview-preview.html" title="交易信号">'+svg('<path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 0 1-3.4 0"/>')+'<span class="dot">3</span></a><div class="user"><div class="av">罗</div><div class="un">罗杰</div></div></div></header>';
    headerMount.outerHTML = '<div class="shell-top">'+header+'<nav class="module-tabs" aria-label="模块功能页签">'+tabHTML+'</nav></div>';
  }

  const root = document.documentElement;
  // 全站默认暗色（交易终端主主题），用户可通过顶栏按钮切浅色，选择持久化。
  let theme = 'dark';
  try{ theme = localStorage.getItem('suying_preview_theme') || 'dark'; }catch(e){}
  root.setAttribute('data-theme', theme === 'dark' ? 'dark' : 'light');
  const themeBtn = document.getElementById('themeBtn');
  if(themeBtn) themeBtn.addEventListener('click', ()=>{
    const next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    root.setAttribute('data-theme', next);
    try{ localStorage.setItem('suying_preview_theme', next); }catch(e){}
    window.dispatchEvent(new Event('suying-theme-change'));
  });
})();
