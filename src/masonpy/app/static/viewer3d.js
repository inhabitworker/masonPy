import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

// Python owns the geometry; this module owns rendering and navigation only.
/** Three.js rendering adapter; logical projection math stays in Python. */
export class WallViewer3D {

  /** @param {HTMLElement} host @param {Function} onSelect Create one renderer, camera and orbit/pick interaction. */
  constructor(host, onSelect) {
    this.host = host;
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0xffffff);
    this.camera = new THREE.PerspectiveCamera(45, 1, .01, 10000);
    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    const canvas = this.renderer.domElement;
    canvas.setAttribute("aria-label", "3D wall; drag to orbit, wheel to zoom, right-drag to pan");
    canvas.tabIndex = 0;
    host.append(canvas);
    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.addEventListener("change", () => this.draw());
    this.controls.addEventListener("start", () => { this.fitted = false; });
    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x8a8790, 2));
    const light = new THREE.DirectionalLight(0xffffff, 2.2);
    light.position.set(30, 50, 40);
    this.scene.add(light);
    this.content = new THREE.Group();
    this.scene.add(this.content);
    this.stones = new Map();
    this.raycaster = new THREE.Raycaster();
    this.bounds = new THREE.Box3(new THREE.Vector3(-1, 0, -1), new THREE.Vector3(1, 2, 1));
    let press = null;
    canvas.addEventListener("pointerdown", e => {
      press = e.isPrimary && e.button === 0 ? { x: e.clientX, y: e.clientY, time: performance.now(), moved: false } : null;
    });
    canvas.addEventListener("pointermove", e => {
      if (press && Math.hypot(e.clientX - press.x, e.clientY - press.y) > 5) press.moved = true;
    });
    canvas.addEventListener("pointercancel", () => { press = null; });
    canvas.addEventListener("pointerup", e => {
      const click = press && !press.moved && performance.now() - press.time < 300;
      press = null;
      if (!click) return;
      const rect = canvas.getBoundingClientRect();
      this.raycaster.setFromCamera(new THREE.Vector2(
        (e.clientX - rect.left) / rect.width * 2 - 1,
        -(e.clientY - rect.top) / rect.height * 2 + 1), this.camera);
      const objects = [...this.stones.values()].filter(item => item.mesh.visible).map(item => item.mesh);
      const hit = this.raycaster.intersectObjects(objects, false)[0];
      const core = this.primitive && this.raycaster.intersectObject(this.primitive, false)[0];
      // Surface stones and the core intentionally coincide at depth zero.
      // Prefer a stone at equal depth, but never pick through the near core.
      const occluded = core && (!hit || core.distance + this.pickTolerance < hit.distance);
      onSelect(occluded ? null : hit?.object.userData.stoneId ?? null);
    });
    this.observer = new ResizeObserver(() => this.resize());
    this.observer.observe(host);
    this.resize();
  }

  /** @param {Object} data @returns {THREE.BufferGeometry} Convert Python arrays and calculate face normals. */
  buffer(data) {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(data.vertices.flat(), 3));
    geometry.setIndex(data.triangles.flat());
    geometry.computeVertexNormals();
    return geometry;
  }

  /** @param {Object} data @param {Object} wall @param {Function} colour Dispose old buffers and rebuild visual objects only. */
  rebuild(data, wall, colour) {
    this.pickTolerance = wall.width * 1e-6;
    this.content.traverse(object => { object.geometry?.dispose(); object.material?.dispose(); });
    this.content.clear();
    this.stones.clear();
    this.primitive = null;
    for (const stone of data.stones) {
      const material = new THREE.MeshLambertMaterial({
        color: colour(stone.id), side: THREE.DoubleSide, flatShading: true,
        polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1
      });
      const mesh = new THREE.Mesh(this.buffer(stone), material);
      mesh.userData.stoneId = stone.id;
      const lines = new THREE.BufferGeometry();
      lines.setAttribute("position", new THREE.Float32BufferAttribute(stone.outlines.flat(), 3));
      const outline = new THREE.LineSegments(lines, new THREE.LineBasicMaterial({ color: 0x222222 }));
      this.content.add(mesh, outline);
      this.stones.set(stone.id, { mesh, outline });
    }
    if (data.primitive.triangles.length) {
      this.primitive = new THREE.Mesh(this.buffer(data.primitive),
        new THREE.MeshLambertMaterial({ color: 0xc4c4c4, side: THREE.DoubleSide, flatShading: true,
          polygonOffset: true, polygonOffsetFactor: 2, polygonOffsetUnits: 2 }));
      this.content.add(this.primitive);
    }
    this.bounds = new THREE.Box3().setFromObject(this.content);
    // Include the full intended wall even in empty and incremental scenes.
    const section = data.mode === "flat" ? [[-wall.width / 2, 0], [wall.width / 2, 0]] : data.section;
    for (const [x, z] of section) {
      this.bounds.expandByPoint(new THREE.Vector3(x, 0, z));
      this.bounds.expandByPoint(new THREE.Vector3(x, wall.height, z));
    }
    const key = `${wall.width}:${wall.height}:${data.mode}`;
    if (key !== this.key || this.fitted) { this.key = key; this.mode = data.mode; this.fit(); }
    this.draw();
  }

  /** @param {Object} wall @param {number} visibleCount @param {number|null} selectedId Apply selection and shallow visibility. */
  sync(wall, visibleCount, selectedId, hideSnecks) {
    wall.stones.forEach((stone, i) => {
      const item = this.stones.get(stone.id);
      if (!item) return;
      item.mesh.visible = item.outline.visible = i < visibleCount && !(hideSnecks && stone.traits.is_sneck);
      item.mesh.material.emissive.setHex(stone.id === selectedId ? 0x143458 : 0);
      item.outline.material.color.setHex(stone.id === selectedId ? 0x0645ad : 0x222222);
    });
    this.draw();
  }

  /** Frame the intended full wall, including an empty or partially generated source. */
  fit() {
    const center = this.bounds.getCenter(new THREE.Vector3());
    const radius = Math.max(1, this.bounds.getSize(new THREE.Vector3()).length() / 2);
    const vertical = THREE.MathUtils.degToRad(this.camera.fov) / 2;
    const horizontal = Math.atan(Math.tan(vertical) * this.camera.aspect);
    const distance = 1.12 * radius / Math.sin(Math.min(vertical, horizontal));
    const direction = this.mode === "projected" ? new THREE.Vector3(1, .5, 1).normalize() : new THREE.Vector3(0, 0, 1);
    this.camera.position.copy(center).addScaledVector(direction, distance);
    this.camera.near = Math.max(.001, radius / 1000);
    this.camera.far = distance + radius * 100;
    this.camera.updateProjectionMatrix();
    this.controls.target.copy(center);
    this.controls.minDistance = radius * .1;
    this.controls.maxDistance = radius * 50;
    this.controls.update();
    this.fitted = true;
    this.draw();
  }

  /** Match the canvas backing store and camera aspect to its visible host. */
  resize() {
    const { width, height } = this.host.getBoundingClientRect();
    if (!width || !height) return;
    this.renderer.setSize(width, height);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    if (this.fitted) this.fit();
    else this.draw();
  }

  /** Render once; OrbitControls changes and component updates request redraws, not a perpetual loop. */
  draw() { this.renderer.render(this.scene, this.camera); }
}
