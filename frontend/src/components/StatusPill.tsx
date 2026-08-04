import { ReactNode } from "react";

export default function StatusPill({tone="neutral", children}:{tone?:"good"|"warn"|"danger"|"neutral";children:ReactNode}) {
  return <span className={`status-pill ${tone}`}><span className="status-dot" />{children}</span>;
}
