import { useEffect, useRef } from "react";
import * as THREE from "three";
import { useAppStore } from "../../store";

// Smooth 3D noise (value noise via hash)
function hash3(x: number, y: number, z: number): number {
  let n = Math.sin(x * 127.1 + y * 311.7 + z * 74.7) * 43758.5453;
  return n - Math.floor(n);
}

function smoothNoise3(x: number, y: number, z: number): number {
  const ix = Math.floor(x), iy = Math.floor(y), iz = Math.floor(z);
  const fx = x - ix, fy = y - iy, fz = z - iz;
  const ux = fx * fx * (3 - 2 * fx);
  const uy = fy * fy * (3 - 2 * fy);
  const uz = fz * fz * (3 - 2 * fz);

  const n000 = hash3(ix,   iy,   iz);
  const n100 = hash3(ix+1, iy,   iz);
  const n010 = hash3(ix,   iy+1, iz);
  const n110 = hash3(ix+1, iy+1, iz);
  const n001 = hash3(ix,   iy,   iz+1);
  const n101 = hash3(ix+1, iy,   iz+1);
  const n011 = hash3(ix,   iy+1, iz+1);
  const n111 = hash3(ix+1, iy+1, iz+1);

  return (
    n000 * (1-ux)*(1-uy)*(1-uz) + n100 * ux*(1-uy)*(1-uz) +
    n010 * (1-ux)*   uy *(1-uz) + n110 * ux*   uy *(1-uz) +
    n001 * (1-ux)*(1-uy)*   uz  + n101 * ux*(1-uy)*   uz  +
    n011 * (1-ux)*   uy *   uz  + n111 * ux*   uy *   uz
  );
}

function fbm(x: number, y: number, z: number, octaves = 4): number {
  let v = 0, a = 0.5, freq = 1.8;
  for (let i = 0; i < octaves; i++) {
    v += a * smoothNoise3(x * freq, y * freq, z * freq);
    a *= 0.5; freq *= 2.1;
  }
  return v;
}

