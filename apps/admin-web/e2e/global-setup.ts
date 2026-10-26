import { spawn, type ChildProcess } from "node:child_process";
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";

async function waitFor(url: string, init?: RequestInit) {
  for (let attempt = 0; attempt < 120; attempt += 1) {
    try {
      if ((await fetch(url, init)).ok) return;
    } catch {
      // The process is still starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`E2E service did not start: ${url}`);
}

function stop(child: ChildProcess) {
  if (!child.killed) child.kill();
}

export default async function globalSetup() {
  const root = process.cwd();
  const nextEnvPath = path.join(root, "next-env.d.ts");
  const originalNextEnv = await readFile(nextEnvPath, "utf8");
  const backend = spawn(
    process.execPath,
    [path.join(root, "e2e/fake-backend.mjs")],
    {
      cwd: root,
      stdio: "ignore",
    },
  );
  const web = spawn(
    process.execPath,
    [
      path.join(root, "node_modules/next/dist/bin/next"),
      "dev",
      "--hostname",
      "127.0.0.1",
      "--port",
      "3100",
    ],
    {
      cwd: root,
      env: {
        ...process.env,
        BACKEND_API_URL: "http://127.0.0.1:4010/api/v1",
        NEXT_DIST_DIR: ".next-e2e",
      },
      stdio: "ignore",
    },
  );
  try {
    await Promise.all([
      waitFor("http://127.0.0.1:4010/api/v1/health/"),
      waitFor("http://127.0.0.1:3100/login"),
      waitFor("http://127.0.0.1:3100/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: "employee@example.test",
          password: "e2e-startup-probe",
        }),
      }),
    ]);
  } catch (error) {
    stop(web);
    stop(backend);
    await writeFile(nextEnvPath, originalNextEnv);
    throw error;
  }
  return async () => {
    stop(web);
    stop(backend);
    await writeFile(nextEnvPath, originalNextEnv);
  };
}
