import React, { useRef, useEffect, useCallback } from 'react';

interface Particle {
  baseX: number;
  baseY: number;
  x: number;
  y: number;
  vx: number;
  vy: number;
  radius: number;
  opacity: number;
  hue: 'dark' | 'muted' | 'emerald';
  neighbors: number[];
}

const COLORS = {
  dark: '24, 24, 24',
  muted: '140, 136, 128',
  emerald: '16, 185, 129',
} as const;

const INFLUENCE_RADIUS = 160;
const REPULSION_STRENGTH = 2.8;
const SPRING = 0.04;
const DAMPING = 0.82;
const DRIFT_SPEED = 0.15;
const TARGET_PARTICLES = 380;

function createParticles(width: number, height: number): Particle[] {
  const spacing = Math.sqrt((width * height) / TARGET_PARTICLES);
  const cols = Math.ceil(width / spacing) + 1;
  const rows = Math.ceil(height / spacing) + 1;
  const particles: Particle[] = [];
  const indexAt = new Map<string, number>();

  for (let row = 0; row < rows; row++) {
    for (let col = 0; col < cols; col++) {
      const jitterX = (Math.random() - 0.5) * spacing * 0.45;
      const jitterY = (Math.random() - 0.5) * spacing * 0.45;
      const x = col * spacing + jitterX;
      const y = row * spacing + jitterY;

      const roll = Math.random();
      const hue: Particle['hue'] = roll > 0.92 ? 'emerald' : roll > 0.7 ? 'muted' : 'dark';

      indexAt.set(`${row},${col}`, particles.length);
      particles.push({
        baseX: x,
        baseY: y,
        x,
        y,
        vx: 0,
        vy: 0,
        radius: hue === 'emerald' ? 2.2 : hue === 'muted' ? 1.6 : 1.3,
        opacity: hue === 'emerald' ? 0.55 : hue === 'muted' ? 0.35 : 0.22,
        hue,
        neighbors: [],
      });
    }
  }

  for (let row = 0; row < rows; row++) {
    for (let col = 0; col < cols; col++) {
      const idx = indexAt.get(`${row},${col}`);
      if (idx === undefined) continue;
      const neighborCoords = [
        [row, col + 1],
        [row + 1, col],
        [row + 1, col + 1],
        [row + 1, col - 1],
      ];
      for (const [r, c] of neighborCoords) {
        const nIdx = indexAt.get(`${r},${c}`);
        if (nIdx !== undefined) particles[idx].neighbors.push(nIdx);
      }
    }
  }

  return particles;
}

function drawParticleField(
  ctx: CanvasRenderingContext2D,
  particles: Particle[],
  width: number,
  height: number,
) {
  ctx.clearRect(0, 0, width, height);

  const drawn = new Set<string>();

  for (let i = 0; i < particles.length; i++) {
    const a = particles[i];
    for (const j of a.neighbors) {
      if (j <= i) continue;
      const key = `${i}-${j}`;
      if (drawn.has(key)) continue;
      drawn.add(key);

      const b = particles[j];
      const dx = a.x - b.x;
      const dy = a.y - b.y;
      const dist = Math.hypot(dx, dy);
      const maxDist = Math.hypot(a.baseX - b.baseX, a.baseY - b.baseY) * 1.6;
      if (dist > maxDist) continue;

      const alpha = (1 - dist / maxDist) * 0.14;
      ctx.beginPath();
      ctx.strokeStyle = `rgba(140, 136, 128, ${alpha})`;
      ctx.lineWidth = 0.6;
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
    }
  }

  for (const p of particles) {
    const rgb = COLORS[p.hue];
    ctx.beginPath();
    ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(${rgb}, ${p.opacity})`;
    ctx.fill();
  }
}

function stepParticles(
  particles: Particle[],
  mouseX: number,
  mouseY: number,
  mouseActive: boolean,
  time: number,
  reducedMotion: boolean,
) {
  for (const p of particles) {
    if (!reducedMotion) {
      p.baseX += Math.sin(time * 0.0004 + p.baseY * 0.01) * DRIFT_SPEED;
      p.baseY += Math.cos(time * 0.00035 + p.baseX * 0.01) * DRIFT_SPEED;
    }

    if (mouseActive && !reducedMotion) {
      const dx = p.x - mouseX;
      const dy = p.y - mouseY;
      const dist = Math.hypot(dx, dy);

      if (dist < INFLUENCE_RADIUS && dist > 0.5) {
        const force = (1 - dist / INFLUENCE_RADIUS) * REPULSION_STRENGTH;
        p.vx += (dx / dist) * force;
        p.vy += (dy / dist) * force;
      }
    }

    p.vx += (p.baseX - p.x) * SPRING;
    p.vy += (p.baseY - p.y) * SPRING;
    p.vx *= DAMPING;
    p.vy *= DAMPING;
    p.x += p.vx;
    p.y += p.vy;
  }
}

export const ImmersiveBackground: React.FC = () => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const particlesRef = useRef<Particle[]>([]);
  const mouseRef = useRef({ x: -9999, y: -9999, active: false });
  const frameRef = useRef<number>(0);
  const reducedMotionRef = useRef(false);

  const resize = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const width = window.innerWidth;
    const height = window.innerHeight;

    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;

    const ctx = canvas.getContext('2d');
    if (ctx) ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    particlesRef.current = createParticles(width, height);
  }, []);

  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    const updateMotion = () => {
      reducedMotionRef.current = mq.matches;
    };
    updateMotion();
    mq.addEventListener('change', updateMotion);

    resize();
    window.addEventListener('resize', resize);

    const onPointerMove = (e: MouseEvent | TouchEvent) => {
      const point = 'touches' in e ? e.touches[0] : e;
      if (!point) return;
      mouseRef.current = { x: point.clientX, y: point.clientY, active: true };
    };

    const onPointerLeave = () => {
      mouseRef.current.active = false;
    };

    window.addEventListener('mousemove', onPointerMove, { passive: true });
    window.addEventListener('touchmove', onPointerMove, { passive: true });
    window.addEventListener('mouseleave', onPointerLeave);

    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const animate = (time: number) => {
      const width = window.innerWidth;
      const height = window.innerHeight;
      const { x, y, active } = mouseRef.current;

      stepParticles(particlesRef.current, x, y, active, time, reducedMotionRef.current);
      drawParticleField(ctx, particlesRef.current, width, height);

      frameRef.current = requestAnimationFrame(animate);
    };

    frameRef.current = requestAnimationFrame(animate);

    return () => {
      cancelAnimationFrame(frameRef.current);
      window.removeEventListener('resize', resize);
      window.removeEventListener('mousemove', onPointerMove);
      window.removeEventListener('touchmove', onPointerMove);
      window.removeEventListener('mouseleave', onPointerLeave);
      mq.removeEventListener('change', updateMotion);
    };
  }, [resize]);

  return (
    <div className="immersive-bg" aria-hidden>
      <div className="immersive-bg__gradient" />
      <canvas ref={canvasRef} className="immersive-bg__particles" />
      <div className="immersive-bg__vignette" />
      <div className="immersive-bg__grain" />
    </div>
  );
};
