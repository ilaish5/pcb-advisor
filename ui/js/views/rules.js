/* PCB Advisor UI - Rules view: preset rules, extra rules, calculators. */

async function loadRules() {
  try {
    RULES_DATA = await api('/api/rules', undefined, {soft: true});
    if (page === 'workspace' && tab === 'rules') renderCenter(true);
  } catch (e) { /* error toasted */ }
}

function rulesHTML(container) {
  const rd = RULES_DATA;
  if (!rd) {
    loadRules();
    return '<div class="dnote" style="margin:20px">Loading design rules and diff…</div>';
  }
  const p = rd.preset?.rules || [];
  const extra = rd.extra || [];
  const diff = rd.diff || [];
  const linked = rd.linked_pcb;

  return `<div class="vhead">
    <div>
      <h2>Design Rules & Calculators</h2>
      <p>JLC PCB capabilities preset, read-back diff against the linked PcbDoc, and engineering calculators.</p>
    </div>
    <div class="vacts">
      <a class="btn pri" href="/api/rules/export?${q()}" download="${esc(PROJECT)}-rules${linked ? '-board' : ''}.RUL">${linked ? 'Download .RUL (full board rule set)' : 'Download .RUL'}</a>
      ${linked ? `<a class="btn" href="/api/rules/export?${q()}&plain=1" download="${esc(PROJECT)}-rules.RUL">Preset only</a>` : ''}
    </div>
  </div>

  <div class="howto">
    <b>How to import the .RUL in Altium Designer</b>
    <ol style="margin:6px 0 0;padding-left:18px;display:grid;gap:4px">
      <li>Open your <b>.PcbDoc</b>, then <b>Design &raquo; Rules</b>.</li>
      <li>Right-click <b>Default Rule Set</b> and choose <b>Import Rules...</b>, pick the downloaded <span class="m">.RUL</span>, leave all rules ticked in <b>Select Design Rules</b> and click <b>Import</b>.</li>
      ${linked
        ? `<li>In <b>Rule Set Already Exists</b> choose <b>Replace existing rules</b>. This file carries all of the board's rules with the JLC values filled in, so nothing is lost.</li>`
        : `<li>In <b>Rule Set Already Exists</b> choose <b>Merge with existing rules</b>. Altium names the imported rules <span class="m">Clearance_1</span> etc. at a lower priority than your old ones, so afterwards open <b>Priorities...</b> and move each imported <span class="m">*_1</span> rule to the top (or delete the old rule of the same kind). Linking the PcbDoc in Settings gives a file you can import with <b>Replace</b> instead.</li>`}
      <li>Come back here and reload this tab: the diff reads the rules back from the PcbDoc and shows the effective (highest-priority) rule per kind.</li>
    </ol>
  </div>

  <div class="sgroup" style="margin-top:18px">
    <div class="sgh">
      <h3>JLC Preset Design Rules</h3>
      <p>Source: <a class="lnk" href="${esc(rd.preset?.capabilities_url || 'https://jlcpcb.com/capabilities/pcb-capabilities')}" target="_blank" rel="noopener">JLC PCB Capabilities</a></p>
    </div>
    <div class="tblwrap">
      <table class="libt">
        <thead><tr><th>Rule Name</th><th>Kind</th><th>Constraints</th><th>Scope</th><th>Description</th></tr></thead>
        <tbody>
          ${p.map(r => `<tr>
            <td class="m"><b>${esc(r.name)}</b></td>
            <td><span class="kind">${esc(r.kind)}</span></td>
            <td class="m">${esc(r.value || '—')}</td>
            <td>${esc(r.scope1 || 'All')}</td>
            <td>${esc(r.description || '')}</td>
          </tr>`).join('')}
        </tbody>
      </table>
    </div>
  </div>

  <div class="sgroup" style="margin-top:18px">
    <div class="sgh">
      <h3>Diff vs Linked PcbDoc</h3>
      <p>${linked ? `Comparing with <b class="m">${esc(linked)}</b>` : `No PcbDoc linked · Link one in <button class="btn" data-page="settings">Settings</button> to see live diff`}</p>
    </div>
    ${diff.length ? `
      <div class="tblwrap">
        <table class="libt">
          <thead><tr><th>Rule</th><th>Kind</th><th>Board Value</th><th>Preset Value</th><th>Status</th><th>Verdict</th></tr></thead>
          <tbody>
            ${diff.map(d => {
              const VERDICT = {same: ['ok', 'Same'], safer: ['ok', 'Safer'], tighter_ok: ['warn', 'Tighter, within fab limit'], below_fab_min: ['bad', 'Below fab min'], unknown: ['plan', 'Not judged']};
              const [vc, vl] = VERDICT[d.verdict] || VERDICT.unknown;
              const st = d.status || d.Status;
              const badge = st === 'match' ? '<span class="tag ok">Match</span>' :
                            st === 'differs' ? '<span class="tag warn">Differs</span>' :
                            st === 'missing_on_board' ? '<span class="tag bad">Missing on board</span>' :
                            '<span class="tag" style="background:var(--accent-soft);color:var(--accent)">Extra on board</span>';
              return `<tr>
                <td class="m"><b>${esc(d.rule || d.Rule || '')}</b></td>
                <td><span class="kind">${esc(d.kind || d.Kind || '')}</span></td>
                <td class="m">${esc(d['board value'] || d.board_value || '—')}</td>
                <td class="m">${esc(d['preset value'] || d.preset_value || '—')}</td>
                <td>${badge}</td>
                <td title="${esc(d.detail || '')}" style="white-space:normal;min-width:240px;max-width:380px"><span class="tag ${vc}">${vl}</span>${d.detail ? `<div class="dnote" style="margin-top:4px">${esc(d.detail)}</div>` : ''}</td>
              </tr>`;
            }).join('')}
          </tbody>
        </table>
      </div>` : '<div class="dnote">No rules found on board.</div>'}
  </div>

  <div class="sgroup" style="margin-top:18px">
    <div class="sgh">
      <h3>Extra Rules (Editable)</h3>
      <p>Custom rules included in the exported .RUL file</p>
    </div>
    ${extra.length ? `
      <div class="tblwrap" style="margin-bottom:10px">
        <table class="libt">
          <thead><tr><th>Rule Name</th><th>Kind</th><th>Scope</th><th>Value / Constraint</th></tr></thead>
          <tbody>
            ${extra.map(r => `<tr>
              <td class="m"><b>${esc(r.name)}</b></td>
              <td><span class="kind">${esc(r.kind)}</span></td>
              <td>${esc(r.scope1 || 'All')}</td>
              <td class="m">${esc(r.value || '')}</td>
            </tr>`).join('')}
          </tbody>
        </table>
      </div>` : '<div class="dnote" style="margin-bottom:10px">No extra rules defined yet.</div>'}

    <div class="card" style="padding:14px;max-width:580px;display:grid;gap:8px">
      <b>Add Extra Rule</b>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
        <div><label style="font-size:11.5px;color:var(--dim)">Name</label><input class="inp" id="er-name" placeholder="PowerNets_Width" style="width:100%;padding:4px 8px;border:1px solid var(--line);border-radius:6px"></div>
        <div><label style="font-size:11.5px;color:var(--dim)">Kind</label>
          <select class="inp" id="er-kind" style="width:100%;padding:4px 8px;border:1px solid var(--line);border-radius:6px">
            <option value="Width">Width</option>
            <option value="Clearance">Clearance</option>
            <option value="RoutingVias">RoutingVias</option>
            <option value="ComponentClearance">ComponentClearance</option>
          </select>
        </div>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
        <div><label style="font-size:11.5px;color:var(--dim)">Scope</label><input class="inp" id="er-scope" placeholder="InNetClass('PowerNets')" style="width:100%;padding:4px 8px;border:1px solid var(--line);border-radius:6px"></div>
        <div><label style="font-size:11.5px;color:var(--dim)">Value / Constraint</label><input class="inp" id="er-val" placeholder="20mil" style="width:100%;padding:4px 8px;border:1px solid var(--line);border-radius:6px"></div>
      </div>
      <div><button class="btn pri" data-act="add-extra-rule">+ Add Extra Rule</button></div>
    </div>
  </div>

  <div class="sgroup" style="margin-top:24px">
    <div class="sgh">
      <h3>Calculators</h3>
      <p>Deterministic calculators returning value, formula, and standard citations</p>
    </div>
    <div style="display:grid;grid-template-columns:repeat(auto-fill, minmax(min(100%, 300px), 1fr));gap:14px">

      <!-- Trace Width IPC-2152 -->
      <div class="card" style="padding:14px;display:grid;gap:8px">
        <b>Trace Width (IPC-2152)</b>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
          <div><label style="font-size:11px;color:var(--dim)">Current (A)</label><input type="number" step="0.1" id="calc-tw-i" value="1.5" class="inp" style="width:100%;padding:4px 8px;border:1px solid var(--line);border-radius:6px"></div>
          <div><label style="font-size:11px;color:var(--dim)">Temp Rise (°C)</label><input type="number" step="1" id="calc-tw-dt" value="10" class="inp" style="width:100%;padding:4px 8px;border:1px solid var(--line);border-radius:6px"></div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
          <div><label style="font-size:11px;color:var(--dim)">Copper (oz)</label><input type="number" step="0.5" id="calc-tw-oz" value="1.0" class="inp" style="width:100%;padding:4px 8px;border:1px solid var(--line);border-radius:6px"></div>
          <div style="display:flex;align-items:flex-end"><button class="btn pri" style="width:100%" data-calc="tw">Calculate</button></div>
        </div>
        <div id="res-tw" class="sidecar" style="display:none;margin-top:4px"></div>
      </div>

      <!-- Voltage Divider -->
      <div class="card" style="padding:14px;display:grid;gap:8px">
        <b>Voltage Divider (E24 Selection)</b>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
          <div><label style="font-size:11px;color:var(--dim)">Vin (V)</label><input type="number" step="0.1" id="calc-div-vin" value="5.0" class="inp" style="width:100%;padding:4px 8px;border:1px solid var(--line);border-radius:6px"></div>
          <div><label style="font-size:11px;color:var(--dim)">Target Vout (V)</label><input type="number" step="0.1" id="calc-div-vout" value="3.3" class="inp" style="width:100%;padding:4px 8px;border:1px solid var(--line);border-radius:6px"></div>
        </div>
        <div><button class="btn pri" style="width:100%" data-calc="div">Find Resistors</button></div>
        <div id="res-div" class="sidecar" style="display:none;margin-top:4px"></div>
      </div>

      <!-- LED Resistor -->
      <div class="card" style="padding:14px;display:grid;gap:8px">
        <b>LED Series Resistor</b>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px">
          <div><label style="font-size:11px;color:var(--dim)">Vsupply (V)</label><input type="number" step="0.1" id="calc-led-vs" value="5.0" class="inp" style="width:100%;padding:4px 8px;border:1px solid var(--line);border-radius:6px"></div>
          <div><label style="font-size:11px;color:var(--dim)">Vf (V)</label><input type="number" step="0.1" id="calc-led-vf" value="2.0" class="inp" style="width:100%;padding:4px 8px;border:1px solid var(--line);border-radius:6px"></div>
          <div><label style="font-size:11px;color:var(--dim)">If (mA)</label><input type="number" step="1" id="calc-led-if" value="20" class="inp" style="width:100%;padding:4px 8px;border:1px solid var(--line);border-radius:6px"></div>
        </div>
        <div><button class="btn pri" style="width:100%" data-calc="led">Calculate</button></div>
        <div id="res-led" class="sidecar" style="display:none;margin-top:4px"></div>
      </div>

      <!-- Via Current -->
      <div class="card" style="padding:14px;display:grid;gap:8px">
        <b>Via Current Capacity</b>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
          <div><label style="font-size:11px;color:var(--dim)">Drill Hole (mm)</label><input type="number" step="0.05" id="calc-via-d" value="0.3" class="inp" style="width:100%;padding:4px 8px;border:1px solid var(--line);border-radius:6px"></div>
          <div><label style="font-size:11px;color:var(--dim)">Temp Rise (°C)</label><input type="number" step="1" id="calc-via-dt" value="10" class="inp" style="width:100%;padding:4px 8px;border:1px solid var(--line);border-radius:6px"></div>
        </div>
        <div><button class="btn pri" style="width:100%" data-calc="via">Calculate Capacity</button></div>
        <div id="res-via" class="sidecar" style="display:none;margin-top:4px"></div>
      </div>

      <!-- Microstrip Impedance IPC-2141 -->
      <div class="card" style="padding:14px;display:grid;gap:8px">
        <b>Microstrip Impedance (IPC-2141)</b>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
          <div><label style="font-size:11px;color:var(--dim)">Width w (mm)</label><input type="number" step="0.05" id="calc-ms-w" value="0.3" class="inp" style="width:100%;padding:4px 8px;border:1px solid var(--line);border-radius:6px"></div>
          <div><label style="font-size:11px;color:var(--dim)">Height h (mm)</label><input type="number" step="0.05" id="calc-ms-h" value="0.2" class="inp" style="width:100%;padding:4px 8px;border:1px solid var(--line);border-radius:6px"></div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
          <div><label style="font-size:11px;color:var(--dim)">Dielectric Er</label><input type="number" step="0.1" id="calc-ms-er" value="4.4" class="inp" style="width:100%;padding:4px 8px;border:1px solid var(--line);border-radius:6px"></div>
          <div style="display:flex;align-items:flex-end"><button class="btn pri" style="width:100%" data-calc="ms">Calculate Z0</button></div>
        </div>
        <div id="res-ms" class="sidecar" style="display:none;margin-top:4px"></div>
      </div>

    </div>
  </div>`;
}

async function runCalculator(d) {
  if (d.calc === 'tw') {
    const cur = parseFloat($('#calc-tw-i').value) || 1.0;
    const rise = parseFloat($('#calc-tw-dt').value) || 10.0;
    const oz = parseFloat($('#calc-tw-oz').value) || 1.0;
    const res = await api(`/api/calc?type=trace_width&current=${cur}&rise=${rise}&oz=${oz}`);
    const box = $('#res-tw');
    box.style.display = 'block';
    box.innerHTML = `<b>Width: ${res.width_mm} mm (${res.width_mil} mil)</b><br><small style="color:var(--dim)">Formula: ${esc(res.formula)}<br>Source: ${esc(res.source)}</small>`;
  } else if (d.calc === 'div') {
    const vin = parseFloat($('#calc-div-vin').value) || 5.0;
    const vout = parseFloat($('#calc-div-vout').value) || 3.3;
    const res = await api(`/api/calc?type=divider&vin=${vin}&vout=${vout}`);
    const box = $('#res-div');
    box.style.display = 'block';
    box.innerHTML = `<b>Recommended E24: R1 = ${res.r1} Ω, R2 = ${res.r2} Ω</b><br>Actual Vout: <b>${res.vout} V</b> (error ${res.error_pct}%)<br><small style="color:var(--dim)">Formula: ${esc(res.formula)}<br>Source: ${esc(res.source)}</small>`;
  } else if (d.calc === 'led') {
    const vs = parseFloat($('#calc-led-vs').value) || 5.0;
    const vf = parseFloat($('#calc-led-vf').value) || 2.0;
    const if_ma = parseFloat($('#calc-led-if').value) || 20.0;
    const res = await api(`/api/calc?type=led&v_supply=${vs}&v_forward=${vf}&i_forward_ma=${if_ma}`);
    const box = $('#res-led');
    box.style.display = 'block';
    box.innerHTML = `<b>Standard E24 Resistor: ${res.r_standard_ohm} Ω</b> (exact: ${res.r_exact_ohm} Ω)<br>Power dissipation: <b>${res.power_w} W</b><br><small style="color:var(--dim)">Formula: ${esc(res.formula)}<br>Source: ${esc(res.source)}</small>`;
  } else if (d.calc === 'via') {
    const drill = parseFloat($('#calc-via-d').value) || 0.3;
    const rise = parseFloat($('#calc-via-dt').value) || 10.0;
    const res = await api(`/api/calc?type=via&drill_mm=${drill}&rise=${rise}`);
    const box = $('#res-via');
    box.style.display = 'block';
    box.innerHTML = `<b>Max current: ${res.current_a} A</b> (barrel area ${res.barrel_area_mil2} mil²)<br><small style="color:var(--dim)">Formula: ${esc(res.formula)}<br>Source: ${esc(res.source)}</small>`;
  } else if (d.calc === 'ms') {
    const w = parseFloat($('#calc-ms-w').value) || 0.3;
    const h = parseFloat($('#calc-ms-h').value) || 0.2;
    const er = parseFloat($('#calc-ms-er').value) || 4.4;
    const res = await api(`/api/calc?type=microstrip&width_mm=${w}&height_mm=${h}&er=${er}`);
    const box = $('#res-ms');
    box.style.display = 'block';
    box.innerHTML = `<b>Impedance Z0: ${res.z0_ohm} Ω</b><br><small style="color:var(--dim)">Formula: ${esc(res.formula)}<br>Source: ${esc(res.source)}</small>`;
  }
}

/* ---------- action + change handlers (dispatched by the delegates in core.js) ---------- */
onAct('add-extra-rule', async (el, d, e) => {
  const name = ($('#er-name')?.value || '').trim();
  const kind = $('#er-kind')?.value || 'Width';
  const scope1 = ($('#er-scope')?.value || 'All').trim();
  const val = ($('#er-val')?.value || '').trim();
  if (!name || !val) { toast('Please specify rule name and value'); return; }
  await api('/api/rules/extra', {rule: {name, kind, scope1, value: val}});
  toast('Extra rule added');
  await loadRules();
  render(true);
  return;
});
