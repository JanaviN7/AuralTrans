import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useSyncExternalStore,
  type ReactNode,
} from "react";

export interface PlayerState {
  time: number;
  duration: number;
  playing: boolean;
  rate: number;
  error: string | null;
}

/** Tiny external store so the playhead and the highlighted word update without re-rendering the page. */
class PlayerStore {
  state: PlayerState = { time: 0, duration: 0, playing: false, rate: 1, error: null };
  private listeners = new Set<() => void>();
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };
  get = () => this.state;
  set(patch: Partial<PlayerState>) {
    this.state = { ...this.state, ...patch };
    this.listeners.forEach((l) => l());
  }
}

interface PlayerApi {
  store: PlayerStore;
  seek: (seconds: number, play?: boolean) => void;
  toggle: () => void;
  skip: (delta: number) => void;
  setRate: (rate: number) => void;
}

const PlayerContext = createContext<PlayerApi | null>(null);

function isTyping(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  return !!el && (["INPUT", "TEXTAREA", "SELECT", "BUTTON"].includes(el.tagName) || el.isContentEditable);
}

export function PlayerProvider({
  src,
  fallbackDuration,
  children,
}: {
  src: string;
  fallbackDuration: number | null;
  children: ReactNode;
}) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const store = useMemo(() => new PlayerStore(), [src]); // eslint-disable-line react-hooks/exhaustive-deps

  const seek = useCallback(
    (seconds: number, play = false) => {
      const audio = audioRef.current;
      if (!audio) return;
      const limit = Number.isFinite(audio.duration) ? audio.duration : (fallbackDuration ?? Infinity);
      audio.currentTime = Math.min(Math.max(0, seconds), limit);
      store.set({ time: audio.currentTime });
      if (play) void audio.play().catch(() => undefined);
    },
    [store, fallbackDuration],
  );

  const toggle = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;
    if (audio.paused) void audio.play().catch(() => undefined);
    else audio.pause();
  }, []);

  const skip = useCallback((delta: number) => seek((audioRef.current?.currentTime ?? 0) + delta), [seek]);

  const setRate = useCallback((rate: number) => {
    if (audioRef.current) audioRef.current.playbackRate = rate;
  }, []);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    let frame = 0;
    const tick = () => {
      store.set({ time: audio.currentTime });
      frame = requestAnimationFrame(tick);
    };
    const duration = () => {
      const d = Number.isFinite(audio.duration) ? audio.duration : (fallbackDuration ?? 0);
      store.set({ duration: d });
    };
    const on = {
      loadedmetadata: duration,
      durationchange: duration,
      play: () => {
        store.set({ playing: true });
        cancelAnimationFrame(frame);
        frame = requestAnimationFrame(tick);
      },
      pause: () => {
        cancelAnimationFrame(frame);
        store.set({ playing: false, time: audio.currentTime });
      },
      ended: () => {
        cancelAnimationFrame(frame);
        store.set({ playing: false, time: audio.currentTime });
      },
      timeupdate: () => store.set({ time: audio.currentTime }),
      ratechange: () => store.set({ rate: audio.playbackRate }),
      error: () => store.set({ error: "The audio could not be loaded." }),
    };
    for (const [name, fn] of Object.entries(on)) audio.addEventListener(name, fn);
    duration();
    return () => {
      cancelAnimationFrame(frame);
      for (const [name, fn] of Object.entries(on)) audio.removeEventListener(name, fn);
    };
  }, [store, fallbackDuration]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (isTyping(e.target) || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.code === "Space") {
        e.preventDefault();
        toggle();
      } else if (e.code === "ArrowLeft") skip(-5);
      else if (e.code === "ArrowRight") skip(5);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggle, skip]);

  const api = useMemo(() => ({ store, seek, toggle, skip, setRate }), [store, seek, toggle, skip, setRate]);
  return (
    <PlayerContext.Provider value={api}>
      <audio ref={audioRef} src={src} preload="auto" />
      {children}
    </PlayerContext.Provider>
  );
}

export function usePlayer(): PlayerApi {
  const ctx = useContext(PlayerContext);
  if (!ctx) throw new Error("usePlayer must be used inside <PlayerProvider>");
  return ctx;
}

/** Subscribe to one derived value. The selector must return a primitive so unchanged values skip renders. */
export function usePlayerValue<T extends string | number | boolean | null>(selector: (s: PlayerState) => T): T {
  const { store } = usePlayer();
  return useSyncExternalStore(store.subscribe, () => selector(store.get()));
}
