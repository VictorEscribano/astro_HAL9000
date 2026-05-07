/**
 * 3D sky dome — Stellarium-style first-person POV using Three.js.
 *
 * Alt/Az → world XYZ:
 *   y = sin(alt)          ← up
 *   x = sin(az)*cos(alt)  ← East
 *   z = -cos(az)*cos(alt) ← South  (North is -Z)
 */
import { useEffect, useRef, useCallback } from "react";
import * as THREE from "three";
import { useAppStore } from "../../store";
import { api } from "../../api";

interface TrackPoint { alt: number; az: number; time: string }
interface Props { track?: TrackPoint[] }

const R = 490;

function altAzToVec3(alt: number, az: number): THREE.Vector3 {
  const a = (alt * Math.PI) / 180;
  const z = (az  * Math.PI) / 180;
  return new THREE.Vector3(
    Math.sin(z) * Math.cos(a),
    Math.sin(a),
    -Math.cos(z) * Math.cos(a),
  ).multiplyScalar(R);
}

function makeLabel(text: string, color = "rgba(230,234,240,0.75)", fontSize = 18): THREE.Sprite {
  const c = document.createElement("canvas");
  c.width = 256; c.height = 48;
  const ctx = c.getContext("2d")!;
  ctx.clearRect(0, 0, 256, 48);
  ctx.fillStyle = color;
  ctx.font = `${fontSize}px 'IBM Plex Mono', monospace`;
  ctx.fillText(text, 4, 36);
  const tex = new THREE.CanvasTexture(c);
  tex.needsUpdate = true;
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthTest: false }));
  sp.scale.set(60, 12, 1);
  return sp;
}

const PLANET_COLORS: Record<string, number> = {
  Mercury: 0xa0a0b0, Venus: 0xffe07a, Mars: 0xe06030,
  Jupiter: 0xc8a070, Saturn: 0xd4b060, Uranus: 0x80d8d8,
  Neptune: 0x4060d0, Moon: 0xe0e0e0, Sun: 0xfffcc0,
};

