/* Inline icon set — single stroke style, currentColor. Keeps the studio
   free of emoji so it reads like a real product surface. */
type P = { size?: number; className?: string };
const base = (size: number) => ({
  width: size, height: size, viewBox: "0 0 24 24", fill: "none",
  stroke: "currentColor", strokeWidth: 1.6, strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
});

export const Logo = ({ size = 18 }: P) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
    <path d="M3 7l9-4 9 4-9 4-9-4z" stroke="var(--brand)" strokeWidth="1.6" strokeLinejoin="round" />
    <path d="M3 12l9 4 9-4M3 17l9 4 9-4" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" opacity="0.55" />
  </svg>
);

export const Spark = ({ size = 16, className }: P) => (
  <svg {...base(size)} className={className}>
    <path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M18.4 5.6l-2.8 2.8M8.4 15.6l-2.8 2.8" />
  </svg>
);
export const Arrow = ({ size = 16, className }: P) => (
  <svg {...base(size)} className={className}><path d="M5 12h14M13 6l6 6-6 6" /></svg>
);
export const ArrowUpRight = ({ size = 14, className }: P) => (
  <svg {...base(size)} className={className}><path d="M7 17L17 7M8 7h9v9" /></svg>
);
export const Download = ({ size = 14, className }: P) => (
  <svg {...base(size)} className={className}><path d="M12 3v12M7 11l5 5 5-5M5 21h14" /></svg>
);
export const Cube = ({ size = 16, className }: P) => (
  <svg {...base(size)} className={className}>
    <path d="M12 2.8l8 4.6v9.2L12 21.2l-8-4.6V7.4l8-4.6zM4 7.4l8 4.6 8-4.6M12 12v9.2" />
  </svg>
);
export const Layers = ({ size = 16, className }: P) => (
  <svg {...base(size)} className={className}><path d="M12 3l9 5-9 5-9-5 9-5zM3 13l9 5 9-5" /></svg>
);
export const Bolt = ({ size = 16, className }: P) => (
  <svg {...base(size)} className={className}><path d="M13 2L5 14h6l-1 8 8-12h-6l1-8z" /></svg>
);
export const Lock = ({ size = 14, className }: P) => (
  <svg {...base(size)} className={className}><rect x="4.5" y="10.5" width="15" height="10" rx="2" /><path d="M8 10.5V7a4 4 0 0 1 8 0v3.5" /></svg>
);
export const Check = ({ size = 12, className }: P) => (
  <svg {...base(size)} className={className}><path d="M4 12l5 5L20 6" /></svg>
);
export const Cross = ({ size = 12, className }: P) => (
  <svg {...base(size)} className={className}><path d="M6 6l12 12M18 6L6 18" /></svg>
);
