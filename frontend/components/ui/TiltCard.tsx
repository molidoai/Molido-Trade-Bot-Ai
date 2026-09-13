"use client";

/**
 * A panel.
 *
 * This used to tilt in 3D under the cursor: a mousemove handler on every card,
 * writing rotateX/rotateY transforms, over a page with `perspective: 1400px`
 * on the body. Fifteen pages use it, so a dashboard with a dozen cards ran a
 * dozen handlers competing for the main thread during exactly the interaction
 * where scrolling needs to stay smooth. It also moved the thing you were
 * trying to read.
 *
 * The name and props are kept so no page has to change.
 */

import type { ReactNode } from "react";

export function TiltCard({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
  /** Accepted and ignored — kept so existing callers still type-check. */
  intensity?: number;
}) {
  return <div className={`panel p-4 sm:p-5 ${className}`}>{children}</div>;
}

export default TiltCard;
