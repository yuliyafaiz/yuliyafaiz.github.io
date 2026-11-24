import { useCallback, useEffect, useRef, useState } from "react";

export interface AsyncState<T> {
  data: T | undefined;
  error: Error | undefined;
  loading: boolean;
  reload: () => Promise<void>;
  setData: (d: T) => void;
}

/** Load data from an async function; re-runs when deps change. Optional polling interval (ms). */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[] = [], pollMs?: number | false): AsyncState<T> {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<Error>();
  const [loading, setLoading] = useState(true);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const alive = useRef(true);

  const reload = useCallback(async () => {
    try {
      const d = await fnRef.current();
      if (alive.current) {
        setData(d);
        setError(undefined);
      }
    } catch (e) {
      if (alive.current) setError(e as Error);
    } finally {
      if (alive.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    alive.current = true;
    setLoading(true);
    void reload();
    return () => {
      alive.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    if (!pollMs) return;
    const t = setInterval(() => void reload(), pollMs);
    return () => clearInterval(t);
  }, [pollMs, reload]);

  return { data, error, loading, reload, setData };
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
}

const SPECIAL: Record<string, string> = {
  ipadapter: "IPAdapter", faceid: "FaceID", controlnet: "ControlNet", openpose: "OpenPose", img2img: "Img2img",
  inpaint: "Inpainting", style_model: "Style model", reference_profile: "Profile loader",
};
export const label = (s: string) => SPECIAL[s] ?? s.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

export function bytes(n?: number): string {
  if (!n) return "—";
  const gb = n / 1024 ** 3;
  return gb >= 1 ? `${gb.toFixed(1)} GB` : `${(n / 1024 ** 2).toFixed(0)} MB`;
}
