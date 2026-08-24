/**
 * True on self-hosted deployments (baked into the selfhost Docker image).
 * Gates billing UI, vendor-infra monitors, and upgrade CTAs.
 */
export const IS_SELF_HOSTED = process.env.NEXT_PUBLIC_SELF_HOSTED === "true";