export default function AIOrb() {
  const mountRef = useRef<HTMLDivElement>(null);
  const { ollamaOnline } = useAppStore();
  // Use ref so animation loop always reads current value without recreating the renderer
  const onlineRef = useRef(ollamaOnline);
  onlineRef.current = ollamaOnline;

  useEffect(() => {
    const el = mountRef.current;
    if (!el) return;

    const W = el.clientWidth || 176;
    const H = el.clientHeight || 200;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    renderer.setSize(W, H, false);
    renderer.setClearColor(0x000000, 0);
    Object.assign(renderer.domElement.style, { position: "absolute", inset: "0", width: "100%", height: "100%" });
    el.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, W / H, 0.1, 100);
    camera.position.set(0, 0, 3.2);

    // ── Organic blob: icosphere-subdivided sphere with noise-displaced vertices ──
    const SEGMENTS = 64;
    const blobGeo = new THREE.SphereGeometry(1, SEGMENTS, SEGMENTS);
    const basePositions = blobGeo.attributes.position.array.slice() as Float32Array;
    const blobPos = blobGeo.attributes.position.array as Float32Array;

    // Surface point cloud — sample uniformly
    const SURFACE_POINTS = 1800;
    const surfacePos: number[] = [];
    for (let i = 0; i < SURFACE_POINTS; i++) {
      const u = Math.random(), v = Math.random();
      const theta = 2 * Math.PI * u;
      const phi = Math.acos(2 * v - 1);
      surfacePos.push(
        Math.sin(phi) * Math.cos(theta),
        Math.sin(phi) * Math.sin(theta),
        Math.cos(phi),
      );
    }
    const surfaceGeo = new THREE.BufferGeometry();
    const surfaceArr = new Float32Array(surfacePos);
    surfaceGeo.setAttribute("position", new THREE.BufferAttribute(surfaceArr, 3));

    const surfaceMat = new THREE.PointsMaterial({
      color: 0xffffff, size: 0.018, sizeAttenuation: true,
      transparent: true, opacity: 0.75,
    });
    const surfacePoints = new THREE.Points(surfaceGeo, surfaceMat);
    scene.add(surfacePoints);

    // Inner glow mesh (additive blending for volumetric feel)
    const glowGeo = new THREE.SphereGeometry(0.92, 32, 32);
    const glowMat = new THREE.MeshBasicMaterial({
      color: 0xff3b3b,
      transparent: true,
      opacity: 0.04,
      side: THREE.BackSide,
    });
    const glowMesh = new THREE.Mesh(glowGeo, glowMat);
    scene.add(glowMesh);

    // Halo particles (outer cloud)
    const HALO = 500;
    const haloPos: number[] = [];
    for (let i = 0; i < HALO; i++) {
      const r = 1.15 + Math.random() * 0.65;
      const theta = Math.random() * 2 * Math.PI;
      const phi = Math.random() * Math.PI;
      haloPos.push(
        r * Math.sin(phi) * Math.cos(theta),
        r * Math.sin(phi) * Math.sin(theta),
        r * Math.cos(phi),
      );
    }
    const haloGeo = new THREE.BufferGeometry();
    haloGeo.setAttribute("position", new THREE.Float32BufferAttribute(haloPos, 3));
    const haloMat = new THREE.PointsMaterial({
      color: 0xff6060, size: 0.012, sizeAttenuation: true,
      transparent: true, opacity: 0.2,
    });
    scene.add(new THREE.Points(haloGeo, haloMat));

    // Lights
    const redLight = new THREE.PointLight(0xff3b3b, 3.0, 8);
    redLight.position.set(1.2, 0.5, 1.5);
    scene.add(redLight);
    scene.add(new THREE.AmbientLight(0xffffff, 0.05));

    // ── Animation ───────────────────────────────────────────────────────────
    let raf = 0;
    let t = 0;

    function animate() {
      raf = requestAnimationFrame(animate);
      t += 0.008;

      // Displace surface points organically using fbm noise
      const noiseScale = 0.6;
      const noiseAmp = 0.28;
      for (let i = 0; i < SURFACE_POINTS; i++) {
        const ox = surfacePos[i * 3];
        const oy = surfacePos[i * 3 + 1];
        const oz = surfacePos[i * 3 + 2];

        // Animated noise offset
        const nx = ox * noiseScale + t * 0.15;
        const ny = oy * noiseScale + t * 0.12;
        const nz = oz * noiseScale + t * 0.18;
        const displacement = fbm(nx, ny, nz) * noiseAmp;

        const r = 1 + displacement;
        surfaceArr[i * 3]     = ox * r;
        surfaceArr[i * 3 + 1] = oy * r;
        surfaceArr[i * 3 + 2] = oz * r;
      }
      surfaceGeo.attributes.position.needsUpdate = true;

      // Deform the glow mesh similarly (lower freq for smoother glow)
      for (let i = 0; i < blobPos.length / 3; i++) {
        const ox = basePositions[i * 3];
        const oy = basePositions[i * 3 + 1];
        const oz = basePositions[i * 3 + 2];
        const d = fbm(ox * 0.5 + t * 0.1, oy * 0.5 + t * 0.08, oz * 0.5 + t * 0.12) * 0.18;
        blobPos[i * 3]     = ox * (1 + d);
        blobPos[i * 3 + 1] = oy * (1 + d);
        blobPos[i * 3 + 2] = oz * (1 + d);
      }
      blobGeo.attributes.position.needsUpdate = true;
      blobGeo.computeVertexNormals();

      // Slow rotation
      surfacePoints.rotation.y += 0.003;
      surfacePoints.rotation.x = 0.08 * Math.sin(t * 0.25);
      glowMesh.rotation.y += 0.002;

      // Breathing pulse
      const pulse = 0.94 + 0.06 * Math.sin(t * 0.65);
      surfacePoints.scale.setScalar(pulse);
      glowMesh.scale.setScalar(pulse * 1.05);

      // Dynamic glow color — reads ref so renderer is never recreated on status change
      if (onlineRef.current) {
        redLight.color.setHex(0xff3b3b);
        redLight.intensity = 2.5 + 1.2 * Math.sin(t * 1.1);
        surfaceMat.color.setHex(0xffffff);
      } else {
        redLight.color.setHex(0x333333);
        redLight.intensity = 0.5;
        surfaceMat.color.setHex(0x888888);
      }

      renderer.render(scene, camera);
    }
    animate();

    const ro = new ResizeObserver(() => {
      const W2 = el.clientWidth;
      const H2 = el.clientHeight;
      if (!W2 || !H2) return;
      renderer.setSize(W2, H2, false);
      camera.aspect = W2 / H2;
      camera.updateProjectionMatrix();
    });
    ro.observe(el);

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      renderer.dispose();
      if (el.contains(renderer.domElement)) el.removeChild(renderer.domElement);
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="flex flex-col h-full bg-bg relative">
      {/* Panel label */}
      <div className="px-3 pt-2 flex items-center justify-between shrink-0" style={{ zIndex: 2, position: "relative" }}>
        <span className="text-[calc(8px*var(--fs))] font-mono tracking-[0.2em] text-accent-red uppercase">
          AI CORE
        </span>
        <span className={`text-[calc(8px*var(--fs))] font-mono tracking-wider
          ${ollamaOnline ? "text-accent-red" : "text-dim"}`}>
          {ollamaOnline ? "● ACTIVE" : "○ OFFLINE"}
        </span>
      </div>

      {/* Three.js orb */}
      <div ref={mountRef} className="relative flex-1 min-h-0 overflow-hidden" />

      {/* Scan-line decoration at bottom */}
      <div className="px-3 pb-2 shrink-0" style={{ zIndex: 2, position: "relative" }}>
        <div className="flex gap-px h-3">
          {Array.from({ length: 20 }).map((_, i) => (
            <div key={i}
              className="flex-1 bg-accent-red/20"
              style={{ height: `${20 + Math.sin(i * 0.8) * 80}%`, alignSelf: "flex-end" }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
