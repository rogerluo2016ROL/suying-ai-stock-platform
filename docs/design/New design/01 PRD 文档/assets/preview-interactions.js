/* Shared interaction layer. Keeps legacy handlers intact and fills gaps on static controls. */
(function(){
  function toast(message, type){
    if(!message) return;
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
    if(staticAction && !action && !staticAction.closest('.module-tabs') && !staticAction.getAttribute('onclick')){
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
})();
