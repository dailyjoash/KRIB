const loadedScripts = new Map();

export function loadExternalScript(src) {
  if (!src) return Promise.reject(new Error("Missing script URL"));
  if (loadedScripts.has(src)) {
    return loadedScripts.get(src);
  }

  const existing = document.querySelector(`script[src="${src}"]`);
  if (existing) {
    const promise = Promise.resolve(existing);
    loadedScripts.set(src, promise);
    return promise;
  }

  const promise = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = src;
    script.async = true;
    script.onload = () => resolve(script);
    script.onerror = () => reject(new Error(`Failed to load ${src}`));
    document.body.appendChild(script);
  });

  loadedScripts.set(src, promise);
  return promise;
}
