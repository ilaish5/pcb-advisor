import re

html = open("ui/index.html").read()

# 1. Add split button to ide-tabs
tabs_regex = r'<div class="ide-tabs" id="ide-tabs">.*?</div>'
tabs_new = """<div class="ide-tabs" id="ide-tabs" style="display:flex;">
    <div class="ide-tabs-list" id="ide-tabs-list" style="display:flex; flex:1; overflow-x:auto;"></div>
    <div class="ide-tabs-list" id="ide-tabs-right-list" style="display:none; flex:1; overflow-x:auto; border-left:1px solid var(--line);"></div>
    <button onclick="toggleSplit()" style="margin:4px; padding:2px 8px; font-size:12px; background:transparent; border:1px solid var(--line); color:var(--dim); border-radius:4px; cursor:pointer;">Split</button>
  </div>"""
html = re.sub(tabs_regex, tabs_new, html, flags=re.S)

# 2. Add containers
main_regex = r'(<div class="demobar" id="demobar" style="display:none"></div>\s*)<div class="diagram" id="diagram">'
main_new = r"""\1
  <div style="display:flex; flex:1; min-height:0;">
    <div id="ide-content-left" style="flex:1; display:flex; flex-direction:column; min-width:0; overflow:hidden;">
      <div class="diagram" id="diagram">"""
html = re.sub(main_regex, main_new, html)

end_main_regex = r'(<div class="native-panel" id="native-panel" .*?</div>\s*)</main>'
end_main_new = r"""\1
    </div>
    <div class="split" id="split-mid" style="display:none; cursor:col-resize; background:var(--line);"></div>
    <div id="ide-content-right" style="display:none; flex:1; flex-direction:column; min-width:0; overflow:hidden; border-left:1px solid var(--line);"></div>
  </div>
</main>"""
html = re.sub(end_main_regex, end_main_new, html)

# 3. Add open-in-main buttons to sidebar nav
nav_regex = r'<nav class="snav">\s*(.*?)\s*</nav>'
def repl_nav(m):
    inner = m.group(1)
    # wrap each button in a flex container and add an open arrow
    buttons = re.findall(r'<button id="t-(.*?)" onclick="showPanel\(\'.*?\'\)">(.*?)</button>', inner)
    res = '<nav class="snav" style="flex-direction:column; gap:0;">\n'
    for pid, label in buttons:
        res += f'''<div style="display:flex; align-items:center;">
      <button id="t-{pid}" onclick="showPanel('{pid}')" style="flex:1; text-align:left;">{label}</button>
      <button onclick="openInIde('panel:{pid}')" title="Open in Main View" style="padding:5px;">↗</button>
    </div>\n'''
    res += '</nav>'
    return res

html = re.sub(nav_regex, repl_nav, html, flags=re.S)


