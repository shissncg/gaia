/**
 * Handler for the 'update' command — pull, rebuild, migrate, restart.
 * @module commands/update/handler
 */

import { runCommandUI } from "../../lib/command-runner.js";
import { runUpdateFlow } from "./flow.js";

export async function runUpdate(): Promise<void> {
  await runCommandUI({
    command: "update",
    whenNonInteractive: "plain",
    autoResolve: [["exit"]],
    runFlow: (store) => runUpdateFlow(store),
  });
}
