/* Shared interaction layer. Keeps legacy handlers intact and fills gaps on static controls. */
(function(){
  function toast(message, type){
    if(!message) return;
    // 类型归一：页面历史代码传 'success'，统一直到 'ok'
    if(type === 'success') type = 'ok';
    let node = document.getElementById('toast') || document.getElementById('shellToast');
    if(!node){
      node = document.createElement('div');
      node.id = 'shellToast';
      node.className = 'toast';
      node.setAttribute('role','status');
      node.setAttribute('aria-live','polite');
      document.body.appendChild(node);
    }
    node.textContent = message;
    node.className = 'toast show ' + (type || 'info');
    clearTimeout(node._timer);
    node._timer = setTimeout(()=>{ node.className = 'toast'; }, 2200);
  }
  window.suyingToast = toast;

  document.addEventListener('click', (event)=>{
    const action = event.target.closest('[data-toast]');
    if(action) toast(action.getAttribute('data-toast'), action.getAttribute('data-toast-type') || 'info');

    const segButton = event.target.closest('.seg .s, .dir-btn, [data-toggle-group]');
    if(segButton && !segButton.hasAttribute('data-keep-active')){
      const group = segButton.closest('.seg,.dir-row,[data-toggle-scope]') || segButton.parentElement;
      if(group){
        group.querySelectorAll('.active,[aria-pressed="true"]').forEach((item)=>{
          if(item !== segButton){
            item.classList.remove('active');
            item.setAttribute('aria-pressed','false');
          }
        });
      }
      segButton.classList.add('active');
      segButton.setAttribute('aria-pressed','true');
    }

    const staticAction = event.target.closest('button:not([disabled]), .chip, .sector-cell, .pos-row, .ord-row');
    if(staticAction && !action && !staticAction.closest('.module-tabs') && !staticAction.closest('.dlg-mask') && !staticAction.getAttribute('onclick')){
      if(staticAction.classList.contains('chip')) staticAction.classList.toggle('active');
      const label = staticAction.textContent.trim().replace(/\s+/g,' ').slice(0,28);
      if(label && !staticAction.closest('.seg')) toast(label + ' 已更新预览状态', 'info');
    }

    const deadLink = event.target.closest('a[href="#"]');
    if(deadLink){
      event.preventDefault();
      toast((deadLink.textContent.trim() || '当前操作') + ' 已在原型中标记', 'info');
    }
  });

  document.addEventListener('input', (event)=>{
    const input = event.target;
    if(!input.matches('input,select,textarea')) return;
    const card = input.closest('.card,.order-panel,.info-card');
    if(card) card.setAttribute('data-dirty','true');
  });

  window.addEventListener('suying-theme-change', ()=>{
    if(window.echarts){
      document.querySelectorAll('div[id*="Chart"],div[id*="chart"]').forEach((node)=>{
        const instance = window.echarts.getInstanceByDom(node);
        if(instance) instance.resize();
      });
    }
  });

  if(window.echarts){
    window.addEventListener('resize', ()=>{
      document.querySelectorAll('div[id*="Chart"],div[id*="chart"]').forEach((node)=>{
        const instance = window.echarts.getInstanceByDom(node);
        if(instance) instance.resize();
      });
    });
  }

  /* 共享确认弹窗：替代原生 confirm()/alert()。用法：
     suyingConfirm('确认一键清仓？', ()=>{ ... }, {title:'高危操作', okText:'确认清仓', danger:true}); */
  function confirmDialog(message, onOk, opts){
    opts = opts || {};
    const mask = document.createElement('div');
    mask.className = 'dlg-mask';
    mask.innerHTML =
      '<div class="dlg" role="dialog" aria-modal="true">' +
        '<div class="dlg-title"></div>' +
        '<div class="dlg-body"></div>' +
        '<div class="dlg-ops"><button class="btn dlg-cancel">取消</button>' +
        '<button class="btn dlg-ok"></button></div>' +
      '</div>';
    mask.querySelector('.dlg-title').textContent = opts.title || '操作确认';
    mask.querySelector('.dlg-body').textContent = message;
    const okBtn = mask.querySelector('.dlg-ok');
    okBtn.textContent = opts.okText || '确认';
    if(opts.danger) okBtn.classList.add('danger'); else okBtn.classList.add('primary');
    function close(){ mask.remove(); document.removeEventListener('keydown', onKey); }
    function onKey(e){ if(e.key === 'Escape') close(); }
    mask.querySelector('.dlg-cancel').addEventListener('click', close);
    mask.addEventListener('click', (e)=>{ if(e.target === mask) close(); });
    okBtn.addEventListener('click', ()=>{ close(); if(typeof onOk === 'function') onOk(); });
    document.addEventListener('keydown', onKey);
    document.body.appendChild(mask);
    okBtn.focus();
  }
  window.suyingConfirm = confirmDialog;

  /* ECharts 主题助手：跟随 shell 的 data-theme（默认 dark）。
     页面初始化图表请用 echarts.init(dom, suyingEchartsTheme())，option 内禁止写 var(--xx)。 */
  window.suyingEchartsTheme = function(){
    return document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
  };
})();
