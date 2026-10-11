import { Elysia } from 'elysia';
import { join } from 'node:path';

export async function createApp() {
  const dist = join(import.meta.dir, 'dist');
  if (!await Bun.file(join(dist, 'index.html')).exists()) {
    throw new Error('Frontend assets are missing. Run bun run build first.');
  }
  const app = new Elysia().get('/healthz', () => ({ status: 'ok', service: 'tars-frontend' }));
  for await (const path of new Bun.Glob('**/*').scan({ cwd: dist, onlyFiles: true })) {
    if (!/\.(html|js|css|jpg|png|tif)$/.test(path)) continue;
    const file = Bun.file(join(dist, path));
    const gzipFile = Bun.file(join(dist, `${path}.gz`));
    const hasGzip = await gzipFile.exists();
    const handler = ({ request }: { request: Request }) => {
      const acceptsGzip = request.headers.get('accept-encoding')?.split(',').some(entry => {
        const [encoding, ...parameters] = entry.trim().toLowerCase().split(';');
        const quality = parameters.find(parameter => parameter.trim().startsWith('q='));
        const q = quality ? Number(quality.trim().slice(2)) : 1;
        return encoding === 'gzip' && q > 0 && q <= 1;
      });
      const compressed = hasGzip && acceptsGzip;
      const headers = new Headers({
        'Content-Type': file.type,
        'Cache-Control': path.endsWith('.html') ? 'no-cache' : /-[a-z0-9]{8,}\.(js|css)$/i.test(path) ? 'public, max-age=31536000, immutable' : 'public, max-age=300',
        'X-Content-Type-Options': 'nosniff',
        'Referrer-Policy': 'same-origin',
      });
      if (hasGzip) headers.set('Vary', 'Accept-Encoding');
      if (compressed) headers.set('Content-Encoding', 'gzip');
      return new Response(request.method === 'HEAD' ? null : compressed ? gzipFile : file, { headers });
    };
    // Register only generated public files; no user-supplied filesystem paths.
    app.get(`/${path}`, handler).head(`/${path}`, handler);
    if (path === 'index.html') app.get('/', handler).head('/', handler);
  }
  return app.compile();
}

if (import.meta.main) {
  const app = await createApp();
  app.listen({ hostname: '0.0.0.0', port: Number(process.env.PORT ?? 3000) });
  console.log(`Tars frontend listening on ${app.server!.url}`);
  process.on('SIGTERM', async () => { await app.stop(); process.exit(0); });
}
