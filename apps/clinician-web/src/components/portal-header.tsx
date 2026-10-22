import type { ReactNode } from "react";

interface PortalHeaderProps {
  eyebrow: string;
  title: string;
  description: string;
  action?: ReactNode;
}

export function PortalHeader({
  eyebrow,
  title,
  description,
  action,
}: PortalHeaderProps) {
  return (
    <header className="portal-header">
      <div>
        <p className="page-eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action ? <div className="header-action">{action}</div> : null}
    </header>
  );
}
