// WEGEK render-review service.
// Loads a generated site in headless Chrome, waits for the WEGEK engine to
// signal readiness, then returns a screenshot for the Stage 7 quality loop.
import express from "express";
import puppeteer from "puppeteer";
import { promises as fs } from "node:fs";
import path from "node:path";

const PORT = process.env.PORT || 8200;
const BACKEND_ORIGIN = process.env.BACKEND_ORIGIN || "http://localhost:8000";
const OUT_DIR = process.env.OUT_DIR || path.join(process.cwd(), "_shots");

const app = express();
app.use(express.json());

let browser;
async function getBrowser() {
  if (!browser || !browser.connected) {
    browser = await puppeteer.launch({
      headless: "new",
      args: ["--no-sandbox", "--disable-setuid-sandbox", "--use-gl=swiftshader", "--enable-webgl"],
    });
  }
  return browser;
}

app.get("/health", (_req, res) => res.json({ status: "ok" }));

app.post("/capture", async (req, res) => {
  const { url, width = 1440, height = 900 } = req.body || {};
  if (!url) return res.status(400).json({ error: "url required" });

  const target = url.startsWith("http") ? url : `${BACKEND_ORIGIN}${url}`;
  try {
    const b = await getBrowser();
    const page = await b.newPage();
    await page.setViewport({ width, height, deviceScaleFactor: 1 });
    await page.goto(target, { waitUntil: "networkidle2", timeout: 60000 });
    // wait for the engine to flag readiness, then let the first frames settle
    await page
      .waitForFunction("document.documentElement.getAttribute('data-wegek-ready') === 'true'", { timeout: 20000 })
      .catch(() => {});
    await new Promise((r) => setTimeout(r, 1500));

    await fs.mkdir(OUT_DIR, { recursive: true });
    const file = path.join(OUT_DIR, `${Date.now()}.png`);
    await page.screenshot({ path: file, type: "png" });
    await page.close();

    res.json({ ok: true, image_path: file, image_url: `/shots/${path.basename(file)}` });
  } catch (err) {
    res.status(500).json({ error: String(err) });
  }
});

app.use("/shots", express.static(OUT_DIR));

app.listen(PORT, () => console.log(`WEGEK renderer on :${PORT} (backend=${BACKEND_ORIGIN})`));
