import { PortalLink } from "./portal-link";
import type { ReactNode } from "react";

import { PortalIcon } from "./portal-icon";
import { PortalNavigation, PortalPrivacyLink } from "./portal-navigation";

interface PortalShellProps {
  children: ReactNode;
}

export function PortalShell({ children }: PortalShellProps) {
  return (
    <div className="portal-shell">
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>
      <aside className="side-rail">
        <div>
          <PortalLink className="wordmark" href="/" aria-label="Cadence overview">
            <span className="wordmark-mark" aria-hidden="true">
              <PortalIcon name="wave" />
            </span>
            <span>
              Cadence
            </span>
          </PortalLink>

          <PortalNavigation />
        </div>

        <div className="rail-footer">
          <PortalPrivacyLink>Privacy and data controls</PortalPrivacyLink>
        </div>
      </aside>

      <div className="portal-main">
        <header className="mobile-bar">
          <PortalLink className="wordmark compact" href="/" aria-label="Cadence overview">
            <span className="wordmark-mark" aria-hidden="true">
              <PortalIcon name="wave" />
            </span>
            <span>Cadence</span>
          </PortalLink>
          <details className="mobile-menu">
            <summary>Menu</summary>
            <PortalNavigation mobile />
          </details>
        </header>
        <main className="page-frame" id="main-content" tabIndex={-1}>
          {children}
        </main>
      </div>
    </div>
  );
}
