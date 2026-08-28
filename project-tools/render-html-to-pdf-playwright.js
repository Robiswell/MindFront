const fs = require("fs");
const os = require("os");
const path = require("path");
const crypto = require("crypto");
const { spawnSync } = require("child_process");
const { fileURLToPath, pathToFileURL } = require("url");
const { chromium } = require("playwright");

const MANIFEST_SCHEMA_VERSION = 2;
const MAX_SNAPSHOT_FILES = 2048;
const MAX_SNAPSHOT_BYTES = 256 * 1024 * 1024;

function sha256Buffer(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

function sha256File(filePath) {
  return sha256Buffer(fs.readFileSync(filePath));
}

function sha256UriForFile(filePath) {
  return `sha256:${sha256File(filePath)}`;
}

function sha256UriForText(value) {
  return `sha256:${sha256Buffer(Buffer.from(value, "utf8"))}`;
}

function stableStringify(value) {
  if (Array.isArray(value)) {
    return `[${value.map((item) => stableStringify(item)).join(",")}]`;
  }
  if (value && typeof value === "object") {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function isPathWithin(rootPath, candidatePath) {
  const relative = path.relative(rootPath, candidatePath);
  return relative === "" || (!relative.startsWith(`..${path.sep}`) && relative !== ".." && !path.isAbsolute(relative));
}

function decodeReference(value) {
  return value
    .replace(/&amp;/gi, "&")
    .replace(/&#x([0-9a-f]+);/gi, (_, hex) => String.fromCodePoint(Number.parseInt(hex, 16)))
    .replace(/&#([0-9]+);/g, (_, decimal) => String.fromCodePoint(Number.parseInt(decimal, 10)));
}

function extractAssetReferences(content, sourcePath) {
  const references = [];
  const extension = path.extname(sourcePath).toLowerCase();

  const cssUrlPattern = /url\(\s*(?:(["'])(.*?)\1|([^)"']+))\s*\)/gi;
  for (const match of content.matchAll(cssUrlPattern)) {
    references.push(match[2] || match[3] || "");
  }

  if (![".html", ".htm", ".svg", ".xml"].includes(extension)) {
    return references;
  }

  const tagPattern = /<([a-z][a-z0-9:-]*)\b[^>]*>/gi;
  const attributePattern = /\b(src|poster|data|href|xlink:href|srcset)\s*=\s*(["'])(.*?)\2/gi;
  for (const tagMatch of content.matchAll(tagPattern)) {
    const tagName = tagMatch[1].toLowerCase();
    const tagText = tagMatch[0];
    for (const attributeMatch of tagText.matchAll(attributePattern)) {
      const attributeName = attributeMatch[1].toLowerCase();
      const attributeValue = attributeMatch[3];
      const hrefIsAsset =
        attributeName !== "href" ||
        ["link", "image", "use", "feimage"].includes(tagName);
      if (!hrefIsAsset) {
        continue;
      }
      if (attributeName === "srcset") {
        for (const item of attributeValue.split(",")) {
          const candidate = item.trim().split(/\s+/, 1)[0];
          if (candidate) {
            references.push(candidate);
          }
        }
      } else {
        references.push(attributeValue);
      }
    }
  }
  return references;
}

function assertStaticLocalDocument(inputPath) {
  const html = fs.readFileSync(inputPath, "utf8");
  const blockedPatterns = [
    [/<base\b/i, "base elements"],
    [/<script\b/i, "script elements"],
    [/<(?:iframe|frame|object|embed)\b/i, "embedded documents"],
    [/\son[a-z]+\s*=/i, "inline event handlers"],
    [/@import\b/i, "CSS imports"],
    [/(?:src\s*=|url\()\s*["']?(?:https?:|file:|\/\/)/i, "external or absolute assets"],
    [/<link\b[^>]*\bhref\s*=\s*["'](?:https?:|file:|\/\/)/i, "external stylesheets"],
  ];
  for (const [pattern, label] of blockedPatterns) {
    if (pattern.test(html)) {
      throw new Error(`Verified PDF rendering does not allow ${label}.`);
    }
  }
}

function resolveLocalAsset(reference, referringPath, sourceRoot) {
  const value = decodeReference(reference.trim());
  if (!value || value.startsWith("#") || /^(?:data|mailto|tel):/i.test(value)) {
    return null;
  }
  if (/^(?:https?|file|javascript):/i.test(value) || value.startsWith("//")) {
    throw new Error(`Verified PDF rendering does not allow non-snapshot asset references: ${value}`);
  }
  if (/^[a-z]:[\\/]/i.test(value) || value.startsWith("\\\\")) {
    throw new Error(`Verified PDF rendering does not allow absolute local asset paths: ${value}`);
  }

  let candidatePath;
  try {
    const candidateUrl = new URL(value, pathToFileURL(referringPath));
    if (candidateUrl.protocol !== "file:") {
      throw new Error(`Unsupported asset protocol: ${candidateUrl.protocol}`);
    }
    candidatePath = path.resolve(fileURLToPath(candidateUrl));
  } catch (error) {
    throw new Error(`Could not resolve local asset reference "${value}": ${error.message}`);
  }

  if (!isPathWithin(sourceRoot, candidatePath)) {
    throw new Error(`Local asset resolves outside the render snapshot: ${value}`);
  }
  if (!fs.existsSync(candidatePath) || !fs.statSync(candidatePath).isFile()) {
    throw new Error(`Local render asset does not exist or is not a file: ${candidatePath}`);
  }

  const realCandidate = fs.realpathSync(candidatePath);
  if (!isPathWithin(sourceRoot, realCandidate)) {
    throw new Error(`Local asset resolves through a link outside the render snapshot: ${value}`);
  }
  return realCandidate;
}

function collectSnapshotDependencies(inputPath) {
  const canonicalInput = fs.realpathSync(inputPath);
  const sourceRoot = fs.realpathSync(path.dirname(canonicalInput));
  const pending = [canonicalInput];
  const discovered = new Map();
  let totalBytes = 0;

  while (pending.length > 0) {
    const currentPath = pending.shift();
    const relativePath = path.relative(sourceRoot, currentPath).split(path.sep).join("/");
    if (discovered.has(relativePath)) {
      continue;
    }
    if (!isPathWithin(sourceRoot, currentPath)) {
      throw new Error(`Render dependency escaped the source root: ${currentPath}`);
    }

    const stats = fs.statSync(currentPath);
    if (!stats.isFile()) {
      throw new Error(`Render dependency is not a regular file: ${currentPath}`);
    }
    totalBytes += stats.size;
    if (discovered.size + 1 > MAX_SNAPSHOT_FILES || totalBytes > MAX_SNAPSHOT_BYTES) {
      throw new Error("Render snapshot exceeds the configured file-count or byte limit.");
    }

    const entry = {
      relativePath,
      sourcePath: currentPath,
      bytes: stats.size,
      sha256: sha256UriForFile(currentPath),
    };
    discovered.set(relativePath, entry);

    if ([".html", ".htm", ".css", ".svg", ".xml"].includes(path.extname(currentPath).toLowerCase())) {
      const content = fs.readFileSync(currentPath, "utf8");
      for (const reference of extractAssetReferences(content, currentPath)) {
        const resolved = resolveLocalAsset(reference, currentPath, sourceRoot);
        if (resolved) {
          pending.push(resolved);
        }
      }
    }
  }

  return {
    sourceRoot,
    sourceHtmlRelativePath: path.relative(sourceRoot, canonicalInput).split(path.sep).join("/"),
    files: [...discovered.values()].sort((left, right) =>
      left.relativePath < right.relativePath
        ? -1
        : left.relativePath > right.relativePath
          ? 1
          : 0
    ),
    totalBytes,
  };
}

function createRenderSnapshot(inputPath) {
  assertStaticLocalDocument(inputPath);
  const dependencies = collectSnapshotDependencies(inputPath);
  const snapshotRoot = fs.mkdtempSync(path.join(os.tmpdir(), "mindfront-render-snapshot-"));

  try {
    for (const entry of dependencies.files) {
      const destination = path.join(snapshotRoot, ...entry.relativePath.split("/"));
      fs.mkdirSync(path.dirname(destination), { recursive: true });
      fs.copyFileSync(entry.sourcePath, destination, fs.constants.COPYFILE_EXCL);
      if (sha256UriForFile(destination) !== entry.sha256) {
        throw new Error(`Render snapshot copy hash mismatch: ${entry.relativePath}`);
      }
    }

    const digestInput = dependencies.files
      .map((entry) => `${entry.relativePath}\0${entry.bytes}\0${entry.sha256}\n`)
      .join("");
    return {
      snapshotRoot,
      snapshotHtmlPath: path.join(
        snapshotRoot,
        ...dependencies.sourceHtmlRelativePath.split("/")
      ),
      manifest: {
        sourceRootPath: dependencies.sourceRoot,
        sourceHtmlRelativePath: dependencies.sourceHtmlRelativePath,
        fileCount: dependencies.files.length,
        totalBytes: dependencies.totalBytes,
        files: dependencies.files.map(({ relativePath, bytes, sha256 }) => ({
          relativePath,
          bytes,
          sha256,
        })),
        snapshotSha256: sha256UriForText(digestInput),
      },
    };
  } catch (error) {
    fs.rmSync(snapshotRoot, { recursive: true, force: true });
    throw error;
  }
}

function resolvePython() {
  const candidates = [
    process.env.MINDFRONT_PYTHON,
    path.join(
      os.homedir(),
      ".cache",
      "codex-runtimes",
      "codex-primary-runtime",
      "dependencies",
      "python",
      "python.exe"
    ),
    "python3",
    "python",
  ].filter(Boolean);
  for (const candidate of candidates) {
    if (path.isAbsolute(candidate) && !fs.existsSync(candidate)) {
      continue;
    }
    const probe = spawnSync(candidate, ["-c", "import pypdf"], {
      encoding: "utf8",
      windowsHide: true,
    });
    if (!probe.error && probe.status === 0) {
      return path.resolve(candidate);
    }
  }
  throw new Error("Could not find a Python runtime with pypdf for PDF tag normalization.");
}

function normalizeListTags(rawPdfPath, outputPath) {
  const normalizerPath = path.resolve(__dirname, "normalize-pdf-list-tags.py");
  if (!fs.existsSync(normalizerPath)) {
    throw new Error(`PDF list-tag normalizer does not exist: ${normalizerPath}`);
  }
  const pythonPath = resolvePython();
  const argumentVector = [
    normalizerPath,
    "--input",
    rawPdfPath,
    "--output",
    outputPath,
  ];
  const completed = spawnSync(pythonPath, argumentVector, {
    encoding: "utf8",
    windowsHide: true,
    timeout: 120000,
  });
  if (completed.error || completed.status !== 0) {
    const failureDetail = completed.error
      ? completed.error.message
      : [completed.stderr.trim(), completed.stdout.trim()].filter(Boolean).join(" ");
    throw new Error(
      `PDF list-tag normalization failed: ${failureDetail || "normalizer returned no diagnostic output"}`
    );
  }

  let result = null;
  try {
    result = JSON.parse(completed.stdout);
  } catch {
    const outputLines = completed.stdout
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);
    for (const line of outputLines.reverse()) {
      try {
        result = JSON.parse(line);
        break;
      } catch {
        // Keep looking for a compact machine-readable result.
      }
    }
  }
  if (
    !result ||
    result.artifactType !== "pdf_list_tag_normalization_result" ||
    !["normalized", "unchanged"].includes(result.status)
  ) {
    throw new Error("PDF list-tag normalizer did not return an accepted JSON result.");
  }

  const rawSha256 = sha256File(rawPdfPath);
  if (result.inputSha256 !== rawSha256) {
    throw new Error("PDF list-tag normalizer input hash does not match the raw PDF.");
  }
  if (result.status === "unchanged") {
    fs.copyFileSync(rawPdfPath, outputPath);
  }
  if (!fs.existsSync(outputPath)) {
    throw new Error("PDF list-tag normalizer did not materialize the final PDF.");
  }

  const finalSha256 = sha256File(outputPath);
  if (result.status === "normalized" && result.outputSha256 !== finalSha256) {
    throw new Error("PDF list-tag normalizer output hash does not match the final PDF.");
  }
  if (result.status === "unchanged" && finalSha256 !== rawSha256) {
    throw new Error("Unchanged PDF materialization does not match the raw PDF.");
  }

  const resultSha256 = sha256UriForText(stableStringify(result));
  return {
    pythonExecutablePath: pythonPath,
    pythonExecutableSha256: sha256UriForFile(pythonPath),
    scriptPath: normalizerPath,
    scriptSha256: sha256UriForFile(normalizerPath),
    invocation: {
      executablePath: pythonPath,
      argumentVector,
      inputPdfPath: rawPdfPath,
      inputPdfSha256: `sha256:${rawSha256}`,
      outputPdfPath: outputPath,
      outputPdfSha256: `sha256:${finalSha256}`,
      exitCode: completed.status,
    },
    result,
    resultSha256,
    summary: {
      status: "passed",
      normalizerStatus: result.status,
      artifactType: result.artifactType,
      inputSha256: `sha256:${rawSha256}`,
      outputSha256: `sha256:${finalSha256}`,
    },
  };
}

function trustChainDigest(bindings) {
  const orderedKeys = [
    "sourceHtmlSha256",
    ...(Object.prototype.hasOwnProperty.call(bindings, "sourceBriefSha256")
      ? ["sourceBriefSha256"]
      : []),
    "snapshotSha256",
    "rendererScriptSha256",
    "rawPdfSha256",
    "normalizerScriptSha256",
    "normalizerResultSha256",
    "finalPdfSha256",
  ];
  return sha256UriForText(
    orderedKeys.map((key) => `${key}=${bindings[key]}\n`).join("")
  );
}

async function renderPdf(
  inputPath,
  outputPath,
  executablePath,
  pageMargin,
  sourceBriefSha256 = null
) {
  const renderSnapshot = createRenderSnapshot(inputPath);
  const rawPdfPath = `${outputPath}.raw.pdf`;
  const runtimeViolations = new Set();
  let browser = null;

  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  for (const artifactPath of [rawPdfPath, outputPath, `${outputPath}.render-manifest.json`]) {
    fs.rmSync(artifactPath, { force: true });
  }

  try {
    browser = await chromium.launch({
      headless: true,
      executablePath,
    });
    const browserVersion = browser.version();
    const pdfOptions = {
      format: "Letter",
      printBackground: true,
      tagged: true,
      outline: true,
      margin: {
        top: pageMargin,
        right: pageMargin,
        bottom: pageMargin,
        left: pageMargin,
      },
    };
    const context = await browser.newContext({
      javaScriptEnabled: false,
      locale: "en-US",
      timezoneId: "UTC",
      colorScheme: "light",
      reducedMotion: "reduce",
      viewport: { width: 1280, height: 720 },
      deviceScaleFactor: 1,
    });

    await context.route("**/*", async (route) => {
      const requestUrl = route.request().url();
      if (/^https?:/i.test(requestUrl)) {
        runtimeViolations.add(`Network request blocked: ${requestUrl}`);
        await route.abort();
        return;
      }
      if (/^file:/i.test(requestUrl)) {
        let requestedPath;
        try {
          requestedPath = path.resolve(fileURLToPath(requestUrl));
        } catch {
          runtimeViolations.add(`Invalid local request blocked: ${requestUrl}`);
          await route.abort();
          return;
        }
        if (!isPathWithin(renderSnapshot.snapshotRoot, requestedPath)) {
          runtimeViolations.add(`Out-of-snapshot request blocked: ${requestUrl}`);
          await route.abort();
          return;
        }
      }
      await route.continue();
    });

    const page = await context.newPage();
    await page.emulateMedia({
      media: "print",
      colorScheme: "light",
      reducedMotion: "reduce",
    });
    await page.goto(pathToFileURL(renderSnapshot.snapshotHtmlPath).href, {
      waitUntil: "networkidle",
    });
    await page.evaluate(() => document.fonts.ready);
    if (runtimeViolations.size > 0) {
      throw new Error([...runtimeViolations].sort().join("; "));
    }
    await page.pdf({
      path: rawPdfPath,
      ...pdfOptions,
    });
    await context.close();

    const rawStats = fs.statSync(rawPdfPath);
    if (rawStats.size <= 0) {
      throw new Error(`Raw rendered PDF is empty: ${rawPdfPath}`);
    }
    const listTagNormalization = normalizeListTags(rawPdfPath, outputPath);
    const finalStats = fs.statSync(outputPath);
    if (finalStats.size <= 0) {
      throw new Error(`Rendered PDF is empty: ${outputPath}`);
    }

    const rendererScriptPath = path.resolve(__filename);
    const sourceHtmlSha256 = sha256UriForFile(inputPath);
    const rendererScriptSha256 = sha256UriForFile(rendererScriptPath);
    const rawPdfSha256 = sha256UriForFile(rawPdfPath);
    const finalPdfSha256 = sha256UriForFile(outputPath);
    const chainBindings = {
      sourceHtmlSha256,
      ...(sourceBriefSha256 ? { sourceBriefSha256 } : {}),
      snapshotSha256: renderSnapshot.manifest.snapshotSha256,
      rendererScriptSha256,
      rawPdfSha256,
      normalizerScriptSha256: listTagNormalization.scriptSha256,
      normalizerResultSha256: listTagNormalization.resultSha256,
      finalPdfSha256,
    };

    return {
      browserVersion,
      pdfOptions,
      rawPdfPath,
      rawPdfSha256,
      rawPdfBytes: rawStats.size,
      finalPdfSha256,
      finalPdfBytes: finalStats.size,
      rendererScriptPath,
      rendererScriptSha256,
      sourceHtmlSha256,
      renderSnapshot: renderSnapshot.manifest,
      listTagNormalization,
      chainBindings,
      chainSha256: trustChainDigest(chainBindings),
    };
  } finally {
    if (browser) {
      await browser.close();
    }
    fs.rmSync(renderSnapshot.snapshotRoot, { recursive: true, force: true });
  }
}

async function main() {
  const [, , inputHtml, outputPdf, requestedBrowser, requestedMargin, requestedBrief] = process.argv;
  if (!inputHtml || !outputPdf) {
    throw new Error(
      "Usage: node render-html-to-pdf-playwright.js <inputHtml> <outputPdf> [browserPath] [margin] [provenanceBrief]"
    );
  }

  const inputPath = path.resolve(inputHtml);
  const outputPath = path.resolve(outputPdf);
  const briefPath = requestedBrief ? path.resolve(requestedBrief) : null;
  const pageMargin = requestedMargin || "0.35in";
  if (!fs.existsSync(inputPath)) {
    throw new Error(`Input HTML does not exist: ${inputPath}`);
  }
  if (briefPath && !fs.existsSync(briefPath)) {
    throw new Error(`Provenance brief does not exist: ${briefPath}`);
  }
  const sourceBriefSha256 = briefPath ? sha256UriForFile(briefPath) : null;
  assertStaticLocalDocument(inputPath);

  const browserCandidates = [
    requestedBrowser,
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
    "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  ].filter(Boolean);
  const executablePath = browserCandidates.find((candidate) => fs.existsSync(candidate));
  if (!executablePath) {
    throw new Error("Could not find a Chromium-compatible browser for PDF rendering.");
  }

  const render = await renderPdf(
    inputPath,
    outputPath,
    executablePath,
    pageMargin,
    sourceBriefSha256
  );
  const manifest = {
    artifactType: "html_to_pdf_render_manifest",
    schemaVersion: MANIFEST_SCHEMA_VERSION,
    generatedAt: new Date().toISOString(),
    renderer: "playwright",
    rendererScriptPath: render.rendererScriptPath,
    rendererScriptSha256: render.rendererScriptSha256,
    playwrightVersion: require("playwright/package.json").version,
    nodeExecutablePath: process.execPath,
    nodeExecutableSha256: sha256UriForFile(process.execPath),
    nodeVersion: process.version,
    browserExecutablePath: executablePath,
    browserExecutableSha256: sha256UriForFile(executablePath),
    browserVersion: render.browserVersion,
    sourceHtmlPath: inputPath,
    sourceHtmlSha256: render.sourceHtmlSha256,
    sourceBriefPath: briefPath,
    sourceBriefSha256,
    renderSnapshot: render.renderSnapshot,
    rawPdf: {
      path: render.rawPdfPath,
      sha256: render.rawPdfSha256,
      bytes: render.rawPdfBytes,
    },
    outputPdfPath: outputPath,
    outputPdfSha256: render.finalPdfSha256,
    outputPdfBytes: render.finalPdfBytes,
    pdfOptions: render.pdfOptions,
    renderProfile: {
      javaScriptEnabled: false,
      locale: "en-US",
      timezoneId: "UTC",
      colorScheme: "light",
      reducedMotion: "reduce",
      viewport: { width: 1280, height: 720 },
      deviceScaleFactor: 1,
      networkPolicy: "http-and-https-aborted",
    },
    listTagNormalization: render.listTagNormalization,
    trustChain: {
      algorithm: "sha256",
      bindings: render.chainBindings,
      chainSha256: render.chainSha256,
    },
  };
  const manifestPath = `${outputPath}.render-manifest.json`;
  const temporaryManifestPath = `${manifestPath}.${process.pid}.tmp`;
  fs.writeFileSync(temporaryManifestPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
  fs.renameSync(temporaryManifestPath, manifestPath);
  console.log(outputPath);
}

if (require.main === module) {
  main().catch((error) => {
    console.error(error && error.stack ? error.stack : String(error));
    process.exit(1);
  });
}

module.exports = {
  assertStaticLocalDocument,
  collectSnapshotDependencies,
  createRenderSnapshot,
  isPathWithin,
  resolveLocalAsset,
  stableStringify,
  trustChainDigest,
};
