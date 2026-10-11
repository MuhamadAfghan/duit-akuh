/**
 * Generates the PWA icon set from public/logo/app-icon.svg.
 *
 * Run with: npm run gen:icons
 *
 * PRD FR16 requires 192 and 512 icons plus a maskable variant, and AC15
 * requires installing on a real iPhone, which needs an opaque PNG
 * apple-touch-icon. Everything here is derived from one SVG so the icons
 * cannot drift apart.
 */
import path from 'node:path';
import process from 'node:process';
import { mkdir, readFile, writeFile } from 'node:fs/promises';

import sharp from 'sharp';

const ROOT = path.resolve(import.meta.dirname, '..');
const SOURCE = path.join(ROOT, 'public/logo/app-icon.svg');
const OUT_DIR = path.join(ROOT, 'public/icons');

/**
 * `purpose: maskable` icons may be cropped to a circle, so platforms expect
 * the artwork to sit in the centre 80%. The source already respects that,
 * so the same render serves both purposes and we only vary the filename.
 */
const TARGETS = [
  { file: 'icon-192.png', size: 192 },
  { file: 'icon-512.png', size: 512 },
  { file: 'icon-maskable-192.png', size: 192 },
  { file: 'icon-maskable-512.png', size: 512 },
  // iOS ignores the manifest and reads this; it must not be transparent.
  { file: 'apple-touch-icon.png', size: 180, flatten: '#009A5B' },
];

async function main() {
  const svg = await readFile(SOURCE);
  await mkdir(OUT_DIR, { recursive: true });

  const results = await Promise.all(
    TARGETS.map(async ({ file, size, flatten }) => {
      let pipeline = sharp(svg, { density: 384 }).resize(size, size, {
        fit: 'contain',
        background: { r: 0, g: 0, b: 0, alpha: 0 },
      });

      if (flatten) {
        pipeline = pipeline.flatten({ background: flatten });
      }

      const buffer = await pipeline.png({ compressionLevel: 9 }).toBuffer();
      const target = path.join(OUT_DIR, file);
      await writeFile(target, buffer);

      const { width, height, channels } = await sharp(buffer).metadata();
      return { file, size, width, height, channels, bytes: buffer.length };
    })
  );

  for (const r of results) {
    const ok = r.width === r.size && r.height === r.size;
    console.log(
      `${ok ? 'ok  ' : 'FAIL'} ${r.file.padEnd(26)} ${r.width}x${r.height} ` +
        `${r.channels}ch ${r.bytes} bytes`
    );
    if (!ok) process.exitCode = 1;
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
