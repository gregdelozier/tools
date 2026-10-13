#!/usr/bin/env node
// Export a Reveal.js slide deck to PDF, one page per slide, using Reveal's
// own print-pdf mode (the deck's existing slide-assets/reveal.js and
// reveal.css already carry the @media print rules this relies on). Waits
// for Reveal.isReady() plus fonts and images, strips any speaker-notes
// elements before printing, and writes the output atomically.
//
//   node export_slides_pdf.mjs <deck.html> <output.pdf>
//
// Uses the same browser runtime as the existing Mermaid renderer.
import { createRequire } from 'node:module';
import { readFile, rename, rm } from 'node:fs/promises';
import { resolve, dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const tools = dirname(fileURLToPath(import.meta.url));
const require = createRequire(join(tools, 'md-to-pdf/package.json'));
// puppeteer 25+ ships as an ESM-only package, so it cannot be require()'d
// directly even via createRequire; resolve its entry path with require.resolve
// (pure path resolution, does not execute the module) and import() that path.
const { default: puppeteer } = await import(pathToFileURL(require.resolve('puppeteer')).href);
const [source, destination] = process.argv.slice(2);
if (!source || !destination || resolve(source) === resolve(destination)) {
  throw new Error('Usage: export_slides_pdf.mjs INPUT.html OUTPUT.pdf');
}
const options = JSON.parse(await readFile(join(tools, 'md-to-pdf/puppeteer.json'), 'utf8'));
const staged = `${resolve(destination)}.${process.pid}.tmp`;
let browser;
try {
  browser = await puppeteer.launch({ ...options, headless: true, timeout: 30000 });
  const page = await browser.newPage();
  await page.evaluateOnNewDocument(() => {
    document.addEventListener('DOMContentLoaded', () => {
      window.Reveal?.configure({ showNotes: false, pdfSeparateFragments: false, pdfMaxPagesPerSlide: 1 });
    });
  });
  const url = pathToFileURL(resolve(source));
  url.search = 'print-pdf';
  await page.goto(url.href, { waitUntil: 'networkidle0', timeout: 60000 });
  await page.waitForFunction(() => window.Reveal?.isReady() && document.querySelector('.pdf-page'));
  await page.evaluate(async () => {
    await document.fonts.ready;
    await Promise.all([...document.images].map(image => image.decode()));
    document.querySelectorAll('aside.notes, .speaker-notes').forEach(node => node.remove());
  });
  await page.pdf({ path: staged, preferCSSPageSize: true, printBackground: true, displayHeaderFooter: false });
  await rename(staged, resolve(destination));
  console.log(`Slide PDF: ${resolve(destination)}`);
} finally {
  if (browser) await browser.close();
  await rm(staged, { force: true });
}
