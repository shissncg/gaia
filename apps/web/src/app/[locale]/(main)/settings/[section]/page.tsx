import { redirect } from "next/navigation";
import type { SettingsSection } from "@/features/settings/config/sectionKeys";
import {
  DEFAULT_SECTION,
  isValidSection,
} from "@/features/settings/config/sectionKeys";
import { IS_SELF_HOSTED } from "@/lib/deployment";
import SettingsSectionClient from "./SettingsSectionClient";

interface PageProps {
  params: Promise<{ readonly section: string }>;
}

export default async function SettingsSectionPage({ params }: PageProps) {
  const { section } = await params;

  if (!isValidSection(section)) {
    redirect(`/settings/${DEFAULT_SECTION}`);
  }

  // Self-hosted deployments have no subscription to manage — the menu entry
  // is already filtered out (settingsConfig.tsx), but a deep link must not
  // render a page for a feature that doesn't exist here.
  if (IS_SELF_HOSTED && section === "subscription") {
    redirect(`/settings/${DEFAULT_SECTION}`);
  }

  return <SettingsSectionClient section={section as SettingsSection} />;
}
