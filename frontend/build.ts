import { copyFile, mkdir, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { TEXTURE_MAP } from './js/planetData.js';

const apiUrl = process.env.PUBLIC_API_URL ?? 'http://localhost:8000';
const parsedUrl = new URL(apiUrl);
if (!['http:', 'https:'].includes(parsedUrl.protocol) || parsedUrl.username || parsedUrl.password || parsedUrl.search || parsedUrl.hash) {
  throw new Error('PUBLIC_API_URL must be an HTTP(S) URL without credentials, query or fragment');
}
const define = {};
for (const name of ['PUBLIC_API_URL', 'PUBLIC_EPHEMERIS_URL', 'PUBLIC_JOBS_URL']) {
  const url = new URL(process.env[name] ?? apiUrl);
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
    throw new Error(`${name} must be an HTTP(S) URL without credentials, query or fragment`);
  }
  define[`process.env.${name}`] = JSON.stringify(url.toString().replace(/\/$/, ''));
}

const dist = join(import.meta.dir, 'dist');
await rm(dist, { recursive: true, force: true });
const result = await Bun.build({
  entrypoints: [join(import.meta.dir, 'index.html')],
  outdir: dist,
  target: 'browser',
  minify: true,
  env: 'disable',
  define,
});
if (!result.success) throw new AggregateError(result.logs, 'Frontend build failed');

// Texture paths are constructed at runtime, so the bundler cannot discover them.
await mkdir(join(dist, 'js/textures'), { recursive: true });
for (const name of new Set([...Object.values(TEXTURE_MAP), '4k_stars_milky_way.jpg'])) {
  await copyFile(join(import.meta.dir, 'js/textures', name), join(dist, 'js/textures', name));
}
for (const output of result.outputs) {
  if (/\.(html|js|css)$/.test(output.path)) {
    await Bun.write(`${output.path}.gz`, Bun.gzipSync(await output.arrayBuffer()));
  }
}
console.log(`Built ${result.outputs.length} frontend assets in ${dist}`);
