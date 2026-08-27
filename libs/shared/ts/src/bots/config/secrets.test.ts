/**
 * Tests for the bots' Infisical loader — the TypeScript twin of
 * libs/shared/py/tests/test_secrets.py. Same env var names, same raise
 * semantics; the two loaders are a documented mirrored contract
 * (libs/shared/CLAUDE.md) and must be kept in lockstep.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@infisical/sdk", () => {
  const login = vi.fn().mockResolvedValue(undefined);
  const listSecrets = vi.fn().mockResolvedValue({ secrets: [] });
  // biome-ignore lint/complexity/useArrowFunction: vitest invokes mockImplementation as a constructor (new InfisicalSDK()), which requires function() not =>
  const InfisicalSDK = vi.fn().mockImplementation(function () {
    return {
      auth: () => ({ universalAuth: { login } }),
      secrets: () => ({ listSecrets }),
    };
  });
  return { InfisicalSDK, __mockLogin: login, __mockListSecrets: listSecrets };
});

import * as infisicalSdkModule from "@infisical/sdk";
import { InfisicalSDK } from "@infisical/sdk";
import { injectInfisicalSecrets } from "./secrets";

interface MockedInfisicalSdkModule {
  __mockLogin: ReturnType<typeof vi.fn>;
  __mockListSecrets: ReturnType<typeof vi.fn>;
}

const { __mockLogin: mockLogin, __mockListSecrets: mockListSecrets } =
  infisicalSdkModule as unknown as MockedInfisicalSdkModule;
const MockedInfisicalSDK = vi.mocked(InfisicalSDK);

const INFISICAL_ENV_KEYS = [
  "ENV",
  "NODE_ENV",
  "INFISICAL_HOST",
  "INFISICAL_ENV",
  "INFISICAL_PROJECT_ID",
  "INFISICAL_MACHINE_IDENTITY_CLIENT_ID",
  "INFISICAL_MACHINE_IDENTITY_CLIENT_SECRET",
] as const;

const FULL_MACHINE_IDENTITY = {
  INFISICAL_PROJECT_ID: "proj-abc",
  INFISICAL_MACHINE_IDENTITY_CLIENT_ID: "cid-xyz",
  INFISICAL_MACHINE_IDENTITY_CLIENT_SECRET: "csec-xyz",
};

let envSnapshot: NodeJS.ProcessEnv;

beforeEach(() => {
  envSnapshot = { ...process.env };
  for (const key of INFISICAL_ENV_KEYS) {
    delete process.env[key];
  }
  vi.clearAllMocks();
});

afterEach(() => {
  process.env = envSnapshot;
});

describe("injectInfisicalSecrets — host and environment slug", () => {
  it("defaults to the public Infisical Cloud host when INFISICAL_HOST is unset", async () => {
    process.env.ENV = "development";
    Object.assign(process.env, FULL_MACHINE_IDENTITY);

    await injectInfisicalSecrets();

    expect(MockedInfisicalSDK).toHaveBeenCalledWith({
      siteUrl: "https://app.infisical.com",
    });
    expect(mockLogin).toHaveBeenCalledWith({
      clientId: FULL_MACHINE_IDENTITY.INFISICAL_MACHINE_IDENTITY_CLIENT_ID,
      clientSecret:
        FULL_MACHINE_IDENTITY.INFISICAL_MACHINE_IDENTITY_CLIENT_SECRET,
    });
    // ENV with no INFISICAL_ENV override also covers the slug-defaults-to-ENV case.
    expect(mockListSecrets).toHaveBeenCalledWith(
      expect.objectContaining({ environment: "development" }),
    );
  });

  it("honors INFISICAL_HOST when set", async () => {
    process.env.ENV = "development";
    Object.assign(process.env, FULL_MACHINE_IDENTITY);
    process.env.INFISICAL_HOST = "https://infisical.internal.example.com";

    await injectInfisicalSecrets();

    expect(MockedInfisicalSDK).toHaveBeenCalledWith({
      siteUrl: "https://infisical.internal.example.com",
    });
  });

  it("uses INFISICAL_ENV as the secrets environment slug when set", async () => {
    process.env.ENV = "production";
    Object.assign(process.env, FULL_MACHINE_IDENTITY);
    process.env.INFISICAL_ENV = "selfhost";

    await injectInfisicalSecrets();

    expect(mockListSecrets).toHaveBeenCalledWith(
      expect.objectContaining({ environment: "selfhost" }),
    );
  });
});

describe("injectInfisicalSecrets — raise semantics", () => {
  it("skips without throwing when zero Infisical vars are set, even in production", async () => {
    process.env.ENV = "production";

    await expect(injectInfisicalSecrets()).resolves.toBeUndefined();
    expect(MockedInfisicalSDK).not.toHaveBeenCalled();
  });

  it("still throws when config is partially set in production", async () => {
    process.env.ENV = "production";
    process.env.INFISICAL_PROJECT_ID =
      FULL_MACHINE_IDENTITY.INFISICAL_PROJECT_ID;
    // MACHINE_IDENTITY_CLIENT_ID / CLIENT_SECRET intentionally left unset.

    await expect(injectInfisicalSecrets()).rejects.toThrow(
      /Incomplete Infisical config/,
    );
    expect(MockedInfisicalSDK).not.toHaveBeenCalled();
  });
});
