import { expect, test } from 'bun:test';

test('build produces a self-contained frontend', async () => {
  const build = Bun.spawn(['bun', 'run', 'build'], {
    cwd: import.meta.dir,
    env: { ...process.env, PUBLIC_API_URL: 'HTTP://LOCALHOST:8000/' },
    stdout: 'pipe', stderr: 'pipe',
  });
  const exitCode = await build.exited;
  const errors = await new Response(build.stderr).text();
  expect(exitCode, errors).toBe(0);
  const html = await Bun.file(`${import.meta.dir}/dist/index.html`).text();
  expect(html).not.toContain('importmap');
  expect(html).not.toContain('cdn.jsdelivr.net');
  const script = html.match(/src="([^"]+\.js)"/)![1];
  const javascript = await Bun.file(`${import.meta.dir}/dist/${script.replace(/^\.\//, '')}`).text();
  expect(javascript.includes('http://localhost:8000'), 'build should normalize the browser API URL').toBe(true);
  expect(await Bun.file(`${import.meta.dir}/dist/js/textures/2k_earth_daymap.jpg`).exists()).toBe(true);
  expect(await Bun.file(`${import.meta.dir}/dist/js/textures/8k_sun.jpg`).exists(), 'unused high-resolution Sun texture should not ship').toBe(false);
});

test('Elysia serves public assets, gzip negotiation, and safe cache policies', async () => {
  const module = await import('./server').catch(() => null);
  expect(module, 'frontend server has not been implemented').not.toBeNull();
  const app = await module!.createApp();
  const request = (path: string, headers: Record<string, string> = {}) => app.handle(new Request(`http://localhost${path}`, { headers }));
  const index = await request('/');
  expect(index.status).toBe(200);
  expect(index.headers.get('cache-control')).toBe('no-cache');
  const html = await index.text();
  const script = html.match(/src="([^"]+\.js)"/)![1];
  const url = '/' + script.replace(/^\.\//, '').replace(/^\//, '');
  const plain = await request(url);
  expect(plain.status).toBe(200);
  expect(plain.headers.get('content-type')).toContain('javascript');
  expect(plain.headers.get('cache-control')).toBe('public, max-age=31536000, immutable');
  expect(plain.headers.get('x-content-type-options')).toBe('nosniff');
  const compressed = await request(url, { 'accept-encoding': 'gzip' });
  expect(compressed.headers.get('content-encoding')).toBe('gzip');
  expect(compressed.headers.get('vary')).toBe('Accept-Encoding');
  expect(Bun.gunzipSync(await compressed.arrayBuffer())).toEqual(new Uint8Array(await plain.arrayBuffer()));
  expect((await request(url, { 'accept-encoding': 'gzip;q=0, br' })).headers.get('content-encoding')).toBeNull();
  expect((await request(url, { 'accept-encoding': 'GZIP; q=0.5' })).headers.get('content-encoding')).toBe('gzip');
  const head = await app.handle(new Request(`http://localhost${url}`, { method: 'HEAD' }));
  expect(head.status).toBe(200);
  expect(await head.text()).toBe('');
  expect((await request('/js/textures/2k_earth_daymap.jpg')).status).toBe(200);
  for (const path of ['/.env', '/server.ts', '/package.json', '/missing.js', '/%2e%2e%2fpackage.json']) {
    expect((await request(path)).status).toBe(404);
  }
  expect((await request('/healthz')).status).toBe(200);
});

test('build rejects credentials and unsupported protocols in the public API URL', async () => {
  for (const url of ['https://user:password@example.com', 'file:///private/api']) {
    const build = Bun.spawn(['bun', 'run', 'build'], {
      cwd: import.meta.dir,
      env: { ...process.env, PUBLIC_API_URL: url },
      stdout: 'ignore', stderr: 'pipe',
    });
    expect(await build.exited).not.toBe(0);
    expect(await new Response(build.stderr).text()).toContain('PUBLIC_API_URL must be an HTTP(S) URL');
    expect(await Bun.file(`${import.meta.dir}/dist/index.html`).exists()).toBe(true);
  }
});

test('same-origin build calls relative /api/v1 paths with no baked-in host', async () => {
  const build = (env: Record<string, string>) => Bun.spawn(['bun', 'run', 'build'], { cwd: import.meta.dir, env: { ...process.env, ...env }, stdout: 'ignore', stderr: 'pipe' }).exited;
  expect(await build({ PUBLIC_API_URL: 'same-origin' })).toBe(0);
  const bundle = (await Promise.all([...new Bun.Glob('dist/*.js').scanSync(import.meta.dir)].map(f => Bun.file(`${import.meta.dir}/${f}`).text()))).join('\n');
  expect(bundle).not.toContain('localhost');
  expect(bundle).toContain('/api/v1/ephemeris/');
  expect(await build({ PUBLIC_API_URL: 'HTTP://LOCALHOST:8000/' })).toBe(0); // restore the default build for later checks
});
