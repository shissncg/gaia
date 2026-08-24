import { execa } from "execa";
import { getContainerStatuses } from "../../lib/docker.js";
import { readDockerComposePortOverrides } from "../../lib/env-writer.js";
import {
  checkDockerDetailed,
  PREREQUISITE_URLS,
} from "../../lib/prerequisites.js";
import {
  buildSelfhostImages,
  detectSetupMode,
  findRepoRoot,
  pullSelfhostImages,
  runSelfhostMigrations,
  startServices,
} from "../../lib/service-starter.js";
import { LOG_BUFFER_LINES } from "../../ui/constants.js";
import type { CLIStore } from "../../ui/store.js";

const ANSI_ESCAPE_RE = new RegExp(`${String.fromCharCode(27)}\\[[0-9;]*m`, "g");

/** Markers apps/api/scripts/run_migrations.py prints for each registry entry. */
const APPLIED_MARKER = "[applied]";
const SKIP_MARKER = "[skip]";

export async function runUpdateFlow(store: CLIStore): Promise<void> {
  store.setStep("Updating");
  store.setStatus("Locating GAIA repository...");

  const repoPath = findRepoRoot();
  if (!repoPath) {
    store.setError(
      new Error(
        "Could not find GAIA repository. Run from within a cloned gaia repo.",
      ),
    );
    return;
  }
  store.updateData("repoPath", repoPath);

  const mode = await detectSetupMode(repoPath);
  if (!mode) {
    store.setError(
      new Error(
        "No .env file found. Run 'gaia init' for fresh setup, or 'gaia setup' to configure an existing repo.",
      ),
    );
    return;
  }
  if (mode !== "selfhost") {
    store.setError(
      new Error(
        "'gaia update' supports self-hosted Docker deployments only. In developer mode, `git pull` and restart your `mise dev` services manually.",
      ),
    );
    return;
  }
  store.updateData("setupMode", mode);

  store.setStatus("Checking Docker...");
  const dockerInfo = await checkDockerDetailed();
  if (!dockerInfo.working) {
    store.setError(
      new Error(
        dockerInfo.errorMessage ||
          `Docker is not running. Please start Docker and try again.\n  ${PREREQUISITE_URLS.docker}`,
      ),
    );
    return;
  }

  const portOverrides = readDockerComposePortOverrides(repoPath);
  store.updateData("dockerLogs", []);

  const logHandler = (chunk: string) => {
    const lines = chunk
      .split("\n")
      .map((l) => l.replace(ANSI_ESCAPE_RE, "").trim())
      .filter((l) => l.length > 0);
    if (lines.length === 0) return;
    const current: string[] = store.currentState.data.dockerLogs || [];
    store.updateData(
      "dockerLogs",
      [...current, ...lines].slice(-LOG_BUFFER_LINES),
    );
  };

  try {
    store.setStatus("Checking for local changes (git pull --ff-only)...");
    const oldSha = (
      await execa("git", ["rev-parse", "--short", "HEAD"], { cwd: repoPath })
    ).stdout.trim();

    try {
      await execa("git", ["pull", "--ff-only"], { cwd: repoPath });
    } catch (e) {
      throw new Error(
        `git pull --ff-only failed — refusing to merge or rebase on your behalf. ` +
          `Resolve manually (check \`git status\`/\`git log\`) and re-run 'gaia update'.\n\n${(e as Error).message}`,
      );
    }

    const newSha = (
      await execa("git", ["rev-parse", "--short", "HEAD"], { cwd: repoPath })
    ).stdout.trim();
    store.updateData("oldSha", oldSha);
    store.updateData("newSha", newSha);

    store.setStatus("Pulling latest Docker images...");
    await pullSelfhostImages(repoPath, logHandler);

    store.setStatus("Building updated services...");
    await buildSelfhostImages(repoPath, logHandler);

    store.setStatus("Running database migrations...");
    let migrationOutput = "";
    await runSelfhostMigrations(repoPath, (chunk) => {
      migrationOutput += chunk;
      logHandler(chunk);
    });
    const migrationsApplied = countOccurrences(migrationOutput, APPLIED_MARKER);
    const migrationsSkipped = countOccurrences(migrationOutput, SKIP_MARKER);
    store.updateData("migrationsApplied", migrationsApplied);
    store.updateData("migrationsSkipped", migrationsSkipped);

    store.setStatus("Restarting all services...");
    await startServices(
      repoPath,
      mode,
      (status) => store.setStatus(status),
      portOverrides,
      logHandler,
    );

    const statuses = await getContainerStatuses();
    const runningCount = statuses.filter((s) => s.status === "running").length;
    store.updateData("containerStatuses", statuses);
    store.updateData("runningCount", runningCount);

    store.setStep("Updated");
    store.setStatus(
      oldSha === newSha
        ? `Already up to date at ${newSha}.`
        : `Updated ${oldSha} -> ${newSha}.`,
    );
    store.updateData("updated", true);
  } catch (e) {
    store.setError(new Error(`Update failed: ${(e as Error).message}`));
    return;
  }

  await store.waitForInput("exit");
}

function countOccurrences(haystack: string, needle: string): number {
  return haystack.split(needle).length - 1;
}
