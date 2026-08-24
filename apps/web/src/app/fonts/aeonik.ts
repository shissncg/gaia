import localFont from "next/font/local";

export const aeonik = localFont({
  src: [
    {
      // No trial-licensed weight-600 cut ships in this fork (see
      // AeonikExtendedProTRIAL-SemiBold.woff2's removal) — the licensed Bold
      // face covers both the 600 and 700 weight declarations below.
      path: "./aeonik/AeonikExtendedPro-Bold.woff2",
      weight: "600",
      style: "normal",
    },
    {
      path: "./aeonik/AeonikExtendedPro-Bold.woff2",
      weight: "700",
      style: "normal",
    },
  ],
  variable: "--font-aeonik",
  display: "swap",
  // Display font for marketing headings (mapped to --font-serif) — on the LCP path.
  preload: true,
  fallback: ["system-ui", "sans-serif"],
});
