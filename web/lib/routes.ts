/**
 * Static hosting (GitHub Pages) support.
 *
 * The normal build runs on a Node server. `STATIC_EXPORT=1 next build` produces plain files instead; pages whose
 * URL contains an id (/clipper/<id>, /story/<id>, /admin/users/<id>, /s/<token>) are then built once with the
 * placeholder id "_" and read the real id from `?id=`. `href()` rewrites links to that form, and the 404 page
 * forwards old-style links (e.g. from notifications or shared URLs) the same way.
 */
export const STATIC = process.env.NEXT_PUBLIC_STATIC === "1";
export const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
export const PLACEHOLDER = "_";

const ID_ROUTE = /^\/(clipper|story|admin\/users|s)\/([^/?#]+)\/?(\?[^#]*)?(#.*)?$/;
const STATIC_CHILDREN = new Set(["new", PLACEHOLDER]);

/** The link to use for an in-app path (unchanged on the server build). */
export function href(path: string): string {
  if (!STATIC) return path;
  const m = ID_ROUTE.exec(path);
  if (!m || STATIC_CHILDREN.has(m[2])) return path;
  const [, section, id, query = "", hash = ""] = m;
  const extra = query ? `&${query.slice(1)}` : "";
  return `/${section}/${PLACEHOLDER}/?id=${encodeURIComponent(decodeURIComponent(id))}${extra}${hash}`;
}

/** Full URL of a page on this site (for share links, email redirects, copying). */
export function siteUrl(path: string): string {
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  return `${origin}${BASE_PATH}${href(path)}`;
}

/** Hard navigation to an in-app path (keeps the base path on static hosting). */
export function go(path: string): void {
  let target = href(path);
  if (STATIC) target = target.replace(/^([^?#]*?)\/?([?#].*)?$/, (_, p: string, rest = "") => `${p}/${rest}`); // trailingSlash
  window.location.href = `${BASE_PATH}${target}`;
}

/** For a path that reached the 404 page: where it should go instead (or null if it's really missing). */
export function staticFallback(pathname: string, search: string, hash: string): string | null {
  const path = pathname.startsWith(BASE_PATH) ? pathname.slice(BASE_PATH.length) || "/" : pathname;
  const target = href(`${path.replace(/\/$/, "")}${search}${hash}`);
  return target !== `${path.replace(/\/$/, "")}${search}${hash}` ? `${BASE_PATH}${target}` : null;
}
