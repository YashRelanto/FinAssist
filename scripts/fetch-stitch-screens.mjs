import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { stitch } from "@google/stitch-sdk";

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = join(__dirname, "..");
const mcpPath = join(process.env.USERPROFILE || "", ".cursor", "mcp.json");
const mcp = JSON.parse(readFileSync(mcpPath, "utf8"));
process.env.STITCH_API_KEY = mcp.mcpServers.stitch.headers["X-Goog-Api-Key"];

const projectId = "17573764507538130363";
const screens = [
  { id: "cde7ddc4f1c7411784867ffde2651c1c", slug: "landing-page" },
  { id: "6191c8dbb9174f36aa51fbfb04c1dbfa", slug: "dashboard" },
];

const outDir = join(root, "stitch-assets", projectId);
mkdirSync(outDir, { recursive: true });

async function download(url, dest) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Download failed ${res.status}: ${url}`);
  const buf = Buffer.from(await res.arrayBuffer());
  writeFileSync(dest, buf);
}

for (const screen of screens) {
  const result = await stitch.callTool("get_screen", {
    name: `projects/${projectId}/screens/${screen.id}`,
    projectId,
    screenId: screen.id,
  });

  const data = result?.result ?? result;
  writeFileSync(
    join(outDir, `${screen.slug}-metadata.json`),
    JSON.stringify(data, null, 2),
  );

  const htmlUrl = data?.htmlCode?.downloadUrl;
  const imageUrl = data?.screenshot?.downloadUrl;

  if (htmlUrl) {
    await download(htmlUrl, join(outDir, `${screen.slug}.html`));
    console.log(`Saved ${screen.slug}.html`);
  } else {
    console.warn(`No HTML URL for ${screen.slug}`);
  }

  if (imageUrl) {
    await download(imageUrl, join(outDir, `${screen.slug}.png`));
    console.log(`Saved ${screen.slug}.png`);
  } else {
    console.warn(`No screenshot URL for ${screen.slug}`);
  }
}

await stitch.close();
console.log(`Assets written to ${outDir}`);
