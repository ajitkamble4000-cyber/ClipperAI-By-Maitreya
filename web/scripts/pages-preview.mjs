// Serve the static build (out/) the way GitHub Pages does, to try it locally:
//   STATIC_EXPORT=1 PAGES_BASE_PATH=/ClipperAI-By-Maitreya npx next build
//   node scripts/pages-preview.mjs /ClipperAI-By-Maitreya 3000
// Folders serve index.html, folder URLs without a trailing slash redirect, and anything missing gets 404.html.
import { createReadStream, existsSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize } from "node:path";

const base = (process.argv[2] ?? "").replace(/\/$/, "");
const port = Number(process.argv[3] ?? 3000);
const root = join(process.cwd(), "out");
const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".txt": "text/plain; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon", ".woff2": "font/woff2", ".ttf": "font/ttf" };

function send(res, status, file) {
  res.writeHead(status, { "Content-Type": TYPES[extname(file)] ?? "application/octet-stream" });
  createReadStream(file).pipe(res);
}

createServer((req, res) => {
  const url = new URL(req.url ?? "/", "http://x");
  if (base && !url.pathname.startsWith(base)) return send(res, 404, join(root, "404.html"));
  const rel = decodeURIComponent(url.pathname.slice(base.length)) || "/";
  const path = normalize(join(root, rel));
  if (!path.startsWith(root)) return send(res, 404, join(root, "404.html"));
  if (existsSync(path) && statSync(path).isDirectory()) {
    if (!url.pathname.endsWith("/")) {
      res.writeHead(301, { Location: `${url.pathname}/${url.search}` });
      return res.end();
    }
    if (existsSync(join(path, "index.html"))) return send(res, 200, join(path, "index.html"));
  } else if (existsSync(path)) return send(res, 200, path);
  else if (existsSync(`${path}.html`)) return send(res, 200, `${path}.html`);
  send(res, 404, join(root, "404.html"));
}).listen(port, () => console.log(`Static preview on http://localhost:${port}${base}/`));
