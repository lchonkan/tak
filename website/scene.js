import * as THREE from 'three';

// ── Setup ───────────────────────────────────────────────
const canvas = document.getElementById('bg-canvas');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight);

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 1000);
camera.position.set(0, 0, 30);

// ── Particle Wave Field ─────────────────────────────────
const COLS = 120;
const ROWS = 60;
const SPACING = 0.45;
const COUNT = COLS * ROWS;

const geometry = new THREE.BufferGeometry();
const positions = new Float32Array(COUNT * 3);
const basePositions = new Float32Array(COUNT * 3);
const colors = new Float32Array(COUNT * 3);
const sizes = new Float32Array(COUNT);

const colorA = new THREE.Color(0x58a6ff); // accent blue
const colorB = new THREE.Color(0xbc8cff); // purple
const colorC = new THREE.Color(0xf778ba); // pink

for (let i = 0; i < ROWS; i++) {
  for (let j = 0; j < COLS; j++) {
    const idx = (i * COLS + j) * 3;
    const x = (j - COLS / 2) * SPACING;
    const y = (i - ROWS / 2) * SPACING;
    positions[idx] = x;
    positions[idx + 1] = y;
    positions[idx + 2] = 0;
    basePositions[idx] = x;
    basePositions[idx + 1] = y;
    basePositions[idx + 2] = 0;

    // Color gradient based on position
    const t = j / COLS;
    const c = new THREE.Color();
    if (t < 0.5) {
      c.lerpColors(colorA, colorB, t * 2);
    } else {
      c.lerpColors(colorB, colorC, (t - 0.5) * 2);
    }
    colors[idx] = c.r;
    colors[idx + 1] = c.g;
    colors[idx + 2] = c.b;

    sizes[i * COLS + j] = Math.random() * 1.5 + 0.5;
  }
}

geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
geometry.setAttribute('size', new THREE.BufferAttribute(sizes, 1));

// Custom shader for round, soft particles
const vertexShader = `
  attribute float size;
  varying vec3 vColor;
  varying float vAlpha;

  void main() {
    vColor = color;
    vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
    float dist = length(mvPosition.xyz);
    vAlpha = smoothstep(60.0, 10.0, dist) * 0.8;
    gl_PointSize = size * (200.0 / -mvPosition.z);
    gl_Position = projectionMatrix * mvPosition;
  }
`;

const fragmentShader = `
  varying vec3 vColor;
  varying float vAlpha;

  void main() {
    float d = length(gl_PointCoord - vec2(0.5));
    if (d > 0.5) discard;
    float alpha = smoothstep(0.5, 0.1, d) * vAlpha;
    gl_FragColor = vec4(vColor, alpha);
  }
`;

const material = new THREE.ShaderMaterial({
  vertexShader,
  fragmentShader,
  vertexColors: true,
  transparent: true,
  depthWrite: false,
  blending: THREE.AdditiveBlending,
});

const particles = new THREE.Points(geometry, material);
scene.add(particles);

// ── Mouse tracking ──────────────────────────────────────
const mouse = { x: 0, y: 0, targetX: 0, targetY: 0 };

document.addEventListener('mousemove', (e) => {
  mouse.targetX = (e.clientX / window.innerWidth) * 2 - 1;
  mouse.targetY = -(e.clientY / window.innerHeight) * 2 + 1;
});

// ── Scroll tracking ─────────────────────────────────────
let scrollY = 0;
window.addEventListener('scroll', () => {
  scrollY = window.scrollY;
});

// ── Resize ──────────────────────────────────────────────
window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

// ── Animation Loop ──────────────────────────────────────
const clock = new THREE.Clock();

function animate() {
  requestAnimationFrame(animate);

  const t = clock.getElapsedTime();
  const posArr = geometry.attributes.position.array;

  // Smooth mouse follow
  mouse.x += (mouse.targetX - mouse.x) * 0.05;
  mouse.y += (mouse.targetY - mouse.y) * 0.05;

  // Scroll-based camera offset (subtle parallax)
  const scrollFactor = scrollY * 0.003;

  for (let i = 0; i < ROWS; i++) {
    for (let j = 0; j < COLS; j++) {
      const idx = (i * COLS + j) * 3;
      const bx = basePositions[idx];
      const by = basePositions[idx + 1];

      // Multi-layered wave displacement
      const wave1 = Math.sin(bx * 0.3 + t * 0.8) * Math.cos(by * 0.3 + t * 0.6) * 1.5;
      const wave2 = Math.sin(bx * 0.6 - t * 1.2 + by * 0.2) * 0.8;
      const wave3 = Math.cos(by * 0.5 + t * 0.5) * Math.sin(bx * 0.15 + t * 0.3) * 1.0;

      // Sound wave ripple from center
      const dist = Math.sqrt(bx * bx + by * by);
      const ripple = Math.sin(dist * 0.5 - t * 2.0) * Math.exp(-dist * 0.04) * 2.0;

      // Mouse influence
      const mx = mouse.x * 15;
      const my = mouse.y * 10;
      const mouseDist = Math.sqrt((bx - mx) * (bx - mx) + (by - my) * (by - my));
      const mouseInfluence = Math.exp(-mouseDist * 0.1) * 3.0;

      posArr[idx + 2] = wave1 + wave2 + wave3 + ripple + mouseInfluence;
    }
  }

  geometry.attributes.position.needsUpdate = true;

  // Camera movement
  particles.rotation.x = -0.2 + mouse.y * 0.05 - scrollFactor * 0.15;
  particles.rotation.y = mouse.x * 0.08;
  camera.position.y = -scrollFactor * 2;

  // Fade out as user scrolls down
  const fadeStart = window.innerHeight * 0.5;
  const fadeEnd = window.innerHeight * 2.5;
  const opacity = 1.0 - Math.min(1, Math.max(0, (scrollY - fadeStart) / (fadeEnd - fadeStart)));
  material.opacity = opacity;

  renderer.render(scene, camera);
}

animate();
