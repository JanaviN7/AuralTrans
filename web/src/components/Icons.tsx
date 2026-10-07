import type { ReactNode } from "react";

function Svg({ children, size = 18 }: { children: ReactNode; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

export const PlayIcon = () => (
  <Svg>
    <path d="M7 4.5v15l12-7.5z" fill="currentColor" stroke="none" />
  </Svg>
);
export const PauseIcon = () => (
  <Svg>
    <path d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z" fill="currentColor" stroke="none" />
  </Svg>
);
export const BackIcon = () => (
  <Svg>
    <path d="M3 12a9 9 0 1 0 3-6.7M3 4v5h5" />
  </Svg>
);
export const ForwardIcon = () => (
  <Svg>
    <path d="M21 12a9 9 0 1 1-3-6.7M21 4v5h-5" />
  </Svg>
);
export const DownloadIcon = () => (
  <Svg>
    <path d="M12 3v12m0 0-4-4m4 4 4-4M4 20h16" />
  </Svg>
);
export const TrashIcon = () => (
  <Svg>
    <path d="M4 7h16M10 11v6m4-6v6M6 7l1 13h10l1-13M9 7V4h6v3" />
  </Svg>
);
export const UploadIcon = ({ size = 28 }: { size?: number }) => (
  <Svg size={size}>
    <path d="M12 16V4m0 0L8 8m4-4 4 4M4 20h16" />
  </Svg>
);
export const SearchIcon = () => (
  <Svg>
    <circle cx="11" cy="11" r="7" />
    <path d="m20 20-3.5-3.5" />
  </Svg>
);
export const PencilIcon = () => (
  <Svg size={15}>
    <path d="M4 20h4L19 9l-4-4L4 16zM13.5 6.5l4 4" />
  </Svg>
);
export const CheckIcon = ({ size = 16 }: { size?: number }) => (
  <Svg size={size}>
    <path d="m5 12.5 4.5 4.5L19 7" />
  </Svg>
);
export const XIcon = ({ size = 16 }: { size?: number }) => (
  <Svg size={size}>
    <path d="M6 6l12 12M18 6 6 18" />
  </Svg>
);
export const ArrowLeftIcon = () => (
  <Svg>
    <path d="M19 12H5m0 0 6-6m-6 6 6 6" />
  </Svg>
);
export const ChevronIcon = ({ up }: { up?: boolean }) => (
  <Svg size={16}>
    <path d={up ? "m6 15 6-6 6 6" : "m6 9 6 6 6-6"} />
  </Svg>
);
export const SparkIcon = () => (
  <Svg size={26}>
    <path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8zM19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8z" />
  </Svg>
);
export const ChatIcon = () => (
  <Svg size={26}>
    <path d="M4 5h16v11H9l-5 4z" />
  </Svg>
);
export const AlertIcon = () => (
  <Svg size={18}>
    <path d="M12 3 2 20h20zM12 10v4m0 3h.01" />
  </Svg>
);
export const Logo = () => (
  <svg width="26" height="26" viewBox="0 0 32 32" aria-hidden="true">
    <rect width="32" height="32" rx="8" fill="var(--accent)" />
    <path d="M7 16h2m3-5v10m4-13v16m4-11v6m3-3h2" stroke="white" strokeWidth="2.4" strokeLinecap="round" fill="none" />
  </svg>
);
