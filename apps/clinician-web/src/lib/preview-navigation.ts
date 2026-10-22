// Preview routing is presentation-only. Its pages and proxy each enforce the
// development flag; clinical pages and actions retain their own authorization.
export const previewRoutes = {
  overview: "/",
  learners: "/learners",
  assignments: "/assignments",
  review: "/review",
  safety: "/safety",
  privacy: "/settings/privacy",
} as const;

export type PreviewView = keyof typeof previewRoutes;

export function isPreviewView(value: string): value is PreviewView {
  return Object.hasOwn(previewRoutes, value);
}

export function isPreviewPath(pathname: string): boolean {
  return pathname === "/accessibility-preview" || pathname.startsWith("/accessibility-preview/");
}

export function canonicalPortalPath(pathname: string): string {
  if (pathname === "/accessibility-preview") return "/";
  const view = pathname.slice("/accessibility-preview/".length);
  return isPreviewPath(pathname) && isPreviewView(view) ? previewRoutes[view] : pathname;
}

export function portalHref(href: string, pathname: string): string {
  if (!isPreviewPath(pathname)) return href;
  const match = Object.entries(previewRoutes).find(([, route]) =>
    href === route || href.startsWith(`${route}?`) || href.startsWith(`${route}#`));
  return match ? `/accessibility-preview/${match[0]}${href.slice(match[1].length)}` : href;
}