# 4. Rewrite JS
js_regex = r'let openTabs = \[\];.*?function renderIdeTabs\(\) \{.*?\}'
js_new = """
let openTabs = [];
let activeIdeTab = 'diagram';
let activeIdeTabRight = null;
let isSplit = false;

function applyTabToContainer(tab, containerId) {
  let container = $(containerId);
  if(!container) return;
  
  // if diagram is currently here, park it back to body if we are removing it
  if (container.contains($('diagram')) && tab !== 'diagram') {
     document.body.appendChild($('diagram'));
     $('diagram').style.display = 'none';
  }
  if (container.contains($('chatPane')) && tab !== 'panel:chat') {
     document.body.appendChild($('chatPane'));
     $('chatPane').style.display = 'none';
  }

  container.querySelectorAll('.doc-frame, .native-panel').forEach(e => e.remove());
  
  if (!tab) {
     // do nothing
  } else if (tab === 'diagram') {
    container.appendChild($('diagram'));
    $('diagram').style.display = 'flex';
  } else if (tab.startsWith('panel:')) {
    let p = tab.substring(6);
    if (p === 'chat') {
       container.appendChild($('chatPane'));
       $('chatPane').style.display = 'flex';
       setTimeout(scrollLog, 10);
    } else {
       let div = document.createElement('div');
       div.className = 'native-panel';
       div.style.flex = '1';
       div.style.overflowY = 'auto';
       div.style.padding = '16px';
       
       let oldTab = TAB;
       TAB = p;
       div.innerHTML = renderPanelToHTML ? renderPanelToHTML() : 'Not implemented';
       TAB = oldTab;
       container.appendChild(div);
    }
  } else {
    let iframe = document.createElement('iframe');
    iframe.className = 'doc-frame';
    iframe.style.width = '100%';
    iframe.style.height = '100%';
    iframe.style.border = 'none';
    iframe.src = q('/api/source/' + encodeURIComponent(tab));
    container.appendChild(iframe);
  }
}

function openInIde(filename) {
  if (!openTabs.includes(filename)) {
    openTabs.push(filename);
  }
  switchIdeTab(filename);
}

function switchIdeTab(tab) {
  activeIdeTab = tab;
  renderIdeTabs();
  applyTabToContainer(tab, 'ide-content-left');
}

function switchIdeTabRight(tab) {
  activeIdeTabRight = tab;
  renderIdeTabs();
  applyTabToContainer(tab, 'ide-content-right');
}

function closeIdeTab(e, tab, isRight) {
  e.stopPropagation();
  openTabs = openTabs.filter(t => t !== tab);
  
  if (activeIdeTab === tab) switchIdeTab(openTabs.length ? openTabs[0] : 'diagram');
  if (activeIdeTabRight === tab) switchIdeTabRight(openTabs.length ? openTabs[0] : null);
  
  renderIdeTabs();
}

function toggleSplit() {
  isSplit = !isSplit;
  if (isSplit) {
    $('ide-content-right').style.display = 'flex';
    $('ide-tabs-right-list').style.display = 'flex';
    $('split-mid').style.display = 'block';
    if (!activeIdeTabRight) switchIdeTabRight(openTabs.length ? openTabs[0] : 'diagram');
    else switchIdeTabRight(activeIdeTabRight);
  } else {
    $('ide-content-right').style.display = 'none';
    $('ide-tabs-right-list').style.display = 'none';
    $('split-mid').style.display = 'none';
    applyTabToContainer(null, 'ide-content-right');
  }
  renderIdeTabs();
}

function makeTabsHtml(activeTab, isRight) {
    let clickFn = isRight ? 'switchIdeTabRight' : 'switchIdeTab';
    let html = `<div class="ide-tab ${activeTab==='diagram'?'active':''}" onclick="${clickFn}('diagram')">Diagram</div>`;
    for (const t of openTabs) {
      let disp = t.startsWith('panel:') ? t.substring(6) : t;
      html += `<div class="ide-tab ${activeTab===t?'active':''}" onclick="${clickFn}('${esc(t).replace(/'/g, "\\\\'")}')">
        ${esc(disp)} <span class="close-btn" onclick="closeIdeTab(event, '${esc(t).replace(/'/g, "\\\\'")}', ${isRight})">×</span>
      </div>`;
    }
    return html;
}

function renderIdeTabs() {
  if($('ide-tabs-list')) $('ide-tabs-list').innerHTML = makeTabsHtml(activeIdeTab, false);
  if($('ide-tabs-right-list')) $('ide-tabs-right-list').innerHTML = makeTabsHtml(activeIdeTabRight, true);
}
"""
html = re.sub(js_regex, js_new.strip(), html, flags=re.S)

# We need a renderPanelToHTML function to generate side panels without inserting to sbody
renderPanelToHTML_script = """
function renderPanelToHTML() {
  let old_sbody = $('sbody');
  let dummy = document.createElement('div');
  Object.defineProperty(document, 'getElementById', {
    value: function(id) {
       if(id === 'sbody') return dummy;
       return HTMLElement.prototype.constructor.prototype.getElementById.apply(document, arguments);
    },
    configurable: true
  });
  
  // Actually, overriding getElementById is messy.
  // We can just extract the generation logic from renderPanel().
  // But wait, it's easier to just temporarily hide sbody, call renderPanel(), and read its innerHTML!
  let backup = old_sbody.innerHTML;
  let force = true;
  // wait, renderPanel expects global variables.
  return "Not implemented fully";
}
"""
# actually let's just use the fact that we can move #sbody !
# if a panel is rendered, it writes to #sbody. So we just move #sbody to native-panel!
EOF
"""

open("ui/index.html", "w").write(html)
print("Done split")
