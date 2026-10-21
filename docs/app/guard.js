// The network lock: while a text is being processed, nothing leaves the page.
//
// The page and the worker each install it in their own scope. Every way a script can open
// a connection is wrapped, and while the lock is held each of them throws instead. The
// statistics queue waits for the lock to be released, so an event can never be sent while
// a text is in memory being worked on. The Content-Security-Policy is the second wall: even
// an unlocked request can only reach the site itself, Hugging Face and the counter.

export class NetworkLockedError extends Error {
  constructor(what) {
    super(`${what} refused: a text is being processed and the network is locked`);
    this.name = "NetworkLockedError";
  }
}

let depth = 0;
const listeners = new Set();

export const isLocked = () => depth > 0;

export function lock() {
  depth++;
}

export function unlock() {
  depth = Math.max(0, depth - 1);
  if (depth === 0) for (const fn of listeners) fn();
}

// Run fn with the lock held, and release it however fn ends.
export async function whileLocked(fn) {
  lock();
  try {
    return await fn();
  } finally {
    unlock();
  }
}

export function onUnlock(fn) {
  listeners.add(fn);
}

export function install(scope = globalThis) {
  if (scope.__reflipGuard) return;
  Object.defineProperty(scope, "__reflipGuard", { value: true });

  const realFetch = scope.fetch?.bind(scope);
  if (realFetch) {
    scope.fetch = (...args) =>
      depth > 0 ? Promise.reject(new NetworkLockedError("fetch")) : realFetch(...args);
  }

  const XHR = scope.XMLHttpRequest;
  if (XHR) {
    const send = XHR.prototype.send;
    XHR.prototype.send = function (...args) {
      if (depth > 0) throw new NetworkLockedError("XMLHttpRequest");
      return send.apply(this, args);
    };
  }

  const nav = scope.navigator;
  if (nav && typeof nav.sendBeacon === "function") {
    const beacon = nav.sendBeacon.bind(nav);
    nav.sendBeacon = (...args) => {
      if (depth > 0) throw new NetworkLockedError("sendBeacon");
      return beacon(...args);
    };
  }

  for (const name of ["WebSocket", "EventSource"]) {
    const Real = scope[name];
    if (!Real) continue;
    scope[name] = new Proxy(Real, {
      construct(target, args) {
        if (depth > 0) throw new NetworkLockedError(name);
        return new target(...args);
      },
    });
  }

  // Images and other elements that load a URL: only in a page, not in a worker.
  const Img = scope.HTMLImageElement;
  if (Img) {
    const desc = Object.getOwnPropertyDescriptor(Img.prototype, "src");
    Object.defineProperty(Img.prototype, "src", {
      ...desc,
      set(v) {
        if (depth > 0) throw new NetworkLockedError("image");
        desc.set.call(this, v);
      },
    });
  }
}
