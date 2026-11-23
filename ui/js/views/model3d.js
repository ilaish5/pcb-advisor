/* The 3D part of the Library quick preview: drag to rotate, scroll to zoom. Loaded on demand, so the page costs nothing until a
   3D preview opens. Everything it needs is under /ui/vendor (see ui/vendor/README.md): three.js with its VRML loader for a .wrl,
   occt-import-js (OpenCascade, WebAssembly) for a STEP file. Nothing is fetched from the internet.
   m3dStart(box, line, info) -> {dispose(), tris, ready}; info is what /api/library/preview?kind=model said ({step, wrl}).
   KiCad models (STEP and the .wrl files made from them) are Z up, so the camera's up is Z; the view is framed on the model's own
   bounding box, whatever its unit. */
const M3D_VENDOR = '/ui/vendor/';
let m3dOcct = null;               // the STEP reader, started once and kept

function m3dScript(src) {
  return new Promise((ok, bad) => {
    const s = document.createElement('script');
    s.src = src;
    s.onload = ok;
    s.onerror = () => bad(new Error('Could not load ' + src));
    document.head.appendChild(s);
  });
}
async function m3dBytes(line, format) {
  const r = await fetch('/api/library/model?' + q({line, format}), {headers: {'X-Usage-Session': window.USAGE_SESSION || ''}});
  if (!r.ok) {
    let msg = 'The 3D file could not be loaded';
    try { msg = (await r.json()).error || msg; } catch (e) { /* keep the generic sentence */ }
    throw new Error(msg);
  }
  return r;
}
async function m3dFromStep(THREE, line) {
  if (!m3dOcct) {
    if (typeof occtimportjs === 'undefined') await m3dScript(M3D_VENDOR + 'occt/occt-import-js.js');
    m3dOcct = occtimportjs({locateFile: f => M3D_VENDOR + 'occt/' + f});
  }
  const occt = await m3dOcct;
  const data = new Uint8Array(await (await m3dBytes(line, 'step')).arrayBuffer());
  const res = occt.ReadStepFile(data, null);
  if (!res || !res.success || !(res.meshes || []).length) throw new Error('The STEP file could not be read');
  const group = new THREE.Group();
  for (const m of res.meshes) {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(m.attributes.position.array, 3));
    if (m.attributes.normal) g.setAttribute('normal', new THREE.Float32BufferAttribute(m.attributes.normal.array, 3));
    g.setIndex(new THREE.BufferAttribute(Uint32Array.from(m.index.array), 1));
    if (!m.attributes.normal) g.computeVertexNormals();
    const c = m.color ? new THREE.Color(m.color[0], m.color[1], m.color[2]) : new THREE.Color(0x8c8c93);
    group.add(new THREE.Mesh(g, new THREE.MeshStandardMaterial({color: c, metalness: 0.15, roughness: 0.55, side: THREE.DoubleSide})));
  }
  return group;
}
async function m3dFromWrl(line) {
  const {VRMLLoader} = await import(M3D_VENDOR + 'three/examples/jsm/loaders/VRMLLoader.js');
  const text = await (await m3dBytes(line, 'wrl')).text();
  return new VRMLLoader().parse(text, '');
}

async function m3dStart(box, line, info) {
  const THREE = await import('three');                       // the importmap in index.html points it at /ui/vendor/three
  const {OrbitControls} = await import(M3D_VENDOR + 'three/examples/jsm/controls/OrbitControls.js');
  let dead = false, raf = 0;
  const w = box.clientWidth || 640, h = box.clientHeight || 380;
  const renderer = new THREE.WebGLRenderer({antialias: true, alpha: true, preserveDrawingBuffer: true});
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(w, h);
  const cv = renderer.domElement;
  cv.className = 'mp-canvas';
  cv.setAttribute('role', 'img');
  cv.setAttribute('aria-label', '3D model. Drag to rotate, scroll to zoom.');
  box.appendChild(cv);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(35, w / h, 0.01, 10000);
  camera.up.set(0, 0, 1);
  scene.add(new THREE.AmbientLight(0xffffff, 1.4));
  scene.add(new THREE.HemisphereLight(0xffffff, 0x555566, 1.2));
  const sun = new THREE.DirectionalLight(0xffffff, 2.2);
  camera.add(sun);
  scene.add(camera);
  const controls = new OrbitControls(camera, cv);
  const draw = () => { if (!dead) renderer.render(scene, camera); };
  const dispose = () => {
    dead = true;
    cancelAnimationFrame(raf);
    ro.disconnect();
    controls.dispose();
    scene.traverse(o => {
      if (o.geometry) o.geometry.dispose();
      [].concat(o.material || []).forEach(m => m.dispose());
    });
    renderer.dispose();
    renderer.forceContextLoss();
    cv.remove();
  };
  const ro = new ResizeObserver(() => {
    const W = box.clientWidth, H = box.clientHeight;
    if (!W || !H || dead) return;
    renderer.setSize(W, H);
    camera.aspect = W / H;
    camera.updateProjectionMatrix();
    draw();
  });
  ro.observe(box);
  const out = {dispose, tris: 0, ready: null};
  out.ready = (async () => {
    const model = info.wrl ? await m3dFromWrl(line) : await m3dFromStep(THREE, line);
    if (dead) return out;
    const b = new THREE.Box3().setFromObject(model);
    if (b.isEmpty()) throw new Error('The 3D file holds no shape');
    const size = b.getSize(new THREE.Vector3()), ctr = b.getCenter(new THREE.Vector3());
    const pivot = new THREE.Group();
    model.position.sub(ctr);
    pivot.add(model);
    scene.add(pivot);
    model.traverse(o => {
      if (o.isMesh && o.geometry) {
        const g = o.geometry;
        out.tris += g.index ? g.index.count / 3 : (g.attributes.position ? g.attributes.position.count / 3 : 0);
      }
    });
    const r = Math.max(size.x, size.y, size.z) || 1;
    const dist = r / (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2))) * 1.9;
    camera.position.set(0.8, -1.0, 0.75).normalize().multiplyScalar(dist);
    camera.near = r / 100;
    camera.far = r * 100;
    camera.updateProjectionMatrix();
    controls.target.set(0, 0, 0);
    controls.minDistance = r * 0.4;
    controls.maxDistance = r * 12;
    controls.addEventListener('change', draw);
    controls.update();
    draw();
    box.dataset.tris = String(Math.round(out.tris));
    box.dataset.size = [size.x, size.y, size.z].map(v => v.toFixed(3)).join('x');
    return out;
  })();
  out.ready.catch(() => dispose());
  return out;
}