export default function SkyChart({ track }: Props) {
  const mountRef = useRef<HTMLDivElement>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const cameraRef   = useRef<THREE.PerspectiveCamera | null>(null);
  const sceneRef    = useRef<THREE.Scene | null>(null);
  const rafRef      = useRef(0);

  const objGroupRef   = useRef<THREE.Group | null>(null);
  const trackGroupRef = useRef<THREE.Group | null>(null);
  const selGroupRef   = useRef<THREE.Group | null>(null);
  const starPointsRef  = useRef<THREE.Points | null>(null);
  const starLabelGroup = useRef<THREE.Group | null>(null);

  // Camera control state (mutable refs — no re-render needed)
  const yaw   = useRef(0);   // current az (degrees)
  const pitch = useRef(15);  // current alt (degrees)
  const tYaw  = useRef(0);
  const tPitch = useRef(15);
  const drag  = useRef<{ x: number; y: number } | null>(null);

  const { skyObjects, selectedTarget } = useAppStore();

  // ── Build scene once ──────────────────────────────────────────────────────
  useEffect(() => {
    const el = mountRef.current;
    if (!el) return;

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    const W0 = el.clientWidth || 800;
    const H0 = el.clientHeight || 600;
    renderer.setSize(W0, H0, false);  // false = don't touch CSS
    Object.assign(renderer.domElement.style, { position: "absolute", inset: "0", width: "100%", height: "100%" });
    el.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    const scene = new THREE.Scene();
    sceneRef.current = scene;

    const camera = new THREE.PerspectiveCamera(70, W0 / H0, 0.1, 2000);
    camera.position.set(0, 1.7, 0);
    cameraRef.current = camera;

    // Sky hemisphere (inside-out so we see it from centre)
    scene.add(new THREE.Mesh(
      new THREE.SphereGeometry(R, 48, 24, 0, Math.PI * 2, 0, Math.PI / 2),
      new THREE.MeshBasicMaterial({ color: 0x000000, side: THREE.BackSide }),
    ));

    // Ground disk
    const floorMesh = new THREE.Mesh(
      new THREE.CircleGeometry(R * 1.1, 64),
      new THREE.MeshBasicMaterial({ color: 0x060806 }),
    );
    floorMesh.rotation.x = -Math.PI / 2;
    floorMesh.position.y = 0.0;
    scene.add(floorMesh);

    // Horizon ring
    const hPts = Array.from({ length: 361 }, (_, i) => altAzToVec3(0.2, i));
    scene.add(new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(hPts),
      new THREE.LineBasicMaterial({ color: 0x3BA7FF, opacity: 0.25, transparent: true }),
    ));

    // Alt rings 30°, 60°
    for (const alt of [30, 60]) {
      const pts = Array.from({ length: 361 }, (_, i) => altAzToVec3(alt, i));
      scene.add(new THREE.Line(
        new THREE.BufferGeometry().setFromPoints(pts),
        new THREE.LineBasicMaterial({ color: 0xffffff, opacity: 0.05, transparent: true }),
      ));
    }

    // Cardinal direction labels
    const dirs = [{ l: "N", az: 0 }, { l: "E", az: 90 }, { l: "S", az: 180 }, { l: "W", az: 270 }];
    for (const { l, az } of dirs) {
      const sp = makeLabel(l, l === "N" ? "#3BA7FF" : "rgba(230,234,240,0.5)", 28);
      const p = altAzToVec3(-3, az);
      sp.position.copy(p);
      scene.add(sp);
    }

    // Real star positions — populated after mount via API; start with empty geometry
    const starGeo = new THREE.BufferGeometry();
    starGeo.setAttribute("position", new THREE.Float32BufferAttribute([], 3));
    starGeo.setAttribute("color",    new THREE.Float32BufferAttribute([], 3));
    const starMat = new THREE.PointsMaterial({
      size: 2.0,
      sizeAttenuation: false,
      vertexColors: true,
      transparent: true,
      opacity: 0.92,
    });
    const starPoints = new THREE.Points(starGeo, starMat);
    scene.add(starPoints);
    starPointsRef.current = starPoints;

    const slg = new THREE.Group();
    scene.add(slg);
    starLabelGroup.current = slg;

    // Groups populated reactively
    const objGroup   = new THREE.Group(); scene.add(objGroup);
    const trackGroup = new THREE.Group(); scene.add(trackGroup);
    const selGroup   = new THREE.Group(); scene.add(selGroup);
    objGroupRef.current   = objGroup;
    trackGroupRef.current = trackGroup;
    selGroupRef.current   = selGroup;

    // Render loop
    function animate() {
      rafRef.current = requestAnimationFrame(animate);
      yaw.current   += (tYaw.current   - yaw.current)   * 0.1;
      pitch.current += (tPitch.current - pitch.current) * 0.1;

      const yR = (yaw.current   * Math.PI) / 180;
      const pR = (pitch.current * Math.PI) / 180;
      const look = new THREE.Vector3(
        Math.sin(yR) * Math.cos(pR),
        Math.sin(pR),
        -Math.cos(yR) * Math.cos(pR),
      );
      camera.lookAt(camera.position.clone().add(look));
      renderer.render(scene, camera);
    }
    animate();

    const ro = new ResizeObserver(() => {
      const W = el.clientWidth;
      const H = el.clientHeight;
      if (!W || !H) return;
      renderer.setSize(W, H, false);
      camera.aspect = W / H;
      camera.updateProjectionMatrix();
    });
    ro.observe(el);

    return () => {
      cancelAnimationFrame(rafRef.current);
      ro.disconnect();
      renderer.dispose();
      if (el.contains(renderer.domElement)) el.removeChild(renderer.domElement);
    };
  }, []);

  // ── Real star positions from HYG catalog ─────────────────────────────────────
  useEffect(() => {
    const pts = starPointsRef.current;
    if (!pts) return;

    api.starsTonight(5.5).then((data: Array<{name:string;alt_deg:number;az_deg:number;magnitude:number;color:string}>) => {
      const posArr: number[] = [];
      const colArr: number[] = [];

      const labelG = starLabelGroup.current;
      if (labelG) { while (labelG.children.length) labelG.remove(labelG.children[0]); }

      for (const star of data) {
        const v = altAzToVec3(star.alt_deg, star.az_deg);
        posArr.push(v.x, v.y, v.z);

        const c = new THREE.Color(star.color ?? "#ffffff");
        const brightness = Math.max(0.35, 1.0 - (star.magnitude - 1.0) * 0.14);
        colArr.push(c.r * brightness, c.g * brightness, c.b * brightness);

        // Label brightest named stars (mag < 1.5 with a proper name)
        if (labelG && star.magnitude < 1.5 && star.name && !/^\d/.test(star.name)) {
          const sp = makeLabel(star.name, `rgba(${Math.round(c.r*255)},${Math.round(c.g*255)},${Math.round(c.b*255)},0.7)`, 13);
          sp.position.set(v.x, v.y + 9, v.z);
          labelG.add(sp);
        }
      }

      const geo = pts.geometry;
      geo.setAttribute("position", new THREE.Float32BufferAttribute(posArr, 3));
      geo.setAttribute("color",    new THREE.Float32BufferAttribute(colArr, 3));
      geo.attributes.position.needsUpdate = true;
      geo.attributes.color.needsUpdate    = true;
      geo.computeBoundingSphere();
    }).catch(() => {
      // Fallback: procedural stars
      const posArr: number[] = [];
      const colArr: number[] = [];
      for (let i = 0; i < 2000; i++) {
        const phi   = Math.acos(1 - Math.random());
        const theta = Math.random() * 2 * Math.PI;
        const v = altAzToVec3((Math.PI / 2 - phi) * (180 / Math.PI), theta * (180 / Math.PI));
        posArr.push(v.x, v.y, v.z);
        const b = 0.5 + Math.random() * 0.5;
        colArr.push(b, b, b);
      }
      const geo = pts.geometry;
      geo.setAttribute("position", new THREE.Float32BufferAttribute(posArr, 3));
      geo.setAttribute("color",    new THREE.Float32BufferAttribute(colArr, 3));
    });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Sky colour (day / night) ─────────────────────────────────────────────────
  useEffect(() => {
    const renderer = rendererRef.current;
    const scene = sceneRef.current;
    if (!renderer || !scene) return;

    const sun = skyObjects.find((o) => o.name === "Sun");
    const sunAlt = sun?.alt_deg ?? -90;

    if (sunAlt > 0) {
      renderer.setClearColor(0x0d2a40, 1);
    } else if (sunAlt > -18) {
      const t = (sunAlt + 18) / 18;
      renderer.setClearColor(new THREE.Color(t * 0.06, t * 0.14, t * 0.25), 1);
    } else {
      renderer.setClearColor(0x000000, 1);
    }
  }, [skyObjects]);

  // ── Sky objects ──────────────────────────────────────────────────────────────
  useEffect(() => {
    const g = objGroupRef.current;
    if (!g) return;
    while (g.children.length) g.remove(g.children[0]);

    for (const obj of skyObjects) {
      if (obj.alt_deg == null || obj.az_deg == null || obj.alt_deg < -3) continue;

      const name = obj.name.split("(")[0].trim();
      const isPlanet = obj.object_type === "Planet";
      const colorHex = PLANET_COLORS[name] ?? 0x7dd3fc;

      const radius = isPlanet
        ? (name === "Sun" || name === "Moon" ? 7 : 4)
        : Math.max(1.5, Math.min(6, (obj.angular_size_arcmin ?? 1) / 3));

      const mesh = new THREE.Mesh(
        new THREE.SphereGeometry(radius, 10, 10),
        new THREE.MeshBasicMaterial({ color: colorHex }),
      );
      mesh.position.copy(altAzToVec3(obj.alt_deg, obj.az_deg));
      mesh.userData = obj;
      g.add(mesh);

      if (isPlanet) {
        const sp = makeLabel(name, "#e8f4fd", 16);
        const p = altAzToVec3(obj.alt_deg, obj.az_deg);
        sp.position.set(p.x, p.y + radius + 12, p.z);
        g.add(sp);
      }
    }
  }, [skyObjects]);

  // ── Selected target: crosshair + animate camera ──────────────────────────────
  useEffect(() => {
    const g = selGroupRef.current;
    if (!g) return;
    while (g.children.length) g.remove(g.children[0]);

    if (!selectedTarget) return;

    const obj = skyObjects.find(
      (o) => o.name === selectedTarget.name
          || o.catalog_id === selectedTarget.name
          || o.name.startsWith(selectedTarget.name)
    );
    if (!obj || obj.alt_deg == null || obj.az_deg == null) return;

    // Animate camera toward object
    tYaw.current   = obj.az_deg;
    tPitch.current = Math.max(5, obj.alt_deg);

    // Crosshair ring
    const ringGeo = new THREE.RingGeometry(8, 10, 32);
    const ringMat = new THREE.MeshBasicMaterial({ color: 0x34d399, side: THREE.DoubleSide, transparent: true, opacity: 0.9 });
    const ring = new THREE.Mesh(ringGeo, ringMat);
    const pos = altAzToVec3(obj.alt_deg, obj.az_deg);
    ring.position.copy(pos);
    ring.lookAt(0, 0, 0);
    g.add(ring);

    // Label
    const sp = makeLabel(`◉ ${selectedTarget.name}`, "#34d399", 15);
    sp.position.set(pos.x, pos.y + 14, pos.z);
    g.add(sp);
  }, [selectedTarget, skyObjects]);

  // ── Sky track ────────────────────────────────────────────────────────────────
  useEffect(() => {
    const g = trackGroupRef.current;
    if (!g) return;
    while (g.children.length) g.remove(g.children[0]);
    if (!track || track.length < 2) return;

    const pts = track.filter((p) => p.alt >= 0).map((p) => altAzToVec3(p.alt, p.az));
    if (pts.length < 2) return;

    g.add(new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(pts),
      new THREE.LineBasicMaterial({ color: 0x34d399, opacity: 0.55, transparent: true }),
    ));

    const dot = new THREE.Mesh(
      new THREE.SphereGeometry(4, 8, 8),
      new THREE.MeshBasicMaterial({ color: 0x34d399 }),
    );
    dot.position.copy(pts[0]);
    g.add(dot);
  }, [track]);

  // ── Pointer events ───────────────────────────────────────────────────────────
  const onPointerDown = useCallback((e: React.PointerEvent) => {
    drag.current = { x: e.clientX, y: e.clientY };
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  }, []);

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    if (!drag.current) return;
    const dx = e.clientX - drag.current.x;
    const dy = e.clientY - drag.current.y;
    drag.current = { x: e.clientX, y: e.clientY };
    tYaw.current   -= dx * 0.25;
    tPitch.current  = Math.max(-5, Math.min(89, tPitch.current + dy * 0.18));
  }, []);

  const onPointerUp = useCallback(() => { drag.current = null; }, []);

  const onWheel = useCallback((e: React.WheelEvent) => {
    const cam = cameraRef.current;
    if (!cam) return;
    cam.fov = Math.max(15, Math.min(100, cam.fov + e.deltaY * 0.04));
    cam.updateProjectionMatrix();
    e.preventDefault();
  }, []);

  return (
    <div
      ref={mountRef}
      className="relative w-full h-full cursor-grab active:cursor-grabbing select-none overflow-hidden"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerLeave={onPointerUp}
      onWheel={onWheel}
      style={{ touchAction: "none" }}
    />
  );
}
